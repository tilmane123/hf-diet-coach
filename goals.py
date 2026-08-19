"""Health-goal fit scoring.

Turns the pre-section answers into a per-recipe fit score in [0, 1], which
score_menu() blends into the raw diet score *before* group rules and
rescaling — so goals influence which recipes reach the Top 5, not just the
numbers printed on them.

Each goal maps to either:
  - a metric  — read straight off the recipe row (veggies, protein, fibre…)
  - a diet    — reuse an existing framework's scorer (health-conscious → WHO)
"""

from __future__ import annotations

import re
import pandas as pd

from config import DIET_WEIGHTS
from scoring import SCORE_FN, WHOLEGR, _clamp, _text

# Share of the blended score driven by goal fit. The diet framework stays
# dominant at 0.30 — goals re-rank within the diet, they don't override it.
GOAL_BLEND = 0.30

# Reference values at which a goal scores full marks.
_VEG_GRAMS_TARGET = 250.0   # g of PHF produce per serving (WHO: 400 g/day)
_VEG_COUNT_TARGET = 8.0     # distinct PHF items — fallback only
_PROTEIN_TARGET = 30.0    # g per serving
_FIBRE_TARGET   = 10.0    # g per serving
_CARB_CEILING   = 60.0    # g per serving — above this, low-carb fit hits 0


def _fit_veg(row) -> float:
    """Fresh-produce fit, by weight of PHF ingredients per serving.

    Some SKUs state no weight in their name ("Avocado", "Green Pepper" — common
    in the UK list), which would score a genuinely veg-heavy recipe at zero.
    Those fall back to the item count so they are not unfairly penalised.
    """
    grams = float(row.get("veggie_grams") or 0)
    if grams > 0:
        return _clamp(grams / _VEG_GRAMS_TARGET)
    return _clamp(float(row.get("veggie_count") or 0) / _VEG_COUNT_TARGET)


def _fit_protein(row) -> float:
    return _clamp(float(row.get("protein") or 0) / _PROTEIN_TARGET)


def _fit_fibre(row) -> float:
    return _clamp(float(row.get("fibre") or 0) / _FIBRE_TARGET)


def _fit_wholegrain(row) -> float:
    return 1.0 if re.search(WHOLEGR, _text(row)) else 0.0


def _fit_low_carb(row) -> float:
    return _clamp(1 - float(row.get("carbs") or 0) / _CARB_CEILING)


def _fit_diet(diet_key: str):
    """Reuse an existing framework's scorer as the fit metric for a goal."""
    def _fn(row) -> float:
        try:
            return _clamp(SCORE_FN[diet_key](row, DIET_WEIGHTS[diet_key]) / 100.0)
        except Exception:
            return 0.0
    return _fn


# goal key → per-recipe fit function. Keys match config.HEALTH_GOALS.
GOAL_FIT = {
    "more_veg":       _fit_veg,
    "kids_veg":       _fit_veg,
    "health_con":     _fit_diet("who"),
    "sports_protein": _fit_protein,
    "wholegrain":     _fit_wholegrain,
    "gut_health":     _fit_fibre,
    "low_carb":       _fit_low_carb,
    "longevity":      _fit_diet("blue_zone"),
}

# Goals that imply a diet framework — surfaced as a suggestion in the UI.
GOAL_SUGGESTS_DIET = {
    "health_con": "who",
    "longevity":  "blue_zone",
}

# ── Nutrition preferences (question 3) ────────────────────────────────────────
# Unranked, unlike goals — all selected preferences carry equal weight.

_KCAL_COMFORT = 450.0   # kcal per serving scoring full marks
_KCAL_RANGE   = 350.0   # kcal above comfort before fit hits 0
_SALT_CEILING = 2.0     # g per serving
_SUGAR_CEILING = 15.0   # g per serving
_FAT_CEILING  = 25.0    # g per serving
_SFAT_CEILING = 7.0     # g per serving — matches the sat-fat chip reference


def _fit_calorie(row) -> float:
    kcal = float(row.get("calories") or 0)
    return _clamp(1 - max(0.0, kcal - _KCAL_COMFORT) / _KCAL_RANGE)


def _fit_low_salt(row) -> float:
    return _clamp(1 - float(row.get("salt") or 0) / _SALT_CEILING)


def _fit_low_sugar(row) -> float:
    return _clamp(1 - float(row.get("sugars") or 0) / _SUGAR_CEILING)


def _fit_low_fat(row) -> float:
    return _clamp(1 - float(row.get("fat") or 0) / _FAT_CEILING)


def _fit_chol(row) -> float:
    # No cholesterol column in the nutrition table — saturated fat is the
    # standard dietary proxy, so cholesterol-friendly scores on low sat. fat.
    return _clamp(1 - float(row.get("sat_fat") or 0) / _SFAT_CEILING)


