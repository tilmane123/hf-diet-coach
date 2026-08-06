MARKETS = {
    "Germany":              {"market": "dach",    "region_code": "deat", "locale": "de-DE", "segment": "DE"},
    "Netherlands":          {"market": "benelux", "region_code": "nl",   "locale": "nl-NL", "segment": "NL"},
    "United Kingdom":       {"market": "gb",      "region_code": "uk",   "locale": "en-GB", "segment": "GR"},
    "France":               {"market": "fr",      "region_code": "fr",   "locale": "fr-FR", "segment": "FR"},
    "Nordics":              {"market": "dkse",    "region_code": "se",   "locale": "sv-SE", "segment": "SE"},
}

DIETS = {
    "💚 Health conscious choices":             "who",
    "🥦 Maximized vegetables":                 "max_veggies",
    "💪 Improve Sports Performance":           "sports",
    "🫒 Mediterranean Diet":                   "mediterranean",
    "💙 Blue Zone / Longevity Diet":           "blue_zone",
    "🌱 EAT-Lancet — Planetary Health":        "eat_lancet",
}

# ── Pre-section questionnaire ─────────────────────────────────────────────────
# Shown before any results on the Recipe Finder page. Answers feed goals.py,
# which blends a priority-weighted "goal fit" into the diet score.
# Order matters: it is the order shown, and the keys are used in goals.GOAL_FIT.

HEALTH_GOALS = [
    ("more_veg",       "I want to eat more vegetables"),
    ("kids_veg",       "I want my kids to discover more vegetables and more vegetable variety"),
    ("health_con",     "I want to eat health-conscious (WHO / national guidelines)"),
    ("sports_protein", "I want to improve my sports performance and protein intake"),
    ("wholegrain",     "I want to eat more whole grains"),
    ("gut_health",     "I want to improve my gut health"),
    ("low_carb",       "I want to minimize carbohydrates"),
    ("longevity",      "I want to increase longevity"),
]

NUTRITION_PREFS = [
    ("calorie_conscious", "Calorie conscious"),
    ("high_fibre",        "High fibre"),
    ("high_protein",      "High protein"),
    ("low_carb_pref",     "Low carbohydrate"),
    ("low_salt",          "Low salt"),
    ("low_sugar",         "Low sugar"),
    ("low_fat",           "Low fat"),
    ("chol_friendly",     "Cholesterol friendly"),
]

MAX_GOALS = 3
MAX_PREFS = 3

DIET_DESCRIPTIONS = {
    "sports": "Let's build that strength together and fuel your body with more energy and protein.",
    "max_veggies": "Looking for a way to increase daily vegetables intake for yourself or your kids? With these recipes that will make it easy!",
    "eat_lancet": "The EAT-Lancet planetary health diet. Strongly plant-forward, strict on saturated fat, high fibre, minimal red meat. Designed for both human and planetary health.",
    "who": "More balanced eating with lots of vegetables, more wholegrains and less salt.",
    "mediterranean": "Traditional Mediterranean eating pattern. Rich in olive oil, vegetables, legumes, whole grains and fish. Moderate healthy fats, low processed foods.",
    "blue_zone": "Inspired by Blue Zone and Longevity Diet research (Buettner & Longo). Emphasises legumes, plant proteins, high fibre, low calories and very low sugar & salt — the dietary pattern of the world's longest-lived populations.",
}

DIET_COLORS = {
    "sports":        "#1F4E79",
    "max_veggies":   "#5C8A0F",
    "eat_lancet":    "#375623",
    "who":           "#2E7D32",
    "mediterranean": "#9C2793",
    "blue_zone":     "#005B8E",
}

# ── CPS tag targeting ─────────────────────────────────────────────────────────
# Substrings matched (case-insensitively) against the recipe's tags,
# recipe_label and target_preferences from public_edw_base_grain_live.recipe.
# A recipe matching primary tags is pushed up the ranking; secondary tags are
# a softer nudge. Tags are market-specific — see the coverage note in CLAUDE.md.
DIET_TAGS = {
    "who": {
        "primary": ["high-protein", "high protein", "calorie smart", "calorie-smart",
                    "mediterranean", "glp-1", "glp1", "nutritious", "conscious-choice",
                    "health conscious choice", "health-conscious", "lean-green",
                    "lean and green", "balanced"],
        "secondary": ["source-of-fibre", "high-fiber", "healthy-grain", "nutri-score-a",
                      "nutri-score-b", "healthy"],
    },
    # Note: match specific tag names only. A bare "protein" would also catch
    # swap-protein / grocery-proteins / sides-proteins, which are ingredient
    # categories, not high-protein claims.
    "sports": {
        "primary": ["high-protein", "high protein", "highprotein",
                    "double-protein", "extra-protein", "premiumprotein",
                    "50g-plus-protein", "over-30g-protein", "high value protein",
                    "super high ptn", "high ptn"],
        "secondary": ["fitfun", "keto", "low-carb", "lower-carb"],
    },
    "max_veggies": {
        "primary": ["extra-vegetables", "more-than-300g-vegetables", "vegetable",
                    "veggie", "vegetarian", "vegan"],
        "secondary": ["family-friendly", "familyfriendly", "family", "kids-fave",
                      "kidschoice", "kids-classic", "cooking-for-kids"],
    },
}

# ── Scoring parameters ────────────────────────────────────────────────────────
# These drive every scoring function in scoring.py.
# Edit here (or override via the app's sidebar sliders) to tune rankings.
#
# Criterion weights:  w_* keys — relative importance, auto-normalised to sum=1
# Thresholds:         _target / _max / _pct keys — nutritional reference values
# Protein multipliers: prot_* keys — score per protein source type (0=bad, 1=best)

