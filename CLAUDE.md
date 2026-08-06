# HF Diet Coach — Claude Code Project Context

This file is loaded automatically by Claude Code at the start of every session.
It gives full project context so you can pick up work without re-explaining the background.

---

## What this app does

A Streamlit app that scores and ranks HelloFresh weekly menus against 5 dietary frameworks
(Health Conscious, Mediterranean, Blue Zone, EAT-Lancet, DGE). For a selected market + week, it fetches
all recipes, scores each one, enforces group-level dietary rules, and renders a Top 5 +
Runner-up 5 with nutritional detail cards.

**Live app:** https://gifomvscsvk9hek6pnqhxa.streamlit.app
**GitHub:** https://github.com/tilmane123/hf-diet-coach
**Current version:** v0.27

---

## File structure

```
hf_diet_coach/
├── app.py                    # Streamlit entry point, version bump + cache clear
├── app_pages/
│   ├── main.py               # Recipe Finder page — all rendering logic lives here
│   └── settings.py           # Diet Settings page — side-by-side parameter editor
├── config.py                 # MARKETS, DIETS, DIET_WEIGHTS, DIET_GROUP_RULES, DIET_COLORS
├── scoring.py                # All scoring functions + protein detection
├── menu_data.py              # fetch_menu(), diverse_top_n(), dedup helpers
├── db_connector.py           # Databricks connection (cached), run_query(), run_queries()
└── settings_store.py         # User settings persistence (JSON file, session-scoped)
```

Diagnostic / one-off scripts (safe to ignore or delete):
`check_code_prefixes.py`, `check_new_sources.py`, `check_picklist_schema.py`,
`check_uk_images.py`, `explore_new_sources.py`, `explore_schema.py`,
`debug_uk.py`, `debug_markets.py`, `debug_uk_images.py`, `debug_au.py`

---

## Databricks data sources

### Primary (old culinary_services tables — used for core data)
| Table | Used for |
|---|---|
| `glue.menu_services.menu_global` | Weekly recipe slot list per market |
| `glue.culinary_services.recipe_editorial_translations_global` | Titles, subtitles |
| `glue.culinary_services.recipe_global` | image_url, unique_recipe_code, difficulty, times |
| `glue.culinary_services.recipe_segment_nutrition_global` | Calories, protein, fat, fibre, salt, etc. |
| `glue.culinary_services.recipe_procurement_picklist_culinarysku_global` | Ingredient list + SKU codes |

### Supplementary (new public_edw_base_grain_live — enrichment via LEFT JOIN in names query)
| Table | Used for |
|---|---|
| `glue.public_edw_base_grain_live.recipe_contents` | `primary_protein`, `sauce_paste` |
| `glue.public_edw_base_grain_live.recipe` | Fallback `image_url` / `internal_image_url` |

**Join key:** `unique_recipe_code` (old tables) ↔ `recipe_code_unique` (new tables)
**Market codes:** old tables use lowercase (`dach`, `gb`); new tables use uppercase (`DACH`, `GB`).
The names query uses `UPPER(market)` in the JOIN conditions.

### Ingredient categorisation (PHF codes)
The picklist `code` column has a 3-letter prefix that categorises each SKU:
- `PHF` = **Produce, Herbs & Fruits** — used to count fresh ingredient variety per recipe
- `PTN` = Protein
- `DAI` = Dairy
- `SPI` = Spices
- `DRY` = Dry goods (pasta, grains)
- `PRO` = Processed / sauces
- `BAK` = Bakery
- `CON` = Convenience

`veggie_count` in the DataFrame = count of distinct `PHF` items per recipe, computed in `fetch_menu()`.

---

## Scoring system (scoring.py)

### Protein detection (`_detect_protein`)
Priority order:
1. `primary_protein` field from `recipe_contents` (structured, e.g. `"Beef-Steak"`) → mapped via `_map_primary_protein()`
2. Title-first regex (RED_MEAT, FISH, POULTRY patterns) — title overrides ingredient text to prevent side-dish false positives (e.g. Buschbohnen in a beef dish should not classify as plant)
3. Full ingredient text regex fallback

Categories: `red_meat`, `fish`, `poultry`, `plant`, `other`

### Score computation (`score_menu`)
Each recipe gets a raw score 0–100 from a weighted sum of nutritional sub-scores.
Weights come from `DIET_WEIGHTS[diet_key]` in `config.py` (overridable via sidebar).
Final scores are rescaled to [72, 97] via min-max normalisation to keep relative gaps
while ensuring the best recipe always appears near 97.

### Group-level rules (`_enforce_group_rules`)
After individual scoring, the top 5 are checked against `DIET_GROUP_RULES`:
- `max_red_meat`: max allowed red-meat recipes in the group. Excess recipes are replaced with the highest-scoring non-red-meat alternative.
- `min_fibre_avg`: if average fibre falls below this, lowest-fibre recipe is swapped out.

