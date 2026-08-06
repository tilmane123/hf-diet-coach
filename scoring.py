"""
Dietary scoring functions. Each returns a float 0–100.
Input: a row from fetch_menu() DataFrame + an optional weights dict.
Defaults are imported from config.DIET_WEIGHTS — override at call time to experiment.
"""

import re
import pandas as pd
from config import DIET_WEIGHTS, DIET_GROUP_RULES, DIET_TAGS


# ── Protein source detection ──────────────────────────────────────────────────

RED_MEAT = (
    r"\b("
    # English
    r"beef|roastbeef|roast.?beef|steak|burger|pork|bacon|lamb|sausage|salami|chorizo|prosciutto|veal|bison|venison"
    r"|ribeye|t-bone|ossobuco|meatball|minced.?beef|ground.?beef|pulled.?pork|pulled.?beef"
    # German
    r"|rind\w*|runder\w*|hack\w*|schwein\w*|speck|lamm|wurst|gulasch|goulash"
    r"|kalb\w*|hirsch|reh\b|wildschwein|wildschweinhack"
    # Dutch
    r"|rundvlees|herten\w*|hertengehakt|hertenvlees|wildgehakt|varken\w*|lams\w*"
    r"|gehakt\w*|worst\w*|slavink\w*|frikandel\w*|tartaar|balletje\w*"
    # French
    r"|boeuf|bœuf|veau|agneau|porc|jambon|gibier|sanglier|cerf|chevreuil|gigot|tartare"
    r"|entrecôte|entrecote|côtelette|côte.?de.?bœuf|magret(?!.{0,10}canard)"
    # Swedish
    r"|nötkött|nöthack|fläsk\w*|kalv\w*|vildsvin|rådjur|älg\b|hjort\w*|korv|fårkött|rensdyr|ren\b"
    # Danish/Norwegian
    r"|oksekød|oksehack|svinekød|kjøttdeig|lammekød|vildt|hjortekød|kalvekød|vilt\b"
    # Italian/Spanish/general
    r"|bolognese|ragù|ragu|osso.?buco|carpaccio|pancetta|mortadella|coppa"
    r")\b"
)

POULTRY  = r"\b(chicken|hähnchen|hühnchen|poulet|kip|kyckling|kylling|turkey|pute|dinde|kalkoen|duck|ente|canard|eend|anka|and\b|perlhuhn|guinea|pintade|faisan|pheasant|quail|wachtel|caille|kwartel|vaktel|vagtel)\b"
FISH     = r"\b(salmon|lachs|saumon|zalm|lax|laks|cod|kabeljau|morue|kabeljauw|torsk|tuna|thon|tonijn|tonfisk|tunfisk|shrimp|garnele|crevette|garnaal|räkor|rejer|tilapia|trout|forelle|truite|forel|öring|ørred)\b"
PLANT_P  = (
    r"\b("
    # Tofu / tempeh / seitan / quorn
    r"tofu|tempeh|seitan|quorn"
    # Lentils (EN/DE/NL/FR/SE/DK)
    r"|lentil\w*|linse\w*|lentille\w*|linzen|linser"
    # Chickpeas
    r"|chickpea\w*|kichererbse\w*|pois.?chiche|kikkererwt\w*|kikärtor|kikærter"
    # Beans (EN/DE/NL/FR/SE/DK + common compounds)
    r"|bean\w*|bohne\w*|haricot\w*|boon|bonen|sojaboon|sojabonen|kidneyboon|kidneybonen"
    r"|böna|bönor|bønne\w*|erbse\w*|peulvruch\w*|doperwt\w*|erwten"
    # Falafel / quinoa / edamame
    r"|falafel|quinoa|edamame"
    # Vegan / vegetarian labels (catches veggie menu slots in any language)
    r"|vegan|vegetarisch|vegetarian|végétarien\w*|vegetarisk\w*|veggie"
    r")\b"
)
LEGUMES  = r"\b(lentil|linse|lentille|linzen|linser|chickpea|kichererbse|kikkererwt|kikärtor|bean|bohne|haricot|boon|böna|bønne)\b"
WHOLEGR  = r"\b(whole.?grain|vollkorn|grain entier|volkornen|fullkorn|fuldkorn|bulgur|couscous|farro|freekeh|barley|gerste|orge|gerst|korn)\b"
FISH_EXT = r"\b(anchovie|sardine|herring|hering|hareng|haring|sill|sild|mackerel|makrele|maquereau|makreel|makrill|makrel|mussel|muschel|moule|mossel|mussla|musling|squid|octopus|seabass|dorade)\b"


