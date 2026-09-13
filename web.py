from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse

from recipe_importer import (
    import_recipe,
    match_ingredients,
    format_recipe_preview,
    save_recipe_to_grocy,
    create_grocy_product,
    save_ingredient_mapping,
)
from normalizer import normalize
from grocy_mcp.client import GrocyClient
import os
import json
import logging

async def get_grocy_products():
    client = GrocyClient(
        os.environ["GROCY_URL"],
        os.environ["GROCY_API_KEY"],
    )

    products = await client.get_objects("products")
    await client._client.aclose()

    return products

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
)

logger = logging.getLogger(__name__)

app = FastAPI()


def suggest_product(ingredient_name, products):
    normalized_name = normalize(ingredient_name).casefold().strip()

    # 1. Täsmällinen nimi
    exact = [
        p for p in products
        if p["name"].casefold().strip() == normalized_name
    ]

    if len(exact) == 1:
        return exact[0]["id"]

    # 2. Alkuosan perusteella
    prefix = normalized_name[:4]

    if len(prefix) < 3:
        return None

    candidates = [
        p for p in products
        if p["name"].casefold().strip().startswith(prefix)
    ]

    if len(candidates) == 1:
        return candidates[0]["id"]

    return None

@app.get("/", response_class=HTMLResponse)
async def index():
    return """
    <!DOCTYPE html>
    <html lang="fi">
    <head>
        <meta charset="utf-8">
        <title>Grocy resepti-importteri</title>
    </head>
    <body>
        <h1>Reseptin tuonti</h1>

        <form method="post" action="/preview">
            <label for="url">Reseptin URL:</label><br>
            <input
                type="url"
                id="url"
                name="url"
                size="80"
                required
            >
            <br><br>
            <button type="submit">Esikatsele</button>
        </form>
    </body>
    </html>
    """



@app.post("/preview", response_class=HTMLResponse)
async def preview(url: str = Form(...)):
    try:
        recipe = import_recipe(url)
        ingredients = await match_ingredients(recipe["ingredients"])
        products = await get_grocy_products()
        products.sort(key=lambda p: p["name"].casefold())

        product_options = ""
        for product in products:
            product_options += (
                f'<option value="{product["id"]}">'
                f'{product["name"]}'
                f'</option>'
            )

        ingredient_rows = ""

        for index, ingredient in enumerate(ingredients):
            grocy = ingredient["grocy"]
            selected_id = grocy.get("matched_product_id")

            if selected_id is None:
                selected_id = suggest_product(
                    ingredient["name"],
                    products,
                )

            options = ""

            # Tyhjä vaihtoehto unmatched-tilanteelle
            if selected_id is None:
                options += '<option value="" selected>-- Ei valintaa --</option>'
            else:
                options += '<option value="">-- Ei valintaa --</option>'

            for product in products:
                selected = ""
                if product["id"] == selected_id:
                    selected = " selected"

                options += (
                    f'<option value="{product["id"]}"{selected}>'
                    f'{product["name"]}'
                    f'</option>'
                )

            amount = ingredient["amount"]
            if amount is None:
                amount_text = ""
            else:
                amount_text = f"{amount:g}"

            unit = ingredient["unit"] or ""
            name = ingredient["name"]

            name_js = json.dumps(name)
            
            ingredient_rows += f"""
            <tr>
                <td>{amount_text}</td>
                <td>{unit}</td>
                <td>{name}</td>
                <td>
                    <select name="product_{index}" id="product_{index}">
                        {options}
                    </select>
                    <button
                        type="button"
                        onclick='createProduct({index}, {name_js}, {json.dumps(unit)})'
                    >
                        + Luo uusi
                    </button>
                </td>
            </tr>
            """

        instruction_rows = ""

        for index, instruction in enumerate(
            recipe.get("instructions", []),
            start=1,
        ):
            if isinstance(instruction, dict):
                text = instruction.get("text", "")
            else:
                text = str(instruction)

            if text:
                instruction_rows += f"""
                <li>{text}</li>
                """

        return f"""
        <!DOCTYPE html>
        <html lang="fi">
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <title>Reseptin esikatselu</title>

            <style>
                body {{
                    font-family: sans-serif;
                    margin: 2rem;
                }}

                table {{
                    border-collapse: collapse;
                    width: 100%;
                    max-width: 1000px;
                }}

                th, td {{
                    padding: 0.6rem;
                    border-bottom: 1px solid #ccc;
                    text-align: left;
                }}

                select {{
                    min-width: 250px;
                    padding: 0.4rem;
                }}
            </style>
        </head>

        <body>
            <h1>{recipe["name"]}</h1>

            <p>
                Annoksia:
                <strong>{recipe["yield"]["amount"]:g}</strong>
                {recipe["yield"]["unit"]}
            </p>

            <form method="post" action="/save">

                <input type="hidden" name="url" value="{url}">

                <table>
                    <thead>
                        <tr>
                            <th>Määrä</th>
                            <th>Yksikkö</th>
                            <th>Ainesosa</th>
                            <th>Grocy-tuote</th>
                        </tr>
                    </thead>

                    <tbody>
                        {ingredient_rows}
                    </tbody>
                </table>

                <h2>Valmistusohje</h2>

                <ol>
                    {instruction_rows}
                </ol>

                <br>

                <button type="submit">
                    Tallenna Grocyyn
                </button>

            </form>

            <p>
                <a href="/">← Takaisin</a>
            </p>
        <script>
            async function createProduct(index, ingredientName, unit) {{
                const productName = prompt(
                    "Uuden Grocy-tuotteen nimi:",
                    ingredientName
                );

                if (!productName) {{
                    return;
                }}

                const formData = new FormData();
                formData.append("product_name", productName);
                formData.append("unit", unit);

                try {{
                    const response = await fetch("/create-product", {{
                        method: "POST",
                        body: formData
                    }});

                    const result = await response.json();

                    if (!response.ok || !result.success) {{
                        alert("Tuotteen luonti epäonnistui:\\n" + result.error);
                        return;
                    }}

                    const select = document.getElementById("product_" + index);

                    const option = new Option(
                        result.product_name,
                        result.product_id,
                        true,
                        true
                    );

                    select.add(option);

                }} catch (error) {{
                    alert("Tuotteen luonti epäonnistui:\\n" + error);
                }}
            }}
        </script>
        </body>
        </html>
        """

    except Exception as e:
        return f"""
        <!DOCTYPE html>
        <html lang="fi">
        <head>
            <meta charset="utf-8">
            <title>Virhe</title>
        </head>
        <body>
            <h1>Virhe</h1>
            <pre>{e}</pre>
            <p><a href="/">← Takaisin</a></p>
        </body>
        </html>
        """

