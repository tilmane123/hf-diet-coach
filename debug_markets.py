import sys
sys.path.insert(0, ".")
from db_connector import run_query

print("Testing connection...")
try:
    r = run_query("SELECT 1 AS ok")
    print("Connection OK:", r)
except Exception as e:
    print(f"Connection ERROR: {e}")

print("\nFrance menu weeks...")
try:
    r = run_query("""
        SELECT DISTINCT week_number, week_year
        FROM glue.menu_services.menu_global
        WHERE market='fr' AND region_code='fr'
          AND item_type='recipe' AND recipe_id IS NOT NULL
          AND status NOT IN ('draft','removed')
        ORDER BY week_year DESC, week_number DESC
        LIMIT 3
    """)
    print(r)
except Exception as e:
    print(f"ERROR: {e}")
