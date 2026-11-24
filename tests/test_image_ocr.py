import unittest
from unittest.mock import patch

from recipe_import import image_ocr


class ParseOcrRecipeTests(unittest.TestCase):
    def test_extracts_recipe_fields_from_finnish_headings(self):
        recipe = image_ocr.parse_ocr_recipe(
            "Omenapaistos\n4 annosta\nAinekset\n"
            "3 dl kaurahiutaleita\n2 omenaa\nValmistus\n"
            "Sekoita ainekset.\nPaista uunissa."
        )

        self.assertEqual(recipe["name"], "Omenapaistos")
        self.assertEqual(recipe["yield"], "4 annosta")
        self.assertEqual(
            recipe["ingredients"],
            ["3 dl kaurahiutaleita", "2 omenaa"],
        )
        self.assertEqual(
            recipe["instructions"],
            ["Sekoita ainekset.", "Paista uunissa."],
        )

    def test_accepts_ingredients_without_an_instructions_section(self):
        recipe = image_ocr.parse_ocr_recipe(
            "Pannukakku\nRaaka-aineet (4 annosta):\n2 dl maitoa\n1 muna"
        )

        self.assertEqual(recipe["yield"], "4 annosta")
        self.assertEqual(recipe["ingredients"], ["2 dl maitoa", "1 muna"])
        self.assertEqual(recipe["instructions"], [])

    def test_recognizes_alternate_instructions_heading(self):
        recipe = image_ocr.parse_ocr_recipe(
            "Pannukakku\nTarvikkeet\n2 dl maitoa\nTee näin\n"
            "Sekoita taikina."
        )

        self.assertEqual(recipe["instructions"], ["Sekoita taikina."])

    def test_reports_missing_ingredient_section(self):
        with self.assertRaisesRegex(ValueError, "Ainekset"):
            image_ocr.parse_ocr_recipe("Omenapaistos\nPaista uunissa.")

    def test_ocr_adapter_passes_text_to_recipe_parser(self):
        with patch(
            "recipe_import.image_ocr.read_image_text",
            return_value="Kakku\nAinekset\n1 dl sokeria",
        ):
            recipe = image_ocr.extract_recipe_from_image(object())

        self.assertEqual(recipe["ingredients"], ["1 dl sokeria"])


if __name__ == "__main__":
    unittest.main()
