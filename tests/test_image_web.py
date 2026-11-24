import io
import os
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
from PIL import Image

import db_init
import normalizer
import web


def png_image():
    buffer = io.BytesIO()
    Image.new("RGB", (4, 4), "white").save(buffer, format="PNG")
    return buffer.getvalue()


class ImageWebTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(web.app)

    def test_home_contains_separate_url_and_image_forms(self):
        response = self.client.get("/")
        self.assertIn('action="/preview"', response.text)
        self.assertIn('enctype="multipart/form-data"', response.text)
        self.assertIn('action="/image"', response.text)

    def test_existing_url_preview_still_works(self):
        recipe = {
            "name": "Verkkoresepti",
            "yield": {"amount": 4.0, "unit": "annosta"},
            "ingredients": [],
            "instructions": ["Sekoita."],
        }
        with (
            patch("web.import_recipe", return_value=recipe) as importer,
            patch("web.match_ingredients", new_callable=AsyncMock, return_value=[]),
            patch("web.get_grocy_products", new_callable=AsyncMock, return_value=[]),
            patch("web.get_grocy_quantity_units", new_callable=AsyncMock, return_value=[]),
            patch.dict(os.environ, {"GROCY_URL": "http://grocy"}),
        ):
            response = self.client.post("/preview", data={"url": "https://example.com/recipe"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("Verkkoresepti", response.text)
        self.assertIn('action="/save"', response.text)
        importer.assert_called_once_with("https://example.com/recipe")

    @patch("web.read_image_text")
    def test_upload_displays_editable_recipe_and_escapes_ocr(self, ocr):
        ocr.return_value = "Kakku <script>\n4 annosta\nAinekset\n2 dl maitoa\nValmistus\nSekoita."
        response = self.client.post(
            "/image", files={"image": ("recipe.png", png_image(), "image/png")}
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("Kakku &lt;script&gt;", response.text)
        self.assertNotIn("<script>", response.text)
        self.assertIn('name="ingredients"', response.text)
        self.assertIn("2 dl maitoa", response.text)
        self.assertIn("Sekoita.", response.text)
        self.assertIn("ei ole vielä käytettävissä", response.text)
        ocr.assert_called_once()

    @patch("web.read_image_text")
    def test_unparseable_ocr_can_be_corrected(self, ocr):
        ocr.return_value = "Kakku\n2 dl maitoa"
        response = self.client.post(
            "/image", files={"image": ("recipe.png", png_image(), "image/png")}
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("2 dl maitoa", response.text)
        response = self.client.post(
            "/image/text", data={"text": "Kakku\nAinekset\n2 dl maitoa"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn('name="ingredients"', response.text)

    @patch("web.read_image_text")
    def test_invalid_and_oversized_images_are_rejected_before_ocr(self, ocr):
        invalid = self.client.post(
            "/image", files={"image": ("recipe.png", b"not an image", "image/png")}
        )
        with patch("web.MAX_IMAGE_BYTES", 3):
            oversized = self.client.post(
                "/image", files={"image": ("recipe.png", png_image(), "image/png")}
            )
        with patch("web.MAX_IMAGE_PIXELS", 3):
            oversized_pixels = self.client.post(
                "/image", files={"image": ("recipe.png", png_image(), "image/png")}
            )
        self.assertEqual(invalid.status_code, 400)
        self.assertEqual(oversized.status_code, 400)
        self.assertEqual(oversized_pixels.status_code, 400)
        ocr.assert_not_called()

    @patch("web.read_image_text", return_value=" ")
    def test_empty_ocr_is_reported(self, ocr):
        response = self.client.post(
            "/image", files={"image": ("recipe.png", png_image(), "image/png")}
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("ei saatu luettua tekstiä", response.text)

    @patch("web.prepare_recipe")
    def test_edited_fields_are_passed_to_shared_preparation(self, prepare):
        prepare.return_value = {
            "ingredients": [{"raw": "2 dl maitoa", "name": "maito", "amount": 2.0, "unit": "dl"}],
            "untracked_ingredients": [{"raw": "suolaa", "name": "suola"}],
        }
        response = self.client.post(
            "/image/preview",
            data={
                "name": "Korjattu kakku",
                "yield_value": "4 annosta",
                "ingredients": "2 dl maitoa\nsuolaa",
                "instructions": "Sekoita.\nPaista.",
                "source_text": "Alkuperäinen OCR",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            prepare.call_args.args[0],
            {
                "name": "Korjattu kakku",
                "yield": "4 annosta",
                "description": None,
                "ingredients": ["2 dl maitoa", "suolaa"],
                "instructions": ["Sekoita.", "Paista."],
            },
        )
        self.assertIn("maito", response.text)
        self.assertIn("suola", response.text)
        self.assertIn("Paista.", response.text)
        self.assertIn(">Alkuperäinen OCR</textarea>", response.text)

    def test_edited_recipe_is_parsed_with_existing_normalizer(self):
        with tempfile.TemporaryDirectory() as directory:
            db_path = os.path.join(directory, "normalization.db")
            db_init.ensure_schema(db_path)
            with patch.object(normalizer, "DB_PATH", db_path):
                response = self.client.post(
                    "/image/preview",
                    data={
                        "name": "Kakku",
                        "yield_value": "4 annosta",
                        "ingredients": "2 dl maitoa\nsuolaa",
                        "instructions": "Sekoita.",
                    },
                )
        self.assertEqual(response.status_code, 200)
        self.assertIn("2 dl maitoa → maitoa (2.0 dl)", response.text)
        self.assertIn("suolaa → suolaa", response.text)

    @patch("web.prepare_recipe", side_effect=ZeroDivisionError)
    def test_invalid_ingredient_preserves_corrections(self, prepare):
        response = self.client.post(
            "/image/preview",
            data={"name": "Kakku", "ingredients": "1/0 dl maitoa"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("1/0 dl maitoa", response.text)
        self.assertIn("Tarkista määrät", response.text)


if __name__ == "__main__":
    unittest.main()
