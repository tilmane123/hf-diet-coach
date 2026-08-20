import datetime
import re as _re
from difflib import SequenceMatcher

import pandas as pd
import streamlit as st
from db_connector import run_query, run_queries

_BATCH_SIZE = 50  # max recipe IDs per IN clause — keeps queries small on large markets

# ── Recipe deduplication helpers (module-level so diverse_top_n can reuse them) ──

# Strip trailing diet labels and "mit/with/met/..." + up to 5 words
# ({0,4} = 1 mandatory + 4 optional = max 5 words after the connector)
_STRIP_RE = _re.compile(
    r"\s*[\(\[]?\s*(bio|organic|vegan|veggie|vegetarisch|vegetarian|vegán)\s*[\)\]]?\s*$"
    r"|\s*[-–]?\s*(mit|with|met|avec|med|con|ohne|without)\s+[^\s,]+(\s+[^\s,]+){0,4}\s*$",
    _re.IGNORECASE,
)
_PREFIX_RE = _re.compile(
    r"^(bio|organic|vegan\w*|veggi\w*|vegetar\w*|bunter?|bunte?)\s+",
    _re.IGNORECASE,
)
_PUNCT_RE = _re.compile(r"[-–/]")

# Sauce/flavor keywords that define recipe identity — used by diverse_top_n
_FLAVOR_KW = _re.compile(
    r"\b(chimichurri|pesto|teriyaki|tikka|masala|curry|bolognese|arrabiata|"
    r"carbonara|stroganoff|shawarma|korma|satay|tahini|harissa|mole|gremolata|"
    r"aioli|romesco|piccata|marsala|cacciatore|salsa\s*verde)\b",
    _re.IGNORECASE,
)

_NUTRI_RE = _re.compile(r'nutri[-_\s]?score[-_\s]?([a-e])', _re.IGNORECASE)


def _extract_nutri_score(tags_str: str) -> str:
    """Return the Nutri-Score letter (A–E) found in a CPS tags string, or ''."""
    m = _NUTRI_RE.search(str(tags_str or ""))
    return m.group(1).upper() if m else ""


def _base(title: str) -> str:
    """Normalise a recipe title to its core dish name for deduplication."""
    t = _PUNCT_RE.sub(" ", str(title)).strip().lower()
    for _ in range(2):
        t_new = _PREFIX_RE.sub("", t).strip()
        if t_new == t:
            break
        t = t_new
    for _ in range(3):
        t_new = _STRIP_RE.sub("", t).strip()
        if t_new == t:
            break
        t = t_new
    return t


def _flavor_keys(title: str, sauce_paste: str = "") -> set:
    keys = {m.group().lower().replace(" ", "_") for m in _FLAVOR_KW.finditer(title)}
    if sauce_paste:
        keys.add(sauce_paste.strip().lower().replace(" ", "_").replace("-", "_"))
    return keys


def diverse_top_n(scored_df: pd.DataFrame, n: int = 10, max_per_flavor: int = 1,
                  sim_threshold: float = 0.55, seed_bases: list = None) -> pd.DataFrame:
    """
    Pick up to n recipes from a score-sorted DataFrame enforcing variety:
    - No more than max_per_flavor recipes share the same sauce/flavor keyword
    - No two recipes with a base-title similarity >= sim_threshold
    seed_bases: pre-populated list of base titles to check against (used so
    runner-up selections don't duplicate top-5 even at a relaxed threshold).
    """
    selected_rows = []
    flavor_counts: dict = {}
    selected_bases: list = list(seed_bases or [])

    for _, row in scored_df.iterrows():
        if len(selected_rows) >= n:
            break
        title   = str(row.get("title", "") or "")
        base    = _base(title)
        flavors = _flavor_keys(title, str(row.get("sauce_paste", "") or ""))

        if any(flavor_counts.get(f, 0) >= max_per_flavor for f in flavors):
            continue
        if any(SequenceMatcher(None, base, b).ratio() >= sim_threshold for b in selected_bases):
            continue

        selected_rows.append(row)
        selected_bases.append(base)
        for f in flavors:
            flavor_counts[f] = flavor_counts.get(f, 0) + 1

    return pd.DataFrame(selected_rows).reset_index(drop=True)