def _text(row) -> str:
    return " ".join([
        str(row.get("title", "") or ""),
        str(row.get("subtitle", "") or ""),
        str(row.get("sub_type", "") or ""),    # e.g. "Veggie", "Vegetarisch"
        str(row.get("dish_type", "") or ""),   # e.g. "vegetarian", "vegan"
        str(row.get("category", "") or ""),
        " ".join(row.get("ingredients", []) or []),
    ]).lower()


_PP_MAP = {
    "red_meat": ("beef", "pork", "lamb", "veal", "venison", "bison", "rabbit", "duck"),
    "poultry":  ("chicken", "turkey", "guinea", "quail", "partridge"),
    "fish":     ("salmon", "cod", "tuna", "shrimp", "prawn", "fish", "hake",
                 "tilapia", "trout", "pangasius", "shellfish", "crab", "lobster"),
    "plant":    ("veggie", "vegetarian", "vegan", "tofu", "tempeh", "lentil",
                 "chickpea", "bean", "falafel", "quorn", "seitan", "halloumi",
                 "plant", "legume"),
}

def _map_primary_protein(pp: str) -> str | None:
    """Map structured primary_protein values (e.g. 'Beef-Steak') to our 5 categories."""
    pp_lower = pp.lower()
    for cat, keywords in _PP_MAP.items():
        if any(kw in pp_lower for kw in keywords):
            return cat
    return None


def _detect_protein(row) -> str:
    # Structured primary_protein field (new Databricks source) — most reliable
    pp = str(row.get("primary_protein", "") or "").strip()
    if pp:
        mapped = _map_primary_protein(pp)
        if mapped:
            return mapped

    # Title-first regex — overrides ingredient text for side-dish false positives
    title = str(row.get("title", "") or "").lower()
    t = _text(row)
    if re.search(RED_MEAT, title): return "red_meat"
    if re.search(FISH,     title): return "fish"
    if re.search(POULTRY,  title): return "poultry"
    # Fall back to full ingredient text — plant dishes often have no animal keyword in title
    if re.search(PLANT_P,  t):     return "plant"
    if re.search(RED_MEAT, t):     return "red_meat"
    if re.search(FISH,     t):     return "fish"
    if re.search(POULTRY,  t):     return "poultry"
    return "other"


def _clamp(v, lo=0.0, hi=1.0): return max(lo, min(hi, v))
def _w(weights, key): return float(weights.get(key, 0))

def _prot_score(weights, prot_type) -> float:
    return float(weights.get(f"prot_{prot_type}", 0.3))

def _normalise_weights(weights: dict, keys: list) -> dict:
    """Return a copy of weights with the given w_ keys normalised to sum=1."""
    total = sum(weights.get(k, 0) for k in keys)
    if total == 0: return weights
    out = dict(weights)
    for k in keys:
        out[k] = weights.get(k, 0) / total
    return out


# ── Improve Sports Performance ────────────────────────────────────────────────

def score_sports(row, weights: dict | None = None) -> float:
    """Protein grams lead; source quality modifies rather than dominates."""
    w = _normalise_weights(weights or DIET_WEIGHTS["sports"],
                           ["w_prot", "w_kcal", "w_fibre", "w_sfat", "w_salt"])
    kcal = float(row.get("calories") or 0)
    if kcal == 0: return 0.0

    grams_s  = _clamp(float(row.get("protein") or 0) / w.get("protein_target_g", 30.0))
    source_s = _prot_score(w, _detect_protein(row))
    prot_s   = 0.75 * grams_s + 0.25 * source_s

    kcal_s   = _clamp(1 - abs(kcal - w.get("kcal_target", 650)) / w.get("kcal_range", 350))
    fibre_s  = _clamp(float(row.get("fibre") or 0) / w.get("fibre_target_g", 8))
    sfat_pct = (float(row.get("sat_fat") or 0) * 9 / kcal)
    sfat_s   = _clamp(1 - sfat_pct / w.get("sfat_max_pct", 0.12))
    salt_s   = _clamp(1 - float(row.get("salt") or 0) / w.get("salt_max_g", 2.5))

    return round((w["w_prot"] * prot_s + w["w_kcal"] * kcal_s +
                  w["w_fibre"] * fibre_s + w["w_sfat"] * sfat_s +
                  w["w_salt"] * salt_s) * 100, 1)


