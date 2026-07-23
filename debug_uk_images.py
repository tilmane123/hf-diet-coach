import sys
sys.path.insert(0, ".")
from db_connector import run_query

# Grab a sample of UK recipe image_url and unique_recipe_code values
print("=== Sample image_url + unique_recipe_code for GB market ===")
r = run_query("""
    SELECT id, unique_recipe_code, image_url
    FROM glue.culinary_services.recipe_global
    WHERE market = 'gb'
      AND id IS NOT NULL
    LIMIT 20
""")
print(r.to_string())

print("\n=== Same recipes via translations join (no market filter on recipe_global) ===")
r2 = run_query("""
    SELECT t.recipe_id, t.title, r.image_url, r.unique_recipe_code, r.market as rg_market
    FROM glue.culinary_services.recipe_editorial_translations_global t
    LEFT JOIN glue.culinary_services.recipe_global r ON t.recipe_id = r.id
    WHERE t.locale = 'en-GB' AND t.market = 'gb'
    LIMIT 20
""")
print(r2.to_string())
