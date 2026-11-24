import sqlite3
import os


def get_db_path():
    """Hae tietokannan polku ympäristömuuttujasta."""
    return os.environ.get("DB_PATH", "/app/data/normalization.db")


def normalize(term):
    db_path = get_db_path()
    with sqlite3.connect(db_path) as db:
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