# ── Maximized vegetables ──────────────────────────────────────────────────────

def score_max_veggies(row, weights: dict | None = None) -> float:
    """Grams of PHF fresh produce per serving lead the score."""
    w = _normalise_weights(weights or DIET_WEIGHTS["max_veggies"],
                           ["w_veg", "w_fibre", "w_prot", "w_kcal", "w_sfat"])
    kcal = float(row.get("calories") or 0)
    if kcal == 0: return 0.0

    grams = float(row.get("veggie_grams") or 0)
    if grams > 0:
        veg_s = _clamp(grams / w.get("veg_target_g", 300.0))
    else:
        # No SKU states a weight (common in the UK list) — fall back to variety
        veg_s = _clamp(float(row.get("veggie_count") or 0) / 8.0)

    fibre_s  = _clamp(float(row.get("fibre") or 0) / w.get("fibre_target_g", 10))
    prot_s   = _prot_score(w, _detect_protein(row))
    kcal_s   = _clamp(1 - abs(kcal - w.get("kcal_target", 550)) / w.get("kcal_range", 350))
    sfat_pct = (float(row.get("sat_fat") or 0) * 9 / kcal)
    sfat_s   = _clamp(1 - sfat_pct / w.get("sfat_max_pct", 0.10))

    return round((w["w_veg"] * veg_s + w["w_fibre"] * fibre_s +
                  w["w_prot"] * prot_s + w["w_kcal"] * kcal_s +
                  w["w_sfat"] * sfat_s) * 100, 1)


# ── EAT-Lancet ────────────────────────────────────────────────────────────────

def score_eat_lancet(row, weights: dict | None = None) -> float:
    w = _normalise_weights(weights or DIET_WEIGHTS["eat_lancet"],
                           ["w_prot", "w_fibre", "w_sfat", "w_kcal"])
    kcal = float(row.get("calories") or 0)
    if kcal == 0: return 0.0

    prot_s  = _prot_score(w, _detect_protein(row))
    fibre_s = _clamp(float(row.get("fibre") or 0) / w.get("fibre_target_g", 10))
    sfat_s  = _clamp(1 - (float(row.get("sat_fat") or 0) * 9 / kcal) / w.get("sfat_max_pct", 0.07))
    kcal_s  = _clamp(1 - abs(kcal - w.get("kcal_target", 550)) / w.get("kcal_range", 350))

    return round((w["w_prot"] * prot_s + w["w_fibre"] * fibre_s +
                  w["w_sfat"] * sfat_s + w["w_kcal"] * kcal_s) * 100, 1)


# ── WHO ───────────────────────────────────────────────────────────────────────

def score_who(row, weights: dict | None = None) -> float:
    w = _normalise_weights(weights or DIET_WEIGHTS["who"],
                           ["w_salt", "w_sugar", "w_sfat", "w_fibre", "w_prot"])
    kcal = float(row.get("calories") or 0)
    if kcal == 0: return 0.0

    salt_s  = _clamp(1 - float(row.get("salt") or 0) / w.get("salt_max_g", 1.25))
    sug_pct = (float(row.get("sugars") or 0) * 4 / kcal)
    sugar_s = _clamp(1 - sug_pct / w.get("sugar_max_pct", 0.05))
    sfat_s  = _clamp(1 - (float(row.get("sat_fat") or 0) * 9 / kcal) / w.get("sfat_max_pct", 0.10))
    fibre_s = _clamp(float(row.get("fibre") or 0) / w.get("fibre_target_g", 10))
    prot_s  = _prot_score(w, _detect_protein(row))

    return round((w["w_salt"] * salt_s + w["w_sugar"] * sugar_s +
                  w["w_sfat"] * sfat_s + w["w_fibre"] * fibre_s +
                  w["w_prot"] * prot_s) * 100, 1)


# ── Mediterranean ─────────────────────────────────────────────────────────────

