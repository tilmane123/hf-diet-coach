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

    return [
        {"label": f"W{int(row.week_number)} {int(row.week_year)}",
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
                       ROW_NUMBER() OVER (PARTITION BY recipe_code_unique ORDER BY recipe_code_unique) AS rn
                FROM glue.public_edw_base_grain_live.recipe
                WHERE market = '{mkt_up}'
            )
            SELECT b.recipe_id, b.title, b.subtitle, b.unique_recipe_code,
                   b.difficulty, b.dish_type, b.active_cooking_time, b.total_time,
                   rc.primary_protein, rc.sauce_paste,
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
        "picklist": f"""
            WITH latest AS (
                SELECT recipe_id, name, code,
                       ROW_NUMBER() OVER (PARTITION BY recipe_id, name ORDER BY published_at DESC) AS rn
                FROM glue.culinary_services.recipe_procurement_picklist_culinarysku_global
                WHERE market = '{market}' AND segment_name = '{segment}'
                  AND recipe_id IN ('{id_str}')
            )
            SELECT recipe_id, name, code FROM latest WHERE rn = 1 ORDER BY recipe_id, name
        """,
    })

    names     = res["names"].drop_duplicates(subset=["recipe_id"], keep="first")
    nutrition = res["nutrition"].drop(columns=["rn"], errors="ignore").drop_duplicates(subset=["recipe_id"], keep="first")
    picklist  = res["picklist"]

    ing_agg     = pd.DataFrame(columns=["recipe_id", "ingredients"])
    veggie_agg  = pd.DataFrame(columns=["recipe_id", "veggie_count"])
    if not picklist.empty:
        ing_agg = (
            picklist.groupby("recipe_id")["name"]
            .apply(lambda x: list(x)[:12])
            .reset_index()
            .rename(columns={"name": "ingredients"})
        )
        # Count distinct fresh-produce items (PHF = fresh fruit & veg)
        phf = picklist[picklist["code"].str.startswith("PHF", na=False)]
        if not phf.empty:
            veggie_agg = (
                phf.groupby("recipe_id")["name"]
                .nunique()
                .reset_index()
                .rename(columns={"name": "veggie_count"})
            )

    # Join + final dedup
    df = (
        menu
        .merge(names, on="recipe_id", how="left")
        .merge(nutrition, on="recipe_id", how="left")
        .merge(ing_agg, on="recipe_id", how="left")
        .merge(veggie_agg, on="recipe_id", how="left")
    )
    df["veggie_count"] = df["veggie_count"].fillna(0).astype(int)
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

    return df.dropna(subset=["calories", "protein", "fibre"]).reset_index(drop=True)
