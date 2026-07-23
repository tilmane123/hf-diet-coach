"""
Schema explorer — run once to find protein/tag fields in Databricks.
Usage: python explore_schema.py
"""

import os, sys
sys.path.insert(0, os.path.dirname(__file__))
from db_connector import run_query

MARKET   = "dach"
LOCALE   = "de-DE"
SAMPLE_WEEK = 32
SAMPLE_YEAR = 2025

def show(title, df):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")
    print(df.to_string(index=False))

# 1. All tables in culinary_services
show("Tables in glue.culinary_services",
    run_query("SHOW TABLES IN glue.culinary_services"))

# 2. All columns in recipe_global (we only use a few currently)
show("Columns in recipe_global",
    run_query("DESCRIBE TABLE glue.culinary_services.recipe_global"))

# 3. All columns in recipe_editorial_translations_global
show("Columns in recipe_editorial_translations_global",
    run_query("DESCRIBE TABLE glue.culinary_services.recipe_editorial_translations_global"))

# 4. Sample dish_type / sub_type values from live menu data
show("Distinct dish_type values (recipe_global, DE market sample)",
    run_query(f"""
        SELECT DISTINCT r.dish_type, COUNT(*) AS n
        FROM glue.culinary_services.recipe_global r
        JOIN glue.menu_services.menu_global m ON r.id = m.recipe_id
        WHERE m.market = '{MARKET}'
          AND m.week_number = {SAMPLE_WEEK}
          AND m.week_year = {SAMPLE_YEAR}
          AND m.item_type = 'recipe'
        GROUP BY r.dish_type
        ORDER BY n DESC
    """))

# 5. Sample sub_type values from menu_global
show("Distinct sub_type values (menu_global, DE W32)",
    run_query(f"""
        SELECT DISTINCT sub_type, COUNT(*) AS n
        FROM glue.menu_services.menu_global
        WHERE market = '{MARKET}'
          AND week_number = {SAMPLE_WEEK}
          AND week_year = {SAMPLE_YEAR}
          AND item_type = 'recipe'
        GROUP BY sub_type
        ORDER BY n DESC
    """))

# 6. Look for any tag / attribute / classification tables
show("All tables in glue schema containing 'tag' or 'attribute' or 'classif'",
    run_query("""
        SELECT table_schema, table_name
        FROM information_schema.tables
        WHERE table_catalog = 'glue'
          AND (LOWER(table_name) LIKE '%tag%'
            OR LOWER(table_name) LIKE '%attrib%'
            OR LOWER(table_name) LIKE '%classif%'
            OR LOWER(table_name) LIKE '%protein%'
            OR LOWER(table_name) LIKE '%label%'
            OR LOWER(table_name) LIKE '%category%')
        ORDER BY table_schema, table_name
    """))

# 7. Spot-check: what does recipe_global actually say for known red-meat recipes
show("Spot-check recipe_global fields for W32 DE recipes (title + dish_type + other fields)",
    run_query(f"""
        SELECT t.title, r.dish_type, r.unique_recipe_code
        FROM glue.culinary_services.recipe_editorial_translations_global t
        JOIN glue.culinary_services.recipe_global r ON t.recipe_id = r.id
        JOIN glue.menu_services.menu_global m ON t.recipe_id = m.recipe_id
        WHERE m.market = '{MARKET}'
          AND m.week_number = {SAMPLE_WEEK}
          AND m.week_year = {SAMPLE_YEAR}
          AND m.item_type = 'recipe'
          AND t.locale = '{LOCALE}'
        LIMIT 30
    """))