@app.post("/save", response_class=HTMLResponse)
async def save(
    request: Request,
    url: str = Form(...),
):
    form_data = await request.form()
    try:
        recipe = import_recipe(url)
        ingredients = await match_ingredients(recipe["ingredients"])

        # Luetaan käyttäjän tekemät Grocy-tuotevalinnat
        for index, ingredient in enumerate(ingredients):
            value = form_data.get(f"product_{index}")

            if not value:
                return HTMLResponse(
                    f"""
                    <h1>Reseptiä ei tallennettu</h1>
                    <p>
                        Ainesosalle
                        <strong>{ingredient["name"]}</strong>
                        ei ole valittu Grocy-tuotetta.
                    </p>
                    <p><a href="javascript:history.back()">← Takaisin</a></p>
                    """,
                    status_code=400,
                )

            ingredient["grocy"]["matched_product_id"] = int(value)
            ingredient["grocy"]["status"] = "matched"
            save_ingredient_mapping(
                ingredient["name"],
                int(value),
            )

        recipe_id = await save_recipe_to_grocy(recipe, ingredients)

        return f"""
        <!DOCTYPE html>
        <html lang="fi">
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <title>Resepti tallennettu</title>
        </head>
        <body>
            <h1>Resepti tallennettu</h1>

            <p>
                <strong>{recipe["name"]}</strong>
                luotiin Grocyyn.
            </p>

            <p>Reseptin ID: {recipe_id}</p>

            <p>
                <a href="/">← Tuo toinen resepti</a>
            </p>
        </body>
        </html>
        """

    except Exception as e:
        return f"""
        <!DOCTYPE html>
        <html lang="fi">
        <head>
            <meta charset="utf-8">
            <title>Virhe</title>
        </head>
        <body>
            <h1>Virhe</h1>
            <pre>{e}</pre>
            <p><a href="javascript:history.back()">← Takaisin</a></p>
        </body>
        </html>
        """

@app.post("/create-product")
async def create_product(
    product_name: str = Form(...),
    unit: str = Form(...),
):
    try:
        product_name = product_name.strip()

        if not product_name:
            raise ValueError("Tuotteen nimi puuttuu.")

        product_id = await create_grocy_product(product_name, unit)

        return {
            "success": True,
            "product_id": product_id,
            "product_name": product_name,
        }

    except Exception as e:
        return JSONResponse(
            {
                "success": False,
                "error": str(e),
            },
            status_code=400,
        )