# ── Group-level rules ─────────────────────────────────────────────────────────
# Applied after individual scoring to ensure the Top 5 and Runner-up 5
# comply with overall dietary recommendations as a group.
# max_red_meat: max red meat recipes allowed per 5-recipe group
# min_fibre_avg: minimum average fibre (g) across the group

DIET_GROUP_RULES = {
    "sports":        {"max_red_meat": 2, "min_fibre_avg": 5.0},
    "max_veggies":   {"max_red_meat": 1, "min_fibre_avg": 7.0},
    "eat_lancet":    {"max_red_meat": 0, "min_fibre_avg": 7.0},
    "who":           {"max_red_meat": 1, "min_fibre_avg": 6.0},
    "mediterranean": {"max_red_meat": 1, "min_fibre_avg": 6.0},
    "blue_zone":     {"max_red_meat": 0, "min_fibre_avg": 8.0},
}

DIET_WEIGHTS = {
    # Improve Sports Performance — protein grams lead, with enough energy to
    # train on. Deliberately unlike the old DGE balance this replaced: red meat
    # is a fine protein source here, so there is no red_meat_cap.
    "sports": {
        # --- Criterion weights (adjust relative importance) ---
        "w_prot":    0.40,
        "w_kcal":    0.20,
        "w_fibre":   0.15,
        "w_sfat":    0.15,
        "w_salt":    0.10,
        # --- Nutritional thresholds ---
        "protein_target_g": 30.0,   # g per serving for full protein marks
        "kcal_target":     650.0,   # a training dinner, not a light one
        "kcal_range":      350.0,
        "fibre_target_g":    8.0,
        "sfat_max_pct":     0.12,
        "salt_max_g":        2.5,
        # --- Protein source multipliers (0.0 = worst, 1.0 = best) ---
        "prot_poultry":  1.00,
        "prot_fish":     0.95,
        "prot_other":    0.75,
        "prot_plant":    0.70,
        "prot_red_meat": 0.65,
    },
    # Maximized vegetables — driven by grams of PHF produce per serving
    "max_veggies": {
        "w_veg":    0.45,
        "w_fibre":  0.20,
        "w_prot":   0.15,
        "w_kcal":   0.10,
        "w_sfat":   0.10,
        "veg_target_g":   300.0,   # g of fresh produce per serving for full marks
        "fibre_target_g":  10.0,
        "kcal_target":    550.0,
        "kcal_range":     350.0,
        "sfat_max_pct":    0.10,
        "prot_plant":    1.00,
        "prot_fish":     0.80,
        "prot_poultry":  0.70,
        "prot_other":    0.60,
        "prot_red_meat": 0.35,
        "red_meat_cap":  45,
    },
    "eat_lancet": {
        "w_prot":  0.35,
        "w_fibre": 0.30,
        "w_sfat":  0.20,
        "w_kcal":  0.15,
        "fibre_target_g":  10.0,
        "sfat_max_pct":    0.07,   # stricter than DGE
        "kcal_target":    550.0,   # ideal per-serving kcal
        "kcal_range":     350.0,   # ± range around target before full penalty
        "prot_plant":    1.00,
        "prot_fish":     0.80,
        "prot_poultry":  0.50,
        "prot_other":    0.40,
        "prot_red_meat": 0.05,
        "red_meat_cap":  25,     # EAT-Lancet: red meat capped at 25/100 regardless of other nutrients
    },
    "who": {
        "w_salt":  0.30,
        "w_sugar": 0.25,
        "w_sfat":  0.20,
        "w_fibre": 0.15,
        "w_prot":  0.10,
        "salt_max_g":     1.25,   # <5 g/day → ~1.25 g per main meal
        "sugar_max_pct":  0.05,   # half of the 10% guideline (conservative)
        "sfat_max_pct":   0.10,
        "fibre_target_g": 10.0,
        "prot_fish":     1.0,
        "prot_plant":    1.0,
        "prot_poultry":  0.7,
        "prot_other":    0.5,
        "prot_red_meat": 0.2,
        "red_meat_cap":  30,     # WHO: red meat capped at 30/100
    },
    "mediterranean": {
        "w_fish":   0.20,
        "w_prot":   0.15,   # protein quality (fish/plant >> poultry >> red meat)
        "w_fibre":  0.15,
        "w_legume": 0.15,
        "w_sfat":   0.10,
        "w_salt":   0.10,
        "w_red":    0.10,
        "w_grain":  0.05,
        "fibre_target_g": 9.0,
        "sfat_max_pct":   0.10,
        "salt_max_g":     2.0,
        "red_meat_cap":   20,    # Mediterranean: red meat hard-capped at 20/100
        # --- Protein source multipliers ---
        "prot_fish":     1.00,
        "prot_plant":    0.90,
        "prot_poultry":  0.45,   # poultry tolerated but not preferred
        "prot_other":    0.35,
        "prot_red_meat": 0.05,
    },
    "blue_zone": {
        "w_prot":   0.25,
        "w_fibre":  0.20,
        "w_legume": 0.15,
        "w_sugar":  0.15,
        "w_kcal":   0.15,
        "w_salt":   0.10,
        "fibre_target_g": 10.0,
        "sugar_max_pct":  0.05,
        "salt_max_g":     1.5,
        "kcal_light_threshold": 400,  # kcal below this → full kcal score
        "kcal_range":           400,  # kcal range before full penalty
        "prot_plant":    1.00,
        "prot_fish":     0.75,
        "prot_poultry":  0.45,   # poultry > other (fixed ordering)
        "prot_other":    0.30,
        "prot_red_meat": 0.05,
        "red_meat_cap":  20,     # Blue Zone: red meat hard-capped at 20/100
    },
}
