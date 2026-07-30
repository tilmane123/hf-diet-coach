"""
Explorer for glue.public_edw_base_grain_live tables.
Run: python explore_new_sources.py
Checks if these tables can replace / supplement the current culinary_services sources
for better image URLs, faster queries, and richer recipe data.
"""

import os, sys
sys.path.insert(0, os.path.dirname(__file__))
from db_connector import run_query

MARKET   = "dach"
LOCALE   = "de-DE"
WEEK     = 32
YEAR     = 2026

def show(title, df):
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}")
    if df is None or df.empty:
        print("  (no rows)")
    else:
        print(df.to_string(index=False, max_colwidth=80))

# ── 1. Schema of each new table ───────────────────────────────────────────────
for tbl in ["menu", "recipe", "recipe_contents", "recipe_nutrition"]:
    try:
        show(f"SCHEMA: glue.public_edw_base_grain_live.{tbl}",
             run_query(f"DESCRIBE TABLE glue.public_edw_base_grain_live.{tbl}"))
    except Exception as e:
        print(f"\n  ERROR describing {tbl}: {e}")

# ── 2. Sample rows from each table ───────────────────────────────────────────
for tbl in ["menu", "recipe", "recipe_contents", "recipe_nutrition"]:
    try:
        show(f"SAMPLE (5 rows): glue.public_edw_base_grain_live.{tbl}",
             run_query(f"SELECT * FROM glue.public_edw_base_grain_live.{tbl} LIMIT 5"))
    except Exception as e:
        print(f"\n  ERROR sampling {tbl}: {e}")

# ── 3. Check if menu table has market/week columns ───────────────────────────
try:
    show(f"Menu rows for market={MARKET}, week={WEEK}, year={YEAR}",
         run_query(f"""
             SELECT *
             FROM glue.public_edw_base_grain_live.menu
             WHERE LOWER(market) = '{MARKET}'
               AND week_number = {WEEK}
               AND week_year   = {YEAR}
             LIMIT 10
         """))
except Exception as e:
    print(f"\n  ERROR querying menu by market/week: {e}")
    # Try without year column
    try:
        show("Retry without week_year",
             run_query(f"""
                 SELECT *
                 FROM glue.public_edw_base_grain_live.menu
                 WHERE LOWER(market) = '{MARKET}'
                 LIMIT 10
             """))
    except Exception as e2:
        print(f"  Also failed: {e2}")

# ── 4. Check recipe table for image_url column ────────────────────────────────
try:
    show("Recipe table: columns containing 'image'",
         run_query("""
             SELECT column_name, data_type
             FROM information_schema.columns
             WHERE table_catalog = 'glue'
               AND table_schema  = 'public_edw_base_grain_live'
               AND table_name    = 'recipe'
               AND LOWER(column_name) LIKE '%image%'
         """))
except Exception as e:
    print(f"\n  ERROR: {e}")

# ── 5. Join recipe + menu — spot-check image + title for DE W32 ───────────────
try:
    show(f"Join recipe+menu for {MARKET} W{WEEK} {YEAR} — title + image_url",
         run_query(f"""
             SELECT m.recipe_id, r.title, r.image_url
             FROM glue.public_edw_base_grain_live.menu m
             JOIN glue.public_edw_base_grain_live.recipe r
               ON m.recipe_id = r.id
             WHERE LOWER(m.market) = '{MARKET}'
               AND m.week_number = {WEEK}
               AND m.week_year   = {YEAR}
             LIMIT 15
         """))
except Exception as e:
    print(f"\n  ERROR joining recipe+menu: {e}")

# ── 6. Check recipe_nutrition for nutrition columns ───────────────────────────
try:
    show("recipe_nutrition: check for fibre/salt/protein/kcal columns",
         run_query("""
             SELECT column_name, data_type
             FROM information_schema.columns
             WHERE table_catalog = 'glue'
               AND table_schema  = 'public_edw_base_grain_live'
               AND table_name    = 'recipe_nutrition'
             ORDER BY ordinal_position
         """))
except Exception as e:
    print(f"\n  ERROR: {e}")

# ── 7. Check recipe_contents for ingredient data ─────────────────────────────
try:
    show("recipe_contents: columns",
         run_query("""
             SELECT column_name, data_type
             FROM information_schema.columns
             WHERE table_catalog = 'glue'
               AND table_schema  = 'public_edw_base_grain_live'
               AND table_name    = 'recipe_contents'
             ORDER BY ordinal_position
         """))
except Exception as e:
    print(f"\n  ERROR: {e}")

print("\n\nDone. Compare column names above with current sources:")
print("  Current menu:      glue.menu_services.menu_global")
print("  Current recipe:    glue.culinary_services.recipe_global")
print("  Current nutrition: glue.culinary_services.recipe_segment_nutrition_global")
print("  Current picklist:  glue.culinary_services.recipe_procurement_picklist_culinarysku_global")