# Pack weight embedded in the SKU name. Covers every format seen in the data:
#   "Gurke (300g)"  "Brokkoli Reis 800g"  "Sliced Mushrooms - 120g"
#   "Zitrone (80-90g)" (range → midpoint)  "Kartoffeln (1kg)"
_GRAM_RE = _re.compile(r"(\d+(?:[.,]\d+)?)\s*(?:-\s*(\d+(?:[.,]\d+)?)\s*)?(kg|g)\b", _re.I)

# Preference order when choosing which serving-size pack list to read.
# Nutrition is published per 2 servings, so size 2 first.
_SIZE_PREFERENCE = ["2", "4", "3", "1"]


def _pack_grams(name: str) -> float:
    """Grams in a SKU pack, parsed from its name. 0.0 when the name states no weight.

    Whole-produce SKUs ("Avocado", "Green Pepper") carry no weight — common in
    the UK list — and contribute 0 rather than a guess.
    """
    best = 0.0
    for m in _GRAM_RE.finditer(str(name or "")):
        lo = float(m.group(1).replace(",", "."))
        hi = float(m.group(2).replace(",", ".")) if m.group(2) else lo
        val = (lo + hi) / 2
        if m.group(3).lower() == "kg":
            val *= 1000
        best = max(best, val)
    return best


_CPS_TABLE = "glue.public_edw_base_grain_live.recipe_csku_ingredient_picklist"
_CPS_SERVINGS = 2   # the 2P ingredient list


def _fetch_cps_ingredients(names: pd.DataFrame, mkt_up: str, segment: str):
    """Ingredient list + fresh-produce weight from the CPS 2-person picklist.

    Returns (ing_agg, veggie_agg), both keyed on recipe_id.

    CPS keys on recipe_code_unique, so this runs after the names query.
    culinary_sku_ratio is the fraction of the pack a recipe uses at this
    serving size (a 30 g ginger pack at ratio 0.5 contributes 15 g), which is
    what the customer actually eats — more accurate than counting whole packs.
    """
    empty_ing = pd.DataFrame(columns=["recipe_id", "ingredients"])
    empty_veg = pd.DataFrame(columns=["recipe_id", "veggie_count", "veggie_grams"])
    if names.empty or "unique_recipe_code" not in names.columns:
        return empty_ing, empty_veg

    codes = [str(c) for c in names["unique_recipe_code"].dropna().unique() if str(c)]
    if not codes:
        return empty_ing, empty_veg

    cps = _batched_query(f"""
        SELECT recipe_code_unique, ingredient_name, culinary_sku_name,
               culinary_sku_code, culinary_sku_ratio
        FROM {_CPS_TABLE}
        WHERE market = '{mkt_up}' AND segment = '{segment}'
          AND servings_size = {_CPS_SERVINGS}
          AND recipe_code_unique IN ('{{ids}}')
    """, codes)

    if cps.empty:
        return empty_ing, empty_veg

    # One row per SKU — the table can repeat a SKU across recipe versions
    cps = cps.drop_duplicates(subset=["recipe_code_unique", "culinary_sku_code"],
                              keep="first")
    code_to_id = names.set_index("unique_recipe_code")["recipe_id"].to_dict()
    cps["recipe_id"] = cps["recipe_code_unique"].map(code_to_id)
    cps = cps[cps["recipe_id"].notna()]
    if cps.empty:
        return empty_ing, empty_veg

    ing_agg = (
        cps.sort_values("ingredient_name")
        .groupby("recipe_id")["ingredient_name"]
        .apply(lambda x: sorted({str(i) for i in x if str(i) not in ("", "nan")})[:12])
        .reset_index()
        .rename(columns={"ingredient_name": "ingredients"})
    )

    phf = cps[cps["culinary_sku_code"].str.contains("PHF", na=False)].copy()
    if phf.empty:
        return ing_agg, empty_veg

    ratio = pd.to_numeric(phf["culinary_sku_ratio"], errors="coerce").fillna(0.0)
    phf["_g"] = phf["culinary_sku_name"].map(_pack_grams) * ratio
    veggie_agg = (
        phf.groupby("recipe_id")
        .agg(veggie_count=("ingredient_name", "nunique"), veggie_grams=("_g", "sum"))
        .reset_index()
    )
    # Weights cover the whole 2-serving recipe — divide down to one serving
    veggie_agg["veggie_grams"] = (veggie_agg["veggie_grams"] / _CPS_SERVINGS).round(0)
    return ing_agg, veggie_agg


