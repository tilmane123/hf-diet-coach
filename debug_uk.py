import sys
sys.path.insert(0, ".")
from db_connector import run_query

print("=== 1. Menu: distinct market/region_code for GB ===")
print(run_query("""
    SELECT DISTINCT market, region_code, COUNT(*) as cnt
    FROM glue.menu_services.menu_global
    WHERE (market = 'gb' OR region_code = 'uk')
      AND item_type = 'recipe' AND status NOT IN ('draft','removed')
      AND recipe_id IS NOT NULL
    GROUP BY market, region_code
""").to_string())

print("\n=== 2. Translations: distinct locales for market='gb' ===")
print(run_query("""
    SELECT DISTINCT locale, COUNT(*) as cnt
    FROM glue.culinary_services.recipe_editorial_translations_global
    WHERE market = 'gb'
    GROUP BY locale ORDER BY cnt DESC LIMIT 10
""").to_string())

print("\n=== 3. Nutrition: any rows for market='gb'? ===")
print(run_query("""
    SELECT COUNT(*) as cnt
    FROM glue.culinary_services.recipe_segment_nutrition_global
    WHERE market = 'gb'
""").to_string())

print("\n=== 4. Picklist: distinct segment_names for market='gb' ===")
print(run_query("""
    SELECT DISTINCT segment_name, COUNT(*) as cnt
    FROM glue.culinary_services.recipe_procurement_picklist_culinarysku_global
    WHERE market = 'gb'
    GROUP BY segment_name ORDER BY cnt DESC LIMIT 10
""").to_string())
