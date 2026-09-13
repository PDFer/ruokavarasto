import re
from fractions import Fraction


UNITS = [
    "rkl",
    "tl",
    "dl",
    "cl",
    "ml",
    "kg",
    "mg",
    "g",
    "l",
    "kpl",
    "prk",
    "pkt",
    "ripaus",
]

UNICODE_FRACTIONS = {
    "½": 0.5,
    "⅓": 1 / 3,
    "⅔": 2 / 3,
    "¼": 0.25,
    "¾": 0.75,
    "⅕": 0.2,
    "⅖": 0.4,
    "⅗": 0.6,
    "⅘": 0.8,
    "⅙": 1 / 6,
    "⅚": 5 / 6,
    "⅛": 0.125,
    "⅜": 0.375,
    "⅝": 0.625,
    "⅞": 0.875,
}


def parse_number(text: str) -> float:
    """Parse integers, decimals, fractions and mixed numbers."""
    text = text.strip().replace(",", ".")

    # Mixed fraction: 1 1/2
    match = re.fullmatch(r"(\d+)\s+(\d+)/(\d+)", text)
    if match:
        whole, numerator, denominator = match.groups()
        return float(whole) + float(Fraction(int(numerator), int(denominator)))

    # Simple fraction: 1/2
    match = re.fullmatch(r"(\d+)/(\d+)", text)
    if match:
        numerator, denominator = match.groups()
        return float(Fraction(int(numerator), int(denominator)))

    # Unicode fraction, optionally after a whole number
    if text:
        if text in UNICODE_FRACTIONS:
            return UNICODE_FRACTIONS[text]

        match = re.fullmatch(r"(\d+)\s*(.)", text)
        if match and match.group(2) in UNICODE_FRACTIONS:
            return float(match.group(1)) + UNICODE_FRACTIONS[match.group(2)]

    return float(text)


def extract_notes(text: str):
    """Extract parenthesized notes from ingredient text."""
    notes = re.findall(r"\(([^()]*)\)", text)
    cleaned = re.sub(r"\([^()]*\)", " ", text)
    return notes, cleaned


def parse_ingredient(raw: str) -> dict:
    """Parse one recipe ingredient into structured data."""
    raw = raw.strip()

    notes, text = extract_notes(raw)
    text = re.sub(r"\s+", " ", text).strip()

    number_pattern = r"(\d+\s+\d+/\d+|\d+/\d+|\d+(?:[.,]\d+)?)"

    unit_pattern = "|".join(re.escape(unit) for unit in UNITS)

    # Approximate/non-numeric amount
    match = re.match(
        r"^\s*(ripaus)\s+(.+)$",
        text,
        re.IGNORECASE,
    )

    if match:
        unit, name = match.groups()

        return {
            "raw": raw,
            "amount": 1.0,
            "unit": unit.lower(),
            "name": name.strip(),
            "notes": notes,
        }

    match = re.match(
        rf"^\s*{number_pattern}\s+({unit_pattern})\b\s*(.*)$",
        text,
        re.IGNORECASE,
    )

    if not match:
        return {
            "raw": raw,
            "amount": None,
            "unit": None,
            "name": text,
            "notes": notes,
        }

    number_text, unit, name = match.groups()

    return {
        "raw": raw,
        "amount": parse_number(number_text),
        "unit": unit.lower(),
        "name": name.strip(),
        "notes": notes,
    }


def parse_ingredients(ingredients):
    """Parse a list of recipe ingredient strings."""
    return [parse_ingredient(ingredient) for ingredient in ingredients]


if __name__ == "__main__":
    test_ingredients = [
        "800 g (4–6 kpl) omenoita (kotimaisia)",
        "1 1/2 tl kanelia",
        "100 g leivontamargariinia (maidotonta)",
        "1/2 dl fariinisokeria",
        "3 dl kaurahiutaleita",
        "2 1/2 dl (1 prk) kaurakasvirasvasekoitetta 15 %",
        "1 rkl perunajauhoja",
        "1 rkl sokeria",
        "1 tl vaniljasokeria",
    ]

    import json

    print(json.dumps(
        parse_ingredients(test_ingredients),
        ensure_ascii=False,
        indent=2,
    ))