def _pick_serving_size(picklist: pd.DataFrame) -> pd.DataFrame:
    """Reduce the per-size pack list to the one serving size each recipe uses.

    A recipe lists the same ingredient at several pack sizes (Rucola 50g / 75g /
    100g), with servings_ratio marking which pack applies at which serving size
    and how many are needed. Keeping only the active rows for one size also
    stops the ingredient list showing three variants of the same vegetable.
    Adds a '_servings' column holding the chosen size as an int.
    """
    if picklist.empty or "size" not in picklist.columns:
        picklist = picklist.copy()
        picklist["servings_ratio"] = 1.0
        picklist["_servings"] = 2
        return picklist

    pl = picklist.copy()
    pl["size"] = pl["size"].astype(str)
    pl["servings_ratio"] = pd.to_numeric(pl["servings_ratio"], errors="coerce").fillna(0.0)

    active = pl[pl["servings_ratio"] > 0]
    if active.empty:
        pl["_servings"] = 2
        return pl.drop_duplicates(subset=["recipe_id", "name"], keep="first")

    # Per recipe, take the first preferred size that actually has active packs
    available = active.groupby("recipe_id")["size"].apply(set)
    chosen = available.map(
        lambda sizes: next((s for s in _SIZE_PREFERENCE if s in sizes), sorted(sizes)[0])
    ).rename("_chosen")

    out = active.merge(chosen, left_on="recipe_id", right_index=True, how="left")
    out = out[out["size"] == out["_chosen"]].copy()
    out["_servings"] = pd.to_numeric(out["_chosen"], errors="coerce").fillna(2).astype(int)
    return out.drop(columns=["_chosen"])


def _week_window() -> tuple[tuple[int, int], tuple[int, int]]:
    """Return (min_week, year), (max_week, year) — current week through current+2."""
    today = datetime.date.today()
    iso_now = today.isocalendar()
    iso_max = (today + datetime.timedelta(weeks=2)).isocalendar()
    return (int(iso_now[1]), int(iso_now[0])), (int(iso_max[1]), int(iso_max[0]))


def _batched_query(query_template: str, ids: list, id_placeholder: str = "{ids}") -> pd.DataFrame:
    """Run a query in batches when the ID list is large, then concatenate results."""
    chunks = [ids[i:i + _BATCH_SIZE] for i in range(0, len(ids), _BATCH_SIZE)]
    parts = []
    for chunk in chunks:
        id_str = "','".join(str(x) for x in chunk)
        q = query_template.replace(id_placeholder, id_str)
        try:
            parts.append(run_query(q))
        except Exception:
            pass  # skip failed batch, don't crash entire fetch
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()


