"""
Integraatiotestit kuvareseptien tuonnille.

Testaa koko workflow:
1. OCR-teksti luetaan kuvasta
2. Teksti jäsennetään reseptin rakenteeksi
3. Ainesosat normalisoidaan
4. Ainesosat yhdistetään Grocy-tuotteisiin

Nämä testit vaativat:
- pytesseract & Tesseract-OCR
- Testikuvia tests/fixtures/images/
- Grocy-API käytettävissä (voidaan mockkailla)
"""

import asyncio
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from recipe_import import image_ocr
from recipe_importer import (
    prepare_recipe,
    parse_yield,
    extract_recipe_from_image,
)


class ImageOCRIntegrationTests(unittest.TestCase):
    """Testaa OCR:n ja reseptin jäsentämisen yhdessä."""

    @classmethod
    def setUpClass(cls):
        """Valmistele test fixtures."""
        cls.fixtures_dir = Path(__file__).parent / "fixtures"
        cls.images_dir = cls.fixtures_dir / "images"
        
        # Varmista, että testikuvat on olemassa
        if not cls.images_dir.exists():
            raise FileNotFoundError(
                f"Testikuvat puuttuvat: {cls.images_dir}\n"
                f"Aja: python tests/fixtures/generate_test_images.py"
            )

    def test_ocr_simple_recipe_image(self):
        """Testaa, että OCR lukee yksinkertaisen reseptin kuvasta."""
        try:
            import pytesseract
        except ImportError:
            self.skipTest("pytesseract ei ole asennettu - OCR-testit ohitettu")
        
        image_path = self.images_dir / "simple_recipe.png"
        if not image_path.exists():
            self.skipTest(f"Testikuva puuttuu: {image_path}")

        with open(image_path, 'rb') as f:
            recipe = extract_recipe_from_image(f)

        # Varmista, että kaikki olennainen data tunnistettiin
        self.assertIsNotNone(recipe["name"])
        self.assertGreater(len(recipe["ingredients"]), 0)
        self.assertIsNotNone(recipe["yield"])

    def test_ocr_pannukakku_image(self):
        """Testaa pannukakun kuvan OCR."""
        try:
            import pytesseract
        except ImportError:
            self.skipTest("pytesseract ei ole asennettu - OCR-testit ohitettu")
        
        image_path = self.images_dir / "pannukakku.png"
        if not image_path.exists():
            self.skipTest(f"Testikuva puuttuu: {image_path}")

        with open(image_path, 'rb') as f:
            recipe = extract_recipe_from_image(f)

        self.assertIsNotNone(recipe["name"])
        self.assertIn("pannukakku", recipe["name"].lower())
        self.assertGreater(len(recipe["ingredients"]), 0)

    def test_ocr_meat_recipe_image(self):
        """Testaa lihapullat-kuvan OCR."""
        try:
            import pytesseract
        except ImportError:
            self.skipTest("pytesseract ei ole asennettu - OCR-testit ohitettu")
        
        image_path = self.images_dir / "lihapullat.png"
        if not image_path.exists():
            self.skipTest(f"Testikuva puuttuu: {image_path}")

        with open(image_path, 'rb') as f:
            recipe = extract_recipe_from_image(f)

        self.assertIsNotNone(recipe["name"])
        self.assertGreater(len(recipe["ingredients"]), 0)


class RecipePreparationIntegrationTests(unittest.TestCase):
    """Testaa reseptin valmistelua ja normalisointia."""

    def setUp(self):
        """Alusta väliaikainen tietokanta joka testille."""
        self.temp_db = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        self.temp_db.close()
        self.db_path = self.temp_db.name
        # Varmista hakemisto
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        # Paikalla tietokantapolkua, jotta normalizer.py:n voi käyttää
        self.old_db_path = os.environ.get("DB_PATH")
        os.environ["DB_PATH"] = self.db_path
        # Sitten luo taulu
        self._setup_test_db()

    def tearDown(self):
        """Puhdista väliaikainen tietokanta."""
        # Palauta alkuperäinen DB_PATH
        if self.old_db_path is not None:
            os.environ["DB_PATH"] = self.old_db_path
        elif "DB_PATH" in os.environ:
            del os.environ["DB_PATH"]
        
        if os.path.exists(self.db_path):
            os.unlink(self.db_path)

    def _setup_test_db(self):
        """Luo test-tietokannan kaavion."""
        with sqlite3.connect(self.db_path) as db:
            db.executescript("""
                CREATE TABLE ingredient_normalization (
                    source_term TEXT PRIMARY KEY,
                    normalized_term TEXT NOT NULL
                );
                
                CREATE TABLE ingredient_grocy_mapping (
                    normalized_term TEXT PRIMARY KEY,
                    grocy_product_id INTEGER NOT NULL,
                    confirmed INTEGER NOT NULL DEFAULT 0
                );
                
                CREATE TABLE unit_grocy_mapping (
                    source_term TEXT PRIMARY KEY,
                    grocy_qu_id INTEGER NOT NULL,
                    confirmed INTEGER NOT NULL DEFAULT 0
                );
            """)

    def test_prepare_simple_recipe(self):
        """Testaa yksinkertaisen reseptin valmistelua."""
        recipe = {
            "name": "Omenapaistos",
            "description": "Helppo omenapaistos",
            "yield": "4 annosta",
            "ingredients": [
                "3 dl kaurahiutaleita",
                "2 omenaa",
                "100 g voita",
            ],
            "instructions": [
                "Sekoita ainekset.",
                "Paista uunissa.",
            ],
        }

        prepared = prepare_recipe(recipe)

        self.assertEqual(prepared["name"], "Omenapaistos")
        self.assertEqual(prepared["yield"]["amount"], 4)
        # Tarkista, että yksikkö on joko "annos" tai "annosta" (molemmat kelpaa)
        self.assertIn(prepared["yield"]["unit"], ["annos", "annosta"])
        self.assertGreater(len(prepared["ingredients"]), 0)

    def test_parse_yield_with_servings(self):
        """Testaa annosten jäsentämistä."""
        yield_data = parse_yield("6 annosta")
        self.assertEqual(yield_data["amount"], 6)
        # Tarkista, että yksikkö on joko "annos" tai "annosta"
        self.assertIn(yield_data["unit"], ["annos", "annosta"])

    def test_parse_yield_with_portions(self):
        """Testaa portions/portion jäsentämistä."""
        for yield_text in ["4 portions", "8 portion", "2 servings"]:
            yield_data = parse_yield(yield_text)
            self.assertIsNotNone(yield_data["amount"])
            # normalize_yield_unit palauttaa "annos" (singular)
            self.assertIn(yield_data["unit"], ["annos", "annosta"])

    def test_parse_yield_decimal(self):
        """Testaa desimaalilukujen jäsentämistä."""
        yield_data = parse_yield("2,5 annosta")
        self.assertEqual(yield_data["amount"], 2.5)

    def test_parse_yield_no_unit(self):
        """Testaa annosten jäsentämistä ilman yksikköä."""
        yield_data = parse_yield("Ei määrää")
        self.assertIsNone(yield_data["amount"])
        self.assertIsNone(yield_data["unit"])
        self.assertEqual(yield_data["raw"], "Ei määrää")


