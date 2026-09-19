import json
import re
from html import escape
from html.parser import HTMLParser
from urllib.request import Request, urlopen
from recipe_import.ingredient_parser import parse_ingredients
from normalizer import normalize_ingredient
from recipe_scrapers import scrape_html
from db_init import ensure_schema
import os

from grocy_mcp.client import GrocyClient
from grocy_mcp.core.workflows import workflow_match_products_preview_data
import sqlite3
import logging

logger = logging.getLogger(__name__)

class JSONLDParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_jsonld = False
        self.current = []
        self.blocks = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)

        if (
            tag.lower() == "script"
            and attrs.get("type", "").lower() == "application/ld+json"
        ):
            self.in_jsonld = True
            self.current = []

    def handle_data(self, data):
        if self.in_jsonld:
            self.current.append(data)

    def handle_endtag(self, tag):
        if tag.lower() == "script" and self.in_jsonld:
            self.blocks.append("".join(self.current))
            self.in_jsonld = False
            self.current = []


def _download(url):
    request = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (RecipeImporter/1.0)"
        },
    )

    with urlopen(request, timeout=20) as response:
        return response.read().decode("utf-8", errors="replace")


def _extract_json_ld(html, url=None):
    parser = JSONLDParser()
    parser.feed(html)

    for block in parser.blocks:
        try:
            data = json.loads(block)
        except json.JSONDecodeError:
            continue

        candidates = []

        if isinstance(data, dict):
            candidates.append(data)

            # JSON-LD voi sisältää @graph-rakenteen
            if isinstance(data.get("@graph"), list):
                candidates.extend(data["@graph"])

        elif isinstance(data, list):
            candidates.extend(data)

        for item in candidates:
            if not isinstance(item, dict):
                continue

            recipe_type = item.get("@type")

            if recipe_type == "Recipe" or (
                isinstance(recipe_type, list) and "Recipe" in recipe_type
            ):
                return {
                    "name": item.get("name"),
                    "description": item.get("description"),
                    "yield": item.get("recipeYield"),
                    "ingredients": item.get("recipeIngredient", []),
                    "instructions": item.get("recipeInstructions", []),
                }

    return None


def _safe_call(method):
    try:
        return method()
    except NotImplementedError:
        return None
    except Exception:
        return None


def _extract_via_recipe_scrapers(html, url):
    try:
        scraper = scrape_html(html=html, org_url=url, wild_mode=True)
    except Exception as e:
        logger.debug("recipe-scrapers ei tunnistanut reseptiä (%s): %s", url, e)
        return None

    ingredients = _safe_call(scraper.ingredients) or []

    if not ingredients:
        return None

    return {
        "name": _safe_call(scraper.title),
        "description": _safe_call(scraper.description),
        "yield": _safe_call(scraper.yields),
        "ingredients": ingredients,
        "instructions": _safe_call(scraper.instructions_list) or [],
    }


def fetch_recipe(url):
    html = _download(url)

    for extractor in (_extract_json_ld, _extract_via_recipe_scrapers):
        try:
            recipe = extractor(html, url)
        except Exception as e:
            logger.debug("extraktori %s epäonnistui: %s", extractor.__name__, e)
            continue

        if recipe and recipe.get("ingredients"):
            return recipe

    raise ValueError("Sivulta ei löytynyt reseptitietoa millään tunnetulla menetelmällä")

def import_recipe(url):
    recipe = fetch_recipe(url)

    ingredients = parse_ingredients(recipe["ingredients"])
    ingredients = [normalize_ingredient(i) for i in ingredients]

    # Ainesosat, joilla ei ole määrää (esim. "basilikaa" makuun), eivät
    # sovi Grocyn varastonseurantaan järkevästi - ne käsitellään erikseen
    # tekstimuotoisena mainintana eikä varastoa vaativana reseptirivinä.
    tracked = [i for i in ingredients if i["amount"] is not None]
    untracked = [i for i in ingredients if i["amount"] is None]

    recipe["ingredients"] = tracked
    recipe["untracked_ingredients"] = untracked
    recipe["yield"] = parse_yield(recipe["yield"])

    return recipe