@st.cache_data(ttl=7200, show_spinner=False)
def get_available_weeks(market: str, region_code: str) -> list[dict]:
    """Return current week + next 3 weeks for this market (fetched directly by week number)."""
    (min_week, min_year), (max_week, max_year) = _week_window()

    # Build an explicit list of (week, year) pairs to query — avoids full table scan
    today = datetime.date.today()
    pairs = []
    for offset in range(3):
        iso = (today + datetime.timedelta(weeks=offset)).isocalendar()
        pairs.append((int(iso[1]), int(iso[0])))

    # Build WHERE clause for exactly these week/year combos
    conditions = " OR ".join(
        f"(week_number = {w} AND week_year = {y})" for w, y in pairs
    )

    df = run_query(f"""
        SELECT DISTINCT week_number, week_year
        FROM glue.menu_services.menu_global
        WHERE market = '{market}'
          AND region_code = '{region_code}'
          AND item_type = 'recipe'
          AND status NOT IN ('draft', 'removed')
          AND recipe_id IS NOT NULL
          AND ({conditions})
        ORDER BY week_year DESC, week_number DESC
    """)

    def _week_label(week: int, year: int) -> str:
        try:
            mon = datetime.date.fromisocalendar(year, week, 1)
            sun = mon + datetime.timedelta(days=6)
            if mon.month == sun.month:
                date_part = f"{mon.day}–{sun.day} {mon.strftime('%b')}"
            else:
                date_part = f"{mon.day} {mon.strftime('%b')} – {sun.day} {sun.strftime('%b')}"
            return f"Week {week}  ·  {date_part} {year}"
        except Exception:
            return f"W{week} {year}"

    return [
        {"label": _week_label(int(row.week_number), int(row.week_year)),
         "short": f"W{int(row.week_number)} {int(row.week_year)}",
         "week": int(row.week_number), "year": int(row.week_year)}
        for _, row in df.iterrows()
    ]


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_menu(market: str, region_code: str, locale: str, segment: str,
               week: int, year: int) -> pd.DataFrame:
    """Fetch full enriched menu for a given market/week with names, images, nutrition."""

    # Step 1: menu slots — deduplicated by recipe_id
    menu = run_query(f"""
        WITH ranked AS (
            SELECT slot_number, slot_group, recipe_id, product_category_name, sub_type, status,
                   ROW_NUMBER() OVER (
                       PARTITION BY recipe_id
                       ORDER BY CASE status
                           WHEN 'published' THEN 1 WHEN 'planned' THEN 2
                           WHEN 'locked' THEN 3 WHEN 'unlocked' THEN 4 ELSE 5 END,
                       slot_number
                   ) AS rn
            FROM glue.menu_services.menu_global
            WHERE week_number = {week} AND week_year = {year}
              AND market = '{market}' AND region_code = '{region_code}'
              AND week_year = {year}
              AND recipe_id IS NOT NULL AND item_type = 'recipe'
              AND status NOT IN ('draft', 'removed')
        )
        SELECT slot_number, slot_group, recipe_id, product_category_name, sub_type, status
        FROM ranked WHERE rn = 1 ORDER BY slot_number
    """)

    if menu.empty:
        return pd.DataFrame()

    menu = menu.drop_duplicates(subset=["recipe_id"], keep="first").reset_index(drop=True)
    ids = [str(x) for x in menu["recipe_id"].dropna().unique().tolist()]
    id_str = "','".join(ids)

    mkt_up = market.upper()

    # Steps 2-4: run all enrichment queries over the cached connection
    res = run_queries({
        "names": f"""
            WITH t AS (
                SELECT t.recipe_id, t.title, t.subtitle,
                       r.image_url AS old_img, r.unique_recipe_code, r.difficulty, r.dish_type,
                       r.active_cooking_time, r.total_time,
                       ROW_NUMBER() OVER (PARTITION BY t.recipe_id ORDER BY t.published_at DESC) AS rn
                FROM glue.culinary_services.recipe_editorial_translations_global t
                LEFT JOIN glue.culinary_services.recipe_global r ON t.recipe_id = r.id
                WHERE t.locale = '{locale}' AND t.market = '{market}'
                  AND t.recipe_id IN ('{id_str}')
            ),
            base AS (
                SELECT recipe_id, title, subtitle, old_img, unique_recipe_code,
                       difficulty, dish_type, active_cooking_time, total_time
                FROM t WHERE rn = 1
            ),
            rc AS (
                SELECT recipe_code_unique, primary_protein, sauce_paste,
                       ROW_NUMBER() OVER (PARTITION BY recipe_code_unique ORDER BY recipe_code_unique) AS rn
                FROM glue.public_edw_base_grain_live.recipe_contents
                WHERE market = '{mkt_up}'
            ),
            nr AS (
                SELECT recipe_code_unique, image_url AS new_img, internal_image_url AS int_img,
                       CAST(tags AS STRING) AS tags,
                       CAST(recipe_label AS STRING) AS recipe_label,
                       CAST(target_preferences AS STRING) AS target_preferences,
                       ROW_NUMBER() OVER (PARTITION BY recipe_code_unique ORDER BY recipe_code_unique) AS rn
                FROM glue.public_edw_base_grain_live.recipe
                WHERE market = '{mkt_up}'
            )
            SELECT b.recipe_id, b.title, b.subtitle, b.unique_recipe_code,
                   b.difficulty, b.dish_type, b.active_cooking_time, b.total_time,
                   rc.primary_protein, rc.sauce_paste,
                   nr.tags, nr.recipe_label, nr.target_preferences,
                   CASE
                     WHEN b.old_img IS NOT NULL AND b.old_img LIKE 'http%' THEN b.old_img
                     WHEN nr.new_img IS NOT NULL AND nr.new_img LIKE 'http%' THEN nr.new_img
                     WHEN nr.int_img IS NOT NULL AND nr.int_img LIKE 'http%' THEN nr.int_img
                     ELSE NULL
                   END AS image_url
            FROM base b
            LEFT JOIN rc ON rc.recipe_code_unique = b.unique_recipe_code AND rc.rn = 1
            LEFT JOIN nr ON nr.recipe_code_unique = b.unique_recipe_code AND nr.rn = 1
        """,
        "nutrition": f"""
            WITH ranked AS (
                SELECT recipe_id, serving, energy, proteins, carbs, fats,
                       saturatedfats, fibers, sugars, salt, calcium, iron, potassium,
                       ROW_NUMBER() OVER (PARTITION BY recipe_id ORDER BY published_at DESC) AS rn
                FROM glue.culinary_services.recipe_segment_nutrition_global
                WHERE market = '{market}' AND recipe_id IN ('{id_str}')
            )
            SELECT * FROM ranked WHERE rn = 1
        """,
    })

    names     = res["names"].drop_duplicates(subset=["recipe_id"], keep="first")
    nutrition = res["nutrition"].drop(columns=["rn"], errors="ignore").drop_duplicates(subset=["recipe_id"], keep="first")

    # Ingredients + produce weight from the CPS 2-person picklist, keyed on
    # unique_recipe_code — so it needs the names result first.
    ing_agg, veggie_agg = _fetch_cps_ingredients(names, mkt_up, segment)

    # Join + final dedup
    df = (
        menu
        .merge(names, on="recipe_id", how="left")
        .merge(nutrition, on="recipe_id", how="left")
        .merge(ing_agg, on="recipe_id", how="left")
        .merge(veggie_agg, on="recipe_id", how="left")
    )
    df["veggie_count"] = df["veggie_count"].fillna(0).astype(int)
    df["veggie_grams"] = df.get("veggie_grams", pd.Series(dtype=float)).fillna(0.0)
    df = df.drop_duplicates(subset=["recipe_id"], keep="first").reset_index(drop=True)

    # Rename columns early so dedup code can reference 'slot'
    df = df.rename(columns={
        "slot_number": "slot",
        "product_category_name": "category",
        "energy": "calories",
        "proteins": "protein",
        "fats": "fat",
        "saturatedfats": "sat_fat",
        "fibers": "fibre",
    })

    # Deduplicate recipe variants — same dish in multiple editions
    df = df.sort_values("slot").reset_index(drop=True)
    df["_base"] = df["title"].fillna("").apply(_base)

    # Pass 1: exact base-title dedup
    df = df.drop_duplicates(subset=["_base"], keep="first").reset_index(drop=True)

    # Pass 2: prefix containment
    bases = df["_base"].tolist()
    drop_idx = set()
    for i in range(len(bases)):
        if i in drop_idx:
            continue
        for j in range(i + 1, len(bases)):
            if j in drop_idx:
                continue
            a, b = bases[i], bases[j]
            if b.startswith(a) or a.startswith(b):
                drop_idx.add(j if len(a) <= len(b) else i)

    # Pass 3: fuzzy similarity ≥ 0.75
    remaining = [idx for idx in range(len(bases)) if idx not in drop_idx]
    for ii, i in enumerate(remaining):
        for j in remaining[ii + 1:]:
            if j in drop_idx:
                continue
            if SequenceMatcher(None, bases[i], bases[j]).ratio() >= 0.75:
                drop_idx.add(j)

    df = df.drop(index=list(drop_idx)).drop(columns=["_base"]).reset_index(drop=True)

    df["nutri_score"] = df["tags"].fillna("").apply(_extract_nutri_score)

    return df.dropna(subset=["calories", "protein", "fibre"]).reset_index(drop=True)
