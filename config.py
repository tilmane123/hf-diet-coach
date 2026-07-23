MARKETS = {
    "Germany":              {"market": "dach",    "region_code": "deat", "locale": "de-DE", "segment": "DE"},
    "Netherlands":          {"market": "benelux", "region_code": "nl",   "locale": "nl-NL", "segment": "NL"},
    "United Kingdom":       {"market": "gb",      "region_code": "uk",   "locale": "en-GB", "segment": "GR"},
    "France":               {"market": "fr",      "region_code": "fr",   "locale": "fr-FR", "segment": "FR"},
    "Scandinavia (DKSE)":   {"market": "dkse",    "region_code": "se",   "locale": "sv-SE", "segment": "SE"},
}

DIETS = {
    "🌍 WHO — World Health Organization":      "who",
    "🫒 Mediterranean Diet":                   "mediterranean",
    "💙 Blue Zone / Longevity Diet":           "blue_zone",
    "🌱 EAT-Lancet — Planetary Health":        "eat_lancet",
    "🇩🇪 DGE — German Dietary Guidelines":    "dge",
}

DIET_DESCRIPTIONS = {
    "dge": "Based on the Deutsche Gesellschaft für Ernährung guidelines. Focuses on balanced macros, adequate fibre (30g/day), low saturated fat, and moderate salt (<6g/day).",
    "eat_lancet": "The EAT-Lancet planetary health diet. Strongly plant-forward, strict on saturated fat, high fibre, minimal red meat. Designed for both human and planetary health.",
    "who": "WHO Healthy Diet guidelines. Strictest on salt (<5g/day) and free sugars (<10% energy). Encourages diverse protein sources and high vegetable intake.",
    "mediterranean": "Traditional Mediterranean eating pattern. Rich in olive oil, vegetables, legumes, whole grains and fish. Moderate healthy fats, low processed foods.",
    "blue_zone": "Inspired by Blue Zone and Longevity Diet research (Buettner & Longo). Emphasises legumes, plant proteins, high fibre, low calories and very low sugar & salt — the dietary pattern of the world's longest-lived populations.",
}

DIET_COLORS = {
    "dge":           "#1F4E79",
    "eat_lancet":    "#375623",
    "who":           "#833C00",
    "mediterranean": "#9C2793",
    "blue_zone":     "#005B8E",
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
    "dge":           {"max_red_meat": 1, "min_fibre_avg": 5.0},
    "eat_lancet":    {"max_red_meat": 0, "min_fibre_avg": 7.0},
    "who":           {"max_red_meat": 1, "min_fibre_avg": 6.0},
    "mediterranean": {"max_red_meat": 1, "min_fibre_avg": 6.0},
    "blue_zone":     {"max_red_meat": 0, "min_fibre_avg": 8.0},
}

DIET_WEIGHTS = {
    "dge": {
        # --- Criterion weights (adjust relative importance) ---
        "w_fibre":   0.30,
        "w_sfat":    0.25,
        "w_salt":    0.20,
        "w_sugar":   0.15,
        "w_prot":    0.10,
        # --- Nutritional thresholds ---
        "fibre_target_g": 10.0,   # g per serving to score full points
        "sfat_max_pct":   0.10,   # saturated fat as fraction of kcal (10 % → score 0)
        "salt_max_g":      2.5,   # g per serving (≈ 6 g/day split 2 meals + snack)
        "sugar_max_pct":  0.10,   # free sugars as fraction of kcal
        # --- Protein source multipliers (0.0 = worst, 1.0 = best) ---
        "prot_fish":     1.0,
        "prot_plant":    0.9,
        "prot_poultry":  0.7,
        "prot_other":    0.5,
        "prot_red_meat": 0.2,
        "red_meat_cap":  40,     # DGE: red meat capped at 40/100 regardless of other nutrients
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