async def match_ingredients(ingredients):
    client = GrocyClient(
        os.environ["GROCY_URL"],
        os.environ["GROCY_API_KEY"],
    )

    result = []

    with sqlite3.connect("/app/data/normalization.db") as db:
        for ingredient in ingredients:
            normalized_name = ingredient["name"]

            row = db.execute(
                """
                SELECT grocy_product_id
                FROM ingredient_grocy_mapping
                WHERE normalized_term = ?
                  AND confirmed = 1
                """,
                (normalized_name,),
            ).fetchone()

            if row:
                product_id = row[0]
                product = await client.get_stock_product(product_id)

                grocy = {
                    "status": "matched",
                    "matched_product_id": product_id,
                    "matched_product_name": product["product"]["name"],
                    "source": "mapping",
                }

            else:
                match_item = {
                    "label": normalized_name,
                }

                if ingredient["amount"] is not None:
                    match_item["quantity"] = ingredient["amount"]

                matches = await workflow_match_products_preview_data(
                    client,
                    [match_item],
                )

                grocy = matches[0]
                grocy["source"] = "matcher"

            result.append({
                **ingredient,
                "grocy": grocy,
            })

    return result

def format_recipe_preview(recipe, ingredients):

    yield_data = recipe["yield"]

    if yield_data["amount"] is not None:
        yield_text = f"{yield_data['amount']:g} {yield_data['unit']}"
    else:
        yield_text = yield_data["raw"] or ""

    lines = [
        recipe["name"],
        yield_text,
        "",
    ]

    for ingredient in ingredients:
        amount = ingredient["amount"]
        if amount is not None:
            amount_text = f"{amount:g}"
        else:
            amount_text = ""

        unit = ingredient["unit"] or ""
        name = ingredient["name"]

        line = f"{amount_text} {unit} {name}".strip()
        lines.append(line)

        grocy = ingredient["grocy"]

        if grocy["status"] == "matched":
            lines.append(
                f"  → ✓ {grocy['matched_product_name']}"
            )
        else:
            lines.append("  → ❌ Ei osumaa")

        for note in ingredient["notes"]:
            lines.append(f"  → {note}")

        if ingredient.get("unit_missing"):
            lines.append(
                "  → ⚠ Yksikköä ei tunnistettu - tarkista/korjaa ennen tallennusta"
            )

        lines.append("")

    untracked = recipe.get("untracked_ingredients") or []
    untracked_names = [i["name"] for i in untracked if i.get("name")]

    if untracked_names:
        lines.append("Lisäksi (ei varastoseurantaa): " + ", ".join(untracked_names))
        lines.append("")

    # Valmistusohje
    if recipe.get("instructions"):
        lines.append("Valmistusohje")
        lines.append("")

        for index, instruction in enumerate(recipe["instructions"], start=1):
            if isinstance(instruction, dict):
                text = instruction.get("text", "")
            else:
                text = str(instruction)

            if text:
                lines.append(f"{index}. {text}")
                lines.append("")

    return "\n".join(lines)


async def save_recipe_to_grocy(recipe, ingredients):
    client = GrocyClient(
        os.environ["GROCY_URL"],
        os.environ["GROCY_API_KEY"],
    )

    instructions = recipe.get("instructions", [])

    instruction_text = "\n\n".join(
        instruction.get("text", "")
        if isinstance(instruction, dict)
        else str(instruction)
        for instruction in instructions
        if instruction
    )

    recipe_id = await client.create_object(
        "recipes",
        {
            "name": recipe["name"],
            "description": instruction_text,
            "base_servings": recipe["yield"]["amount"] or 1,
            "desired_servings": recipe["yield"]["amount"] or 1,
        },
    )

    for ingredient in ingredients:
        grocy = ingredient["grocy"]

        if grocy["status"] != "matched":
            continue

        product_id = grocy["matched_product_id"]

        product = await client.get_stock_product(product_id)
        product_name = product["product"]["name"]

        # Käytetään MCP:n olemassa olevaa reseptin ainesosan lisäystä.
        # Grocy määrittää samalla tuotteen oletusyksikön.
        from grocy_mcp.core.workflows import workflow_add_recipe_ingredient

        await workflow_add_recipe_ingredient(
            client,
            recipe_id=recipe_id,
            product_id=product_id,
            amount=ingredient["amount"],
        )

    return recipe_id


def parse_yield(value):
    if value is None:
        return {
            "amount": None,
            "unit": None,
            "raw": None,
        }

    text = str(value).strip()

    match = re.match(r"^(\d+(?:[.,]\d+)?)\s*(.*)$", text)

    if not match:
        return {
            "amount": None,
            "unit": None,
            "raw": text,
        }

    amount = float(match.group(1).replace(",", "."))
    unit = normalize_yield_unit(match.group(2).strip())

    return {
        "amount": amount,
        "unit": unit,
        "raw": text,
    }

def normalize_yield_unit(unit):
    units = {
        "portion": "annos",
        "portions": "annos",
        "serving": "annos",
        "servings": "annos",
    }

    return units.get(unit.lower(), unit)

