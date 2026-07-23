import sys
sys.path.insert(0, ".")
from db_connector import run_query

print("=== AU picklist segment_names ===")
r = run_query("""
    SELECT DISTINCT segment_name, COUNT(*) as cnt
    FROM glue.culinary_services.recipe_procurement_picklist_culinarysku_global
    WHERE market = 'au'
    GROUP BY segment_name ORDER BY cnt DESC LIMIT 10
""")
print(r.to_string())

print("\n=== AU translations locales ===")
r2 = run_query("""
    SELECT DISTINCT locale, COUNT(*) as cnt
    FROM glue.culinary_services.recipe_editorial_translations_global
    WHERE market = 'au'
    GROUP BY locale ORDER BY cnt DESC LIMIT 5
""")
print(r2.to_string())
