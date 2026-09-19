"""
Alustaa normalization.db-tietokannan taulut, jos niitä ei vielä ole.

Tämä tiedosto on tarkoituksella versionhallinnassa (toisin kuin alkuperäinen
kehitysaikainen alustus), jotta uusi ympäristö voidaan ottaa käyttöön ilman
tauluja kuvaavan SQL:n muistelua koodin INSERT/SELECT-lauseista.

CREATE TABLE IF NOT EXISTS -muoto tekee ajamisesta turvallista joka
käynnistyksellä, myös silloin kun tietokanta on jo olemassa.
"""

import os
import sqlite3

DB_PATH = "/app/data/normalization.db"

SCHEMA = """
-- Muuttaa reseptin raa'an ainesosatekstin kanoniseksi termiksi
-- (normalizer.py: normalize()).
CREATE TABLE IF NOT EXISTS ingredient_normalization (
    source_term TEXT PRIMARY KEY,
    normalized_term TEXT NOT NULL
);

-- Muistaa käyttäjän vahvistaman Grocy-tuotteen normalisoidulle
-- ainesosanimelle (recipe_importer.py: match_ingredients / save_ingredient_mapping).
CREATE TABLE IF NOT EXISTS ingredient_grocy_mapping (
    normalized_term TEXT PRIMARY KEY,
    grocy_product_id INTEGER NOT NULL,
    confirmed INTEGER NOT NULL DEFAULT 0
);

-- Muistaa käyttäjän vahvistaman Grocy-yksikön jäsentäjän tunnistamalle
-- raa'alle yksikkötekstille (recipe_importer.py: get_unit_mapping / save_unit_mapping).
CREATE TABLE IF NOT EXISTS unit_grocy_mapping (
    source_term TEXT PRIMARY KEY,
    grocy_qu_id INTEGER NOT NULL,
    confirmed INTEGER NOT NULL DEFAULT 0
);
"""


def ensure_schema(db_path: str = DB_PATH) -> None:
    """Luo puuttuvat taulut. Turvallista kutsua useasti / joka käynnistyksellä."""
    os.makedirs(os.path.dirname(db_path), exist_ok=True)

    with sqlite3.connect(db_path) as db:
        db.executescript(SCHEMA)
        db.commit()


if __name__ == "__main__":
    ensure_schema()
    print(f"Tietokantarakenne varmistettu: {DB_PATH}")