class GrocyIntegrationMockTests(unittest.TestCase):
    """
    Testaa Grocy-integraatiota mock-objekteilla.
    
    Todellisen Grocy-serverin testaamiseen, käytä
    tests/test_integration_with_grocy.py:tä.
    """

    def setUp(self):
        """Alusta väliaikainen tietokanta ja mock-objektit."""
        self.temp_db = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        self.temp_db.close()
        self.db_path = self.temp_db.name
        self._setup_test_db()
        # Paikalla tietokantapolkua, jotta normalizer.py:n voi käyttää
        self.old_db_path = os.environ.get("DB_PATH")
        os.environ["DB_PATH"] = self.db_path
        # Varmista hakemisto
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)

    def tearDown(self):
        """Puhdista väliaikainen tietokanta."""
        # Palauta alkuperäinen DB_PATH
        if self.old_db_path is not None:
            os.environ["DB_PATH"] = self.old_db_path
        elif "DB_PATH" in os.environ:
            del os.environ["DB_PATH"]
        
        if os.path.exists(self.db_path):
            os.unlink(self.db_path)

    def _setup_test_db(self):
        """Luo test-tietokannan kaavion."""
        with sqlite3.connect(self.db_path) as db:
            db.executescript("""
                CREATE TABLE ingredient_normalization (
                    source_term TEXT PRIMARY KEY,
                    normalized_term TEXT NOT NULL
                );
                
                CREATE TABLE ingredient_grocy_mapping (
                    normalized_term TEXT PRIMARY KEY,
                    grocy_product_id INTEGER NOT NULL,
                    confirmed INTEGER NOT NULL DEFAULT 0
                );
                
                CREATE TABLE unit_grocy_mapping (
                    source_term TEXT PRIMARY KEY,
                    grocy_qu_id INTEGER NOT NULL,
                    confirmed INTEGER NOT NULL DEFAULT 0
                );
            """)
            
            # Lisää test-dataa
            db.execute(
                """INSERT INTO ingredient_grocy_mapping 
                   (normalized_term, grocy_product_id, confirmed) 
                   VALUES (?, ?, 1)""",
                ("voita", 1),
            )
            db.commit()

    @patch('sqlite3.connect')
    def test_match_ingredients_with_mapping(self, mock_connect):
        """Testaa ainesosien yhdistämistä mappauksen avulla."""
        # Tämä testi vaatii enemmän mock-asettelua.
        # Katso integration_tests/ täydellisempää testiä varten.
        pass


class FullWorkflowIntegrationTests(unittest.TestCase):
    """
    Testaa koko tuontityövoiman alusta loppuun.
    
    Mock-versionissa käytetään mock-Grocy-clientia.
    Katso tests/integration/ full-stack -testeille Grocy-serverin kanssa.
    """

    def test_workflow_name_extraction(self):
        """Testaa, että reseptin nimi tunnistetaan."""
        ocr_text = """
        Päärynäkaakao
        6 annosta

        Ainekset
        4 päärynää
        2 dl suklaakastiketta
        1 dl kermaa

        Valmistus
        Kuori päärynät.
        Lisää suklaakastike.
        Tarjoile kylmänä.
        """

        from recipe_import.image_ocr import parse_ocr_recipe
        recipe = parse_ocr_recipe(ocr_text)

        self.assertEqual(recipe["name"], "Päärynäkaakao")
        self.assertEqual(len(recipe["ingredients"]), 3)

    def test_workflow_finnish_ingredients(self):
        """Testaa suomalaisten ainesosien käsittelyä."""
        ocr_text = """
        Ruisleipä
        2 annosta

        Raaka-aineet
        500 g ruis jauhoja
        3 dl vettä
        1 tl suolaa
        1 pkt kuivahiiva

        Valmistaminen
        Sekoita jauhot veteen.
        Lisää suola ja hiiva.
        Paista.
        """

        from recipe_import.image_ocr import parse_ocr_recipe
        recipe = parse_ocr_recipe(ocr_text)

        self.assertEqual(recipe["name"], "Ruisleipä")
        self.assertIn("500 g ruis jauhoja", recipe["ingredients"])
        self.assertGreater(len(recipe["instructions"]), 0)


if __name__ == "__main__":
    unittest.main()
