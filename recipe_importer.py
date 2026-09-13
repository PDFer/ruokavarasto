import json
import re
from html import escape
from html.parser import HTMLParser
from urllib.request import Request, urlopen
from recipe_import.ingredient_parser import parse_ingredients
from normalizer import normalize_ingredient
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


def fetch_recipe(url):
    request = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (RecipeImporter/1.0)"
        },
    )

    with urlopen(request, timeout=20) as response:
        html = response.read().decode("utf-8", errors="replace")

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

    raise ValueError("Sivulta ei löytynyt Recipe JSON-LD -tietoa")

def import_recipe(url):
    recipe = fetch_recipe(url)

    ingredients = parse_ingredients(recipe["ingredients"])
    ingredients = [normalize_ingredient(i) for i in ingredients]

    recipe["ingredients"] = ingredients
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

    # Hae Grocyn yksiköt kerran
    quantity_units = await client.get_objects("quantity_units")

    unit_map = {
        unit["name"].lower(): unit["id"]
        for unit in quantity_units
        if unit.get("active", 1)
    }

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

        unit = ingredient.get("unit")

        if not unit:
            raise ValueError(
                f"Ainesosalta '{ingredient['name']}' puuttuu yksikkö."
            )

        qu_id = unit_map.get(unit.lower())

        if qu_id is None:
            raise ValueError(
                f"Grocyssa ei ole yksikköä '{unit}' "
                f"ainesosalle '{ingredient['name']}'."
            )

        logger.debug(
            "TALLENNUS: %s %s %s -> product_id=%s, qu_id=%s",
            ingredient["name"],
            ingredient["amount"],
            unit,
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

async def create_grocy_product(name, unit):
    client = GrocyClient(
        os.environ["GROCY_URL"],
        os.environ["GROCY_API_KEY"],
    )

    quantity_units = await client.get_objects("quantity_units")

    unit_map = {
        u["name"].lower(): u["id"]
        for u in quantity_units
        if u.get("active", 1)
    }

    qu_id = unit_map.get(unit.lower())

    if qu_id is None:
        raise ValueError(f"Grocyssa ei ole yksikköä '{unit}'.")

    product_id = await client.create_object(
        "products",
        {
            "name": name,
            "location_id": 5,
            "qu_id_purchase": qu_id,
            "qu_id_stock": qu_id,
            "qu_id_consume": qu_id,
        },
    )

    await client._client.aclose()

    return product_id

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
    asyncio.run(test_save())