PREF_FIT = {
    "calorie_conscious": _fit_calorie,
    "high_fibre":        _fit_fibre,
    "high_protein":      _fit_protein,
    "low_carb_pref":     _fit_low_carb,
    "low_salt":          _fit_low_salt,
    "low_sugar":         _fit_low_sugar,
    "low_fat":           _fit_low_fat,
    "chol_friendly":     _fit_chol,
}


def pref_fit(df: pd.DataFrame, pref_keys) -> pd.Series:
    """Equal-weighted fit across the selected nutrition preferences."""
    fns = [PREF_FIT[p] for p in (pref_keys or []) if p in PREF_FIT]
    if not fns:
        return pd.Series([0.0] * len(df), index=df.index)
    return df.apply(lambda r: sum(f(r) for f in fns) / len(fns), axis=1)


# Priority weights: 1st goal 50 %, 2nd 30 %, 3rd 20 %.
RANK_WEIGHTS = [0.50, 0.30, 0.20]


def rank_weights(n: int) -> list:
    """Priority weights for n ranked goals, renormalised to sum to 1.

    Picking fewer than 3 goals keeps the same relative emphasis:
    two goals → 62.5 / 37.5, one goal → 100.
    """
    if n <= 0:
        return []
    used = RANK_WEIGHTS[:n]
    total = sum(used)
    return [w / total for w in used]


def goal_fit(df: pd.DataFrame, goal_keys) -> pd.Series:
    """Priority-weighted fit across the ranked goals, as a Series in [0, 1].

    goal_keys must be in priority order — first is the 50 % goal.
    """
    fns = [GOAL_FIT[g] for g in (goal_keys or []) if g in GOAL_FIT]
    if not fns:
        return pd.Series([0.0] * len(df), index=df.index)
    ws = rank_weights(len(fns))
    return df.apply(lambda r: sum(w * f(r) for w, f in zip(ws, fns)), axis=1)


# ── Framework recommendation ──────────────────────────────────────────────────
# How well each framework serves each answer, 0-1. Explicit rather than derived
# from DIET_WEIGHTS: some answers (low carb) have no weight-key equivalent, and
# a visible table is easier to argue with and tune than an inferred one.

# Order is positional — every tuple below must match it, column for column.
_DIETS = ("who", "mediterranean", "blue_zone", "eat_lancet", "sports", "max_veggies")

GOAL_DIET_AFFINITY = {
    #                  who   medit  blue   eat-l  sport  maxveg
    "more_veg":       (0.70, 0.85, 0.85, 0.90, 0.40, 1.00),
    "kids_veg":       (0.70, 0.80, 0.60, 0.75, 0.40, 1.00),
    "health_con":     (1.00, 0.70, 0.60, 0.60, 0.50, 0.70),
    "sports_protein": (0.60, 0.65, 0.40, 0.50, 1.00, 0.40),
    "wholegrain":     (0.85, 1.00, 0.80, 0.75, 0.55, 0.70),
    "gut_health":     (0.70, 0.80, 1.00, 0.90, 0.50, 0.85),
    "low_carb":       (0.65, 0.55, 0.30, 0.30, 0.70, 0.45),
    "longevity":      (0.65, 0.90, 1.00, 0.85, 0.40, 0.80),
}

PREF_DIET_AFFINITY = {
    #                     who   medit  blue   eat-l  sport  maxveg
    "calorie_conscious": (0.80, 0.60, 0.95, 0.85, 0.45, 0.75),
    "high_fibre":        (0.75, 0.80, 1.00, 0.90, 0.50, 0.90),
    "high_protein":      (0.60, 0.65, 0.40, 0.50, 1.00, 0.40),
    "low_carb_pref":     (0.65, 0.55, 0.30, 0.30, 0.70, 0.45),
    "low_salt":          (1.00, 0.70, 0.85, 0.55, 0.45, 0.70),
    "low_sugar":         (1.00, 0.65, 0.90, 0.60, 0.50, 0.70),
    "low_fat":           (0.85, 0.45, 0.75, 0.80, 0.50, 0.75),
    "chol_friendly":     (0.85, 0.90, 0.90, 0.90, 0.45, 0.80),
}


# ── Rules driven by the #1 priority goal ──────────────────────────────────────
# The top-ranked goal (the 50 % one) can override the affinity scoring outright.

GOAL1_FORCED_DIET = {
    "more_veg":       "max_veggies",
    "kids_veg":       "max_veggies",
    "health_con":     "who",
    "sports_protein": "sports",
    "longevity":      "blue_zone",
}

# Top goal here → fibre drives the ranking, whichever framework is in use
GOAL1_FIBRE_FIRST = {"wholegrain", "gut_health"}
FIBRE_FIRST_BLEND = 0.45   # replaces GOAL_BLEND so fibre genuinely leads

# Top goal here → recipes above the limit are removed from the pool entirely
GOAL1_MAX_CARBS = {"low_carb": 50.0}


def first_goal(goal_keys):
    """The #1 priority goal, or None."""
    goals = [g for g in (goal_keys or []) if g in GOAL_FIT]
    return goals[0] if goals else None


