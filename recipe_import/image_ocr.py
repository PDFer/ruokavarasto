import re


INGREDIENTS_HEADING = re.compile(
    r"^(?:ainekset|ainesosat?|raaka[-\s]?aineet|tarvikkeet|tarvitset|ingredients)\b",
    re.IGNORECASE,
)
INSTRUCTIONS_HEADING = re.compile(
    r"^(?:valmistus(?:ohje(?:et)?)?|valmistaminen|ohje(?:et)?|tee\s+näin|"
    r"instructions?|directions?|method)\b",
    re.IGNORECASE,
)
YIELD_PATTERN = re.compile(
    r"\b(\d+(?:[,.]\d+)?)\s*"
    r"(annosta?|henkilöä|henkilölle|portion(?:s)?|servings?)\b",
    re.IGNORECASE,
)


def parse_ocr_recipe(text):
    """Map OCR text with conventional recipe headings to importer source data."""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    ingredients_heading = next(
        (index for index, line in enumerate(lines) if INGREDIENTS_HEADING.match(line)),
        None,
    )
    if ingredients_heading is None:
        raise ValueError("OCR-tekstistä ei löytynyt Ainekset-osiota.")

    instructions_heading = next(
        (
            index
            for index in range(ingredients_heading + 1, len(lines))
            if INSTRUCTIONS_HEADING.match(lines[index])
        ),
        None,
    )

    ingredients_end = instructions_heading or len(lines)
    ingredients = lines[ingredients_heading + 1:ingredients_end]
    if not ingredients:
        raise ValueError("OCR-tekstistä ei löytynyt ainesosarivejä.")

    instructions = (
        lines[instructions_heading + 1:]
        if instructions_heading is not None
        else []
    )

    yield_value = None
    title = None
    for line in lines[:ingredients_heading]:
        yield_match = YIELD_PATTERN.search(line)
        if yield_match and yield_value is None:
            yield_value = f"{yield_match.group(1)} {yield_match.group(2)}"
        elif title is None:
            title = line

    if yield_value is None:
        yield_match = YIELD_PATTERN.search(lines[ingredients_heading])
        if yield_match:
            yield_value = f"{yield_match.group(1)} {yield_match.group(2)}"

    if title is None:
        raise ValueError("Reseptin nimeä ei tunnistettu OCR-tekstistä.")

    return {
        "name": title,
        "description": None,
        "yield": yield_value,
        "ingredients": ingredients,
        "instructions": instructions,
        "source_text": text,
    }


def read_image_text(image):
    try:
        import pytesseract
        from PIL import Image
    except ImportError as error:
        raise RuntimeError(
            "Kuvatuonti vaatii Pillow-, pytesseract- ja Tesseract-asennukset."
        ) from error

    with Image.open(image) as opened_image:
        return pytesseract.image_to_string(
            opened_image.convert("RGB"),
            lang="fin+eng",
            config="--psm 6",
        )


def extract_recipe_from_image(image):
    """OCR an image locally and map its text into the importer's source format."""
    text = read_image_text(image)
    if not text.strip():
        raise ValueError("Kuvasta ei saatu luettua tekstiä.")

    return parse_ocr_recipe(text)
