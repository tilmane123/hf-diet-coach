# HF Diet Coach

A Streamlit app that scores and ranks HelloFresh weekly menus against 5 evidence-based dietary frameworks, helping identify which recipes best fit each diet for any market and week.

**Live app:** https://gifomvscsvk9hek6pnqhxa.streamlit.app

---

## What it does

1. Select a **market** (Germany, UK, Netherlands, France, Scandinavia), **diet framework**, and **week**
2. Click **Find best recipes** — the app fetches the full weekly menu from Databricks, scores every recipe nutritionally, and enforces group-level dietary rules
3. Displays a **Top 5** (best fit) and **Runner-up 5** with:
   - Colour-coded nutrient chips (protein, fibre, sat. fat, fresh produce count)
   - A weekly diet score card with progress bars
   - Recipe images, difficulty, cooking time, and ingredients

---

## Diet frameworks

| Framework | Focus |
|---|---|
| 🌍 WHO | Strictest on salt and free sugars |
| 🫒 Mediterranean | Fish, legumes, olive oil, whole grains |
| 💙 Blue Zone | Zero red meat, high fibre, longevity diet |
| 🌱 EAT-Lancet | Planetary health — plant-forward, minimal red meat |
| 🇩🇪 DGE | German national dietary guidelines |

All scoring parameters (criterion weights, nutritional thresholds, protein multipliers) are visible and editable in the **Diet Settings** page for side-by-side comparison across all 5 diets.

---

## Local setup

### Prerequisites
- Python 3.10+
- Access to the HelloFresh Databricks workspace

### Install

```bash
git clone https://github.com/tilmane123/hf-diet-coach.git
cd hf-diet-coach
pip install -r requirements.txt
```

### Configure Databricks credentials

Create a `.env` file in the **parent directory** of `hf_diet_coach/` (i.e. `databricks_analytics/.env`):

```
DATABRICKS_HOST=https://your-workspace.azuredatabricks.net
DATABRICKS_HTTP_PATH=/sql/1.0/warehouses/your-warehouse-id
DATABRICKS_TOKEN=dapi...
```

### Run

```bash
streamlit run app.py
```

---

## Project structure

```
hf_diet_coach/
├── app.py                    # Entry point — version tracking + cache management
├── app_pages/
│   ├── main.py               # Recipe Finder — all rendering and scoring logic
│   └── settings.py           # Diet Settings — side-by-side parameter editor
├── config.py                 # All diet parameters, market codes, colours
├── scoring.py                # Nutritional scoring + protein type detection
├── menu_data.py              # Data fetching, deduplication, variety enforcement
├── db_connector.py           # Databricks connection (session-cached)
├── settings_store.py         # User settings persistence
├── CLAUDE.md                 # Full technical context for Claude Code sessions
└── requirements.txt
```

---

## Data sources (Databricks)

The app combines two Databricks schema families:

**`glue.culinary_services` / `glue.menu_services`** — core menu and recipe data  
**`glue.public_edw_base_grain_live`** — enriched recipe data (structured protein type, fallback images)

Ingredient categorisation uses the SKU `code` prefix from the procurement picklist:
`PHF` = Produce, Herbs & Fruits — used to count fresh ingredient variety per recipe.

---

## Deployment (Streamlit Cloud)

The app deploys automatically from the `main` branch of this repo.

> **Note:** the local working branch is `master`. Always push with:
> ```bash
> git push origin master:main
> ```

Databricks credentials are stored as Streamlit secrets (Settings → Secrets in the Streamlit Cloud dashboard). A collaborator needs to be added in both GitHub (Settings → Collaborators) and Streamlit Cloud (app Settings → Sharing) to manage deployments.

---

## Versioning

The version string lives in `app.py` (`_VERSION`) and `app_pages/main.py` (sidebar caption).
Bump it on every meaningful change — it triggers a Streamlit cache clear on first load.

| Version | What changed |
|---|---|
| v0.27 | Cached Databricks connection; enrichment folded into one SQL query (speed) |
| v0.26 | Veggie count from PHF SKU codes — no more word lists |
| v0.25 | Weekly score card above recipe cards; colour-coded nutrient chips |
| v0.24 | Relaxed runner-up similarity threshold (0.40) to fix short UK selections |
| v0.23 | Migrated to `public_edw_base_grain_live` for protein type and image fallback |
| v0.22 | Side-by-side Diet Settings; score rescaling to 72–97 range; variety dedup |

---

## Key design decisions

**Protein detection priority** — the recipe title is checked before ingredients. This prevents side vegetables (e.g. green beans in a beef dish) from overriding the primary protein classification. Structured `primary_protein` from `recipe_contents` is used when available.

**Variety enforcement** — `diverse_top_n()` enforces two layers before splitting Top 5 / Runner-up: a flavor-keyword cap (max 1 chimichurri, 1 pesto, etc.) and a base-title fuzzy-similarity check. Runner-up uses a relaxed threshold (0.40 vs. 0.55) to avoid empty sections on small markets.

**Score range** — raw scores are min-max rescaled to [72, 97] per week. This means the best recipe always appears near 97 and relative gaps are preserved, but absolute values don't drift when a week has unusually high or low baseline quality.

**Red = 2× limit** — nutrient chip colours use red only when a value exceeds twice the recommended limit. This keeps most recipes showing green or amber and avoids alarm fatigue.