def forced_diet(goal_keys) -> str | None:
    """Framework mandated by the #1 goal, if any."""
    return GOAL1_FORCED_DIET.get(first_goal(goal_keys))


def carb_limit(goal_keys) -> float | None:
    """Hard carb ceiling (g per serving) mandated by the #1 goal, if any."""
    return GOAL1_MAX_CARBS.get(first_goal(goal_keys))


def apply_goal_filters(df: pd.DataFrame, goal_keys=None):
    """Drop recipes the #1 goal excludes outright.

    Returns (filtered_df, note) — note describes what was removed, or None.
    Never returns an empty frame when the input was non-empty: if nothing
    clears the bar, the original pool comes back with an explanatory note so
    the page shows the closest options rather than nothing at all.
    """
    limit = carb_limit(goal_keys)
    if df.empty or limit is None or "carbs" not in df.columns:
        return df, None

    carbs = pd.to_numeric(df["carbs"], errors="coerce")
    keep = df[carbs < limit]
    dropped = len(df) - len(keep)
    if keep.empty:
        return df, (f"No recipe this week is under {limit:.0f} g carbs — "
                    f"showing the full menu ranked by your other answers instead.")
    return keep.reset_index(drop=True), (
        f"Low-carb filter: showing only recipes under {limit:.0f} g carbs "
        f"({len(keep)} of {len(df)} recipes; {dropped} excluded)."
    )


def recommend_diets(goal_keys=None, pref_keys=None) -> list:
    """Rank the frameworks against the questionnaire answers.

    Goals carry their 50/30/20 priority weighting; preferences are equal-weighted
    and count for half as much as goals, since the goals question is the one the
    user explicitly ranked.

    Returns [(diet_key, score 0-1), ...] best first — empty if nothing was answered.
    """
    goals = [g for g in (goal_keys or []) if g in GOAL_DIET_AFFINITY]
    prefs = [p for p in (pref_keys or []) if p in PREF_DIET_AFFINITY]
    if not goals and not prefs:
        return []

    # A #1 goal with a mandated framework wins outright — it heads the list at
    # 100 %, with the affinity ranking filling in behind it.
    forced = forced_diet(goal_keys)

    totals = {d: 0.0 for d in _DIETS}
    weight_used = 0.0

    if goals:
        for w, g in zip(rank_weights(len(goals)), goals):
            for d, a in zip(_DIETS, GOAL_DIET_AFFINITY[g]):
                totals[d] += w * a
        weight_used += 1.0

    if prefs:
        for p in prefs:
            for d, a in zip(_DIETS, PREF_DIET_AFFINITY[p]):
                totals[d] += 0.5 * a / len(prefs)
        weight_used += 0.5

    ranked = sorted(((d, totals[d] / weight_used) for d in _DIETS),
                    key=lambda kv: kv[1], reverse=True)
    if forced:
        ranked = [(forced, 1.0)] + [(d, s) for d, s in ranked if d != forced]
    return ranked


def recommendation_reason(diet_key: str, goal_keys=None) -> str:
    """The answered goal that most supports this framework — the 'why'."""
    goals = [g for g in (goal_keys or []) if g in GOAL_DIET_AFFINITY]
    if not goals:
        return ""
    idx = _DIETS.index(diet_key)
    best = max(goals, key=lambda g: GOAL_DIET_AFFINITY[g][idx])
    return best


def blend(df: pd.DataFrame, goal_keys=None, pref_keys=None,
          blend_weight: float = GOAL_BLEND) -> pd.DataFrame:
    """Blend goal + preference fit into the raw 0-100 'score' column.

    goal_keys must be in priority order (50/30/20); pref_keys are equal-weighted.
    When both are answered they contribute equally to the personalised half.

    Adds 'goal_fit', 'pref_fit' and 'fit' columns (all 0-100) so the UI can
    show why a recipe ranked where it did. No-op when nothing is selected.
    """
    goals = [g for g in (goal_keys or []) if g in GOAL_FIT]
    prefs = [p for p in (pref_keys or []) if p in PREF_FIT]
    if df.empty or (not goals and not prefs):
        return df

    out = df.copy()
    parts = []          # (series, weight)
    if goals:
        g = goal_fit(out, goals)
        out["goal_fit"] = (g * 100).round(1)
        parts.append((g, 1.0))
    if prefs:
        p = pref_fit(out, prefs)
        out["pref_fit"] = (p * 100).round(1)
        parts.append((p, 1.0))

    # #1 goal is wholegrain or gut health → fibre leads the ranking outright
    if first_goal(goals) in GOAL1_FIBRE_FIRST:
        blend_weight = FIBRE_FIRST_BLEND
        f = out.apply(_fit_fibre, axis=1)
        out["fibre_fit"] = (f * 100).round(1)
        parts.append((f, 1.5))

    total_w = sum(w for _, w in parts)
    fit = sum(s * w for s, w in parts) / total_w
    out["fit"] = (fit * 100).round(1)
    out["score"] = (out["score"] * (1 - blend_weight) + fit * 100 * blend_weight).round(1)
    return out