def score_mediterranean(row, weights: dict | None = None) -> float:
    w = _normalise_weights(weights or DIET_WEIGHTS["mediterranean"],
                           ["w_fish", "w_prot", "w_fibre", "w_sfat", "w_salt", "w_legume", "w_red", "w_grain"])
    kcal = float(row.get("calories") or 0)
    if kcal == 0: return 0.0

    t = _text(row)
    prot = _detect_protein(row)
    fish_s   = 1.0 if (prot == "fish" or re.search(FISH_EXT, t)) else 0.0
    legume_s = 1.0 if re.search(LEGUMES, t) else 0.0
    grain_s  = 1.0 if re.search(WHOLEGR, t) else 0.0
    red_s    = 0.0 if prot == "red_meat" else 1.0
    prot_s   = _prot_score(w, prot)   # fish/plant >> poultry >> red meat
    sfat_s   = _clamp(1 - (float(row.get("sat_fat") or 0) * 9 / kcal) / w.get("sfat_max_pct", 0.10))
    salt_s   = _clamp(1 - float(row.get("salt") or 0) / w.get("salt_max_g", 2.0))
    fibre_s  = _clamp(float(row.get("fibre") or 0) / w.get("fibre_target_g", 9))

    return round((w["w_fish"] * fish_s + w["w_prot"] * prot_s +
                  w["w_fibre"] * fibre_s + w["w_sfat"] * sfat_s +
                  w["w_salt"] * salt_s + w["w_legume"] * legume_s +
                  w["w_red"] * red_s + w["w_grain"] * grain_s) * 100, 1)


# ── Blue Zone ─────────────────────────────────────────────────────────────────

def score_blue_zone(row, weights: dict | None = None) -> float:
    w = _normalise_weights(weights or DIET_WEIGHTS["blue_zone"],
                           ["w_prot", "w_fibre", "w_legume", "w_sugar", "w_kcal", "w_salt"])
    kcal = float(row.get("calories") or 0)
    if kcal == 0: return 0.0

    t = _text(row)
    prot_s   = _prot_score(w, _detect_protein(row))
    legume_s = 1.0 if re.search(LEGUMES, t) else 0.0
    fibre_s  = _clamp(float(row.get("fibre") or 0) / w.get("fibre_target_g", 10))
    sug_pct  = (float(row.get("sugars") or 0) * 4 / kcal)
    sugar_s  = _clamp(1 - sug_pct / w.get("sugar_max_pct", 0.05))
    salt_s   = _clamp(1 - float(row.get("salt") or 0) / w.get("salt_max_g", 1.5))
    thr = w.get("kcal_light_threshold", 400)
    rng = w.get("kcal_range", 400)
    kcal_s   = _clamp(1 - max(0, kcal - thr) / rng)

    return round((w["w_prot"] * prot_s + w["w_fibre"] * fibre_s +
                  w["w_legume"] * legume_s + w["w_sugar"] * sugar_s +
                  w["w_kcal"] * kcal_s + w["w_salt"] * salt_s) * 100, 1)


# ── Dispatcher ────────────────────────────────────────────────────────────────

SCORE_FN = {
    "sports":        score_sports,
    "max_veggies":   score_max_veggies,
    "eat_lancet":    score_eat_lancet,
    "who":           score_who,
    "mediterranean": score_mediterranean,
    "blue_zone":     score_blue_zone,
}


# ── CPS tag alignment ─────────────────────────────────────────────────────────
# Share of the score set by whether a recipe carries the framework's CPS tags.
# A boost rather than a hard filter: tag vocabularies differ per market, and
# filtering would empty the results in markets that lack a given tag.
TAG_BLEND = 0.25

# Fit by number of primary tags matched. A secondary-only match scores 0.45.
_TAG_STEPS = {0: 0.0, 1: 0.75, 2: 0.90}
_SECONDARY_ONLY = 0.45


def _tag_text(row) -> str:
    """All tag-ish fields for a recipe, lowercased into one searchable string."""
    return " ".join(
        str(row.get(c) or "") for c in ("tags", "recipe_label", "target_preferences")
    ).lower()


def tag_fit(row, diet_key: str) -> float:
    """How well a recipe's CPS tags match the framework, 0-1."""
    spec = DIET_TAGS.get(diet_key)
    if not spec:
        return 0.0
    text = _tag_text(row)
    if not text.strip():
        return 0.0
    n_primary = sum(1 for p in spec.get("primary", []) if p in text)
    if n_primary:
        return _TAG_STEPS.get(n_primary, 1.0)
    if any(s in text for s in spec.get("secondary", [])):
        return _SECONDARY_ONLY
    return 0.0


def _safe_score(fn, row, weights) -> float:
    try:
        score = fn(row, weights)
        cap = (weights or {}).get("red_meat_cap", None)
        if cap is not None and _detect_protein(row) == "red_meat":
            score = min(score, float(cap))
        return score
    except Exception:
        return 0.0