async def save_recipe_to_grocy(recipe, ingredients):
    client = GrocyClient(
        os.environ["GROCY_URL"],
        os.environ["GROCY_API_KEY"],
    )

    instructions = recipe.get("instructions", [])

    instruction_text = (
        '<div class="is-block has-inner-container">'
        '<div class="inner-container">'
        '<ol>'
        + "".join(
            f"<li>{escape(instruction.get('text', '') if isinstance(instruction, dict) else str(instruction))}</li>"
            for instruction in instructions
            if instruction
        )
        + "</ol>"
        "</div>"
        "</div>"
    )

    untracked = recipe.get("untracked_ingredients") or []
    untracked_names = [i["name"] for i in untracked if i.get("name")]

    if untracked_names:
        instruction_text += (
            '<div class="is-block has-inner-container">'
            '<div class="inner-container">'
            f"<p>Lisäksi: {escape(', '.join(untracked_names))}</p>"
            "</div>"
            "</div>"
        )

    recipe_id = await client.create_object(
        "recipes",
        {
            "name": recipe["name"],
            "description": instruction_text,
            "base_servings": recipe["yield"]["amount"] or 1,
            "desired_servings": recipe["yield"]["amount"] or 1,
        },
    )


    for ingredient in ingredients:
        grocy = ingredient["grocy"]

        if grocy["status"] != "matched":
            raise ValueError(
                f"Ainesosalle '{ingredient['name']}' ei ole Grocy-tuotetta."
            )

        product_id = grocy["matched_product_id"]

        qu_id = ingredient.get("grocy_qu_id")

        if qu_id is None:
            raise ValueError(
                f"Ainesosalle '{ingredient['name']}' ei ole valittu Grocy-yksikköä."
            )

        logger.debug(
            "TALLENNUS: %s %s -> product_id=%s, qu_id=%s",
            ingredient["name"],
            ingredient["amount"],
            product_id,
            qu_id,
        )

        try:
            pos_id = await client.create_object(
                "recipes_pos",
                {
                    "recipe_id": recipe_id,
                    "product_id": product_id,
                    "amount": ingredient["amount"],
                    "qu_id": qu_id,
                },
            )

            logger.debug(
                "TALLENNETTU: %s -> position_id=%s",
                ingredient["name"],
                pos_id,
            )

        except Exception as e:
            raise ValueError(
                f"Ainesosan '{ingredient['name']}' tallennus epäonnistui: "
                f"tuote ID {product_id}, yksikkö '{unit}' (qu_id {qu_id}). "
                f"Grocy: {e}"
            ) from e
    return recipe_id

def get_unit_mapping(source_term):
    """Hae vahvistettu Grocy-yksikkömappaus annetulle raakatekstille."""
    if not source_term:
        return None

    with sqlite3.connect("/app/data/normalization.db") as db:
        row = db.execute(
            """
            SELECT grocy_qu_id
            FROM unit_grocy_mapping
            WHERE source_term = ?
              AND confirmed = 1
            """,
            (source_term,),
        ).fetchone()

    return row[0] if row else None


def save_unit_mapping(source_term, grocy_qu_id):
    with sqlite3.connect("/app/data/normalization.db") as db:
        db.execute(
            """
            INSERT INTO unit_grocy_mapping
                (source_term, grocy_qu_id, confirmed)
            VALUES (?, ?, 1)
            ON CONFLICT(source_term)
            DO UPDATE SET
                grocy_qu_id = excluded.grocy_qu_id,
                confirmed = 1
            """,
            (source_term, grocy_qu_id),
        )
        db.commit()

def save_ingredient_mapping(normalized_term, grocy_product_id):
    with sqlite3.connect("/app/data/normalization.db") as db:
        db.execute(
            """
            INSERT INTO ingredient_grocy_mapping
                (normalized_term, grocy_product_id, confirmed)
            VALUES (?, ?, 1)
            ON CONFLICT(normalized_term)
            DO UPDATE SET
                grocy_product_id = excluded.grocy_product_id,
                confirmed = 1
            """,
            (normalized_term, grocy_product_id),
        )
        db.commit()


async def test_save():
    recipe = import_recipe(
        "https://yhteishyva.fi/reseptit/kaura-omenapaistos/4Np5MrTHxjBVjgnKMNGUo3"
    )
    ingredients = await match_ingredients(recipe["ingredients"])
    recipe_id = await save_recipe_to_grocy(recipe, ingredients)
    print("Created recipe:", recipe_id)


if __name__ == "__main__":
    import asyncio
    ensure_schema()
    asyncio.run(test_save())