### Variety enforcement (`diverse_top_n` in menu_data.py)
Runs on the full scored pool before top5/runner5 split. Two layers:
- **Flavor cap**: no more than 1 recipe per sauce keyword (chimichurri, pesto, etc.) — uses `sauce_paste` field from recipe_contents, falls back to `_FLAVOR_KW` regex
- **Base-title similarity**: no two recipes with SequenceMatcher ratio ≥ threshold
  - Top 5: threshold = 0.55 (strict)
  - Runner-up 5: threshold = 0.40 (relaxed — fixes short selections on small menus like UK)
  - Runner-up also receives `seed_bases` from top 5 so it never duplicates the top selection

---

## Nutrient display (app_pages/main.py)

### Per-card chips (colour-coded traffic light)
| Chip | Reference | Logic |
|---|---|---|
| 💪 Protein | 20g target | green ≥20g, amber ≥10g, red <10g |
| 🌾 Fibre | 8g target | green ≥8g, amber ≥4g, red <4g |
| 🧈 Sat. fat | 7g max | green ≤7g, amber ≤14g, red >14g (2× max) |
| 🥦 Vegetables (PHF) | 200 g/serving | green ≥200g, amber ≥100g, red <100g. Falls back to item count when no SKU states a weight |
| 🔥 Calories | neutral grey | informational only |

Red is reserved for >2× the recommended limit — keeps most recipes showing green/amber.

### Weekly score card
Appears directly below the section header (before recipe cards).
Shows average score + 4 bars (protein, fibre, sat. fat, vegetables) for the group of 5.
Bar colour uses the same `_chip_color()` function as individual cards.

---

## Connection and caching

`db_connector.py` uses `@st.cache_resource` to keep one Databricks connection alive for the
entire Streamlit session. Previously every query opened a fresh connection (~3s overhead each).
On failure, it clears the cache and reconnects once.

`fetch_menu()` is decorated with `@st.cache_data(ttl=3600)` — results are cached for 1 hour
per (market, week, year) combination.

---

## Markets supported

| Display name | market code | locale | Notes |
|---|---|---|---|
| Germany | `dach` | `de-DE` | Primary test market |
| Netherlands | `benelux` | `nl-NL` | |
| United Kingdom | `gb` | `en-GB` | Image fallback from new tables critical here |
| France | `fr` | `fr-FR` | |
| Nordics | `dkse` | `sv-SE` | |

---

## Diet frameworks

| Key | Display name | Strictest constraint |
|---|---|---|
| `who` | Health Conscious recipes | Salt <5g/day, low sugar |
| `mediterranean` | Mediterranean | Olive oil / fish focus, moderate red meat |
| `blue_zone` | Blue Zone | Zero red meat, very high fibre |
| `eat_lancet` | EAT-Lancet | Zero red meat, plant-forward, kcal-aware |
| `dge` | DGE | German guidelines, balanced macros |

---

## Known issues / watch points

- **New table market codes**: `public_edw_base_grain_live` uses uppercase market codes.
  `UPPER('dach') = 'DACH'` ✓ and `UPPER('gb') = 'GB'` ✓ work. `benelux` → `'BENELUX'`
  may not match — verify if Netherlands enrichment (primary_protein, images) is working.
- **PHF veggie count**: counts all PHF SKUs including fruit and herbs. This is intentional
  (PHF = Produce, Herbs & Fruits). Shown as "🥦 Xg vegetables".
- **Runner-up sometimes < 5**: on small markets (UK) with strict diets (EAT-Lancet),
  fewer than 5 diverse recipes may pass all filters. The relaxed 0.40 threshold helps but
  cannot fully compensate for a genuinely small menu pool.
- **Nutrition filter**: `fetch_menu()` drops recipes missing calories, protein, or fibre.
  Some market/segment combos have patchy nutrition data — empty results often traced here.

---

## How to run locally

1. Clone the repo and install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
2. Create a `.env` file in the parent directory (`databricks_analytics/.env`) with:
   ```
   DATABRICKS_HOST=https://your-workspace.azuredatabricks.net
   DATABRICKS_HTTP_PATH=/sql/1.0/warehouses/your-warehouse-id
   DATABRICKS_TOKEN=dapi...
   ```
3. Run:
   ```bash
   streamlit run app.py
   ```

For Streamlit Cloud, these three values are stored as secrets in the app's Settings → Secrets panel.

---

## Deployment

- Streamlit Cloud auto-deploys from the `main` branch of `tilmane123/hf-diet-coach`
- The local repo pushes to `master`; always push with `git push origin master:main`
- Version is tracked in `app.py` (`_VERSION`) and `app_pages/main.py` (caption)
- Bumping the version string triggers a cache clear on first load (`st.cache_data.clear()`)