def _enforce_group_rules(group: pd.DataFrame, rules: dict, pool: pd.DataFrame) -> pd.DataFrame:
    """Replace excess red meat recipes with next-best alternatives from pool."""
    max_rm = rules.get("max_red_meat", 5)

    # Tag protein type
    group = group.copy()
    group["_prot"] = group.apply(_detect_protein, axis=1)

    rm_rows = group[group["_prot"] == "red_meat"].sort_values("score", ascending=True)
    excess  = len(rm_rows) - max_rm
    if excess <= 0:
        return group.drop(columns=["_prot"]).sort_values("score", ascending=False).reset_index(drop=True)

    # Remove the lowest-scoring excess red meat recipes
    remove_ids = set(rm_rows.head(excess)["recipe_id"].tolist())
    group = group[~group["recipe_id"].isin(remove_ids)].drop(columns=["_prot"])

    # Fill slots from pool, skipping red meat if cap already reached
    used_ids = set(group["recipe_id"].tolist())
    rm_count = sum(1 for _, r in group.iterrows() if _detect_protein(r) == "red_meat")

    for _, candidate in pool.iterrows():
        if len(group) >= 5:
            break
        if candidate["recipe_id"] in used_ids:
            continue
        if _detect_protein(candidate) == "red_meat" and rm_count >= max_rm:
            continue
        group = pd.concat([group, candidate.to_frame().T], ignore_index=True)
        used_ids.add(candidate["recipe_id"])
        if _detect_protein(candidate) == "red_meat":
            rm_count += 1

    return group.sort_values("score", ascending=False).reset_index(drop=True)


def score_menu(df: pd.DataFrame, diet_key: str, weights: dict | None = None,
               goal_keys=None, pref_keys=None) -> pd.DataFrame:
    """Score all recipes, apply group rules to Top 5 and Runner-up 5, return full df.

    goal_keys / pref_keys come from the pre-section questionnaire. They are
    blended in here — before group rules and rescaling — so personalisation
    changes which recipes reach the Top 5, not just their printed scores.
    """
    if df.empty:
        return df.copy()
    fn = SCORE_FN[diet_key]
    out = df.copy()
    out["score"] = out.apply(lambda row: _safe_score(fn, row, weights), axis=1)

    # CPS tag alignment — lifts recipes carrying the framework's tags
    if diet_key in DIET_TAGS:
        tf = out.apply(lambda row: tag_fit(row, diet_key), axis=1)
        out["tag_fit"] = (tf * 100).round(0)
        out["score"] = (out["score"] * (1 - TAG_BLEND) + tf * 100 * TAG_BLEND).round(1)

    if goal_keys or pref_keys:
        from goals import blend   # local import: goals.py imports from this module
        out = blend(out, goal_keys, pref_keys)

    out = out.sort_values("score", ascending=False).reset_index(drop=True)

    rules = DIET_GROUP_RULES.get(diet_key, {})
    if not rules:
        return out

    # Split into top5, runner5, rest — enforce rules on each group
    top5    = out.iloc[:5].copy()
    runner5 = out.iloc[5:10].copy()
    rest    = out.iloc[10:].copy()

    pool_for_top    = pd.concat([runner5, rest], ignore_index=True)
    top5            = _enforce_group_rules(top5, rules, pool_for_top)

    used_in_top     = set(top5["recipe_id"].tolist())
    pool_for_runner = out[~out["recipe_id"].isin(used_in_top)].reset_index(drop=True)
    runner5         = pool_for_runner.iloc[:5].copy()
    runner5         = _enforce_group_rules(runner5, rules, pool_for_runner.iloc[5:])

    used_both       = used_in_top | set(runner5["recipe_id"].tolist())
    remainder       = out[~out["recipe_id"].isin(used_both)].reset_index(drop=True)

    result = pd.concat([top5, runner5, remainder], ignore_index=True)
    return _rescale_scores(result)


def _rescale_scores(df: pd.DataFrame, lo: float = 72.0, hi: float = 97.0) -> pd.DataFrame:
    """
    Rescale raw scores to [lo, hi] so the week's best recipe → hi and
    the week's worst → lo. Preserves relative gaps; makes display numbers
    sit comfortably in the 72–97 range instead of clustering around 50-60.
    """
    if df.empty or "score" not in df.columns:
        return df
    s_min = df["score"].min()
    s_max = df["score"].max()
    if s_max <= s_min:
        df = df.copy()
        df["score"] = round((lo + hi) / 2, 1)
        return df
    df = df.copy()
    df["score"] = (lo + (df["score"] - s_min) / (s_max - s_min) * (hi - lo)).round(1)
    return df
