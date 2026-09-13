import sqlite3

DB_PATH = "/app/data/normalization.db"


def normalize(term):
    with sqlite3.connect(DB_PATH) as db:
        row = db.execute(
            """
            SELECT normalized_term
            FROM ingredient_normalization
            WHERE source_term = ?
            """,
            (term,),
        ).fetchone()

    return row[0] if row else term

def normalize_ingredient(ingredient):
    result = ingredient.copy()
    result["name"] = normalize(ingredient["name"])
    return result
