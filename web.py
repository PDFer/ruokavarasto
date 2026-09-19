from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse

from recipe_importer import (
    import_recipe,
    match_ingredients,
    format_recipe_preview,
    save_recipe_to_grocy,
    save_ingredient_mapping,
    get_unit_mapping,
    save_unit_mapping,
)
from normalizer import normalize
from grocy_mcp.client import GrocyClient
from db_init import ensure_schema
import os
import logging

async def get_grocy_products():
    client = GrocyClient(
        os.environ["GROCY_URL"],
        os.environ["GROCY_API_KEY"],
    )

    products = await client.get_objects("products")
    await client._client.aclose()

    return products

async def get_grocy_quantity_units():
    client = GrocyClient(
        os.environ["GROCY_URL"],
        os.environ["GROCY_API_KEY"],
    )

    quantity_units = await client.get_objects("quantity_units")
    await client._client.aclose()

    return quantity_units

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
)

logger = logging.getLogger(__name__)

app = FastAPI()


@app.on_event("startup")
async def on_startup():
    ensure_schema()


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

def suggest_unit(unit_text, quantity_units):
    if not unit_text:
        return None

    mapped = get_unit_mapping(unit_text)

    if mapped is not None:
        return mapped

    normalized = unit_text.casefold().strip()

    exact = [
        u for u in quantity_units
        if u["name"].casefold().strip() == normalized
        or (u.get("name_plural") or "").casefold().strip() == normalized
    ]

    if len(exact) == 1:
        return exact[0]["id"]

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

        quantity_units = await get_grocy_quantity_units()
        quantity_units.sort(key=lambda u: u["name"].casefold())

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

            product_options_row = ""

            # Tyhjä vaihtoehto unmatched-tilanteelle
            if selected_id is None:
                product_options_row += '<option value="" selected>-- Ei valintaa --</option>'
            else:
                product_options_row += '<option value="">-- Ei valintaa --</option>'

            for product in products:
                selected = ""
                if product["id"] == selected_id:
                    selected = " selected"

                product_options_row += (
                    f'<option value="{product["id"]}"{selected}>'
                    f'{product["name"]}'
                    f'</option>'
                )

            selected_qu_id = suggest_unit(ingredient["unit"], quantity_units)

            unit_options_row = ""

            if selected_qu_id is None:
                unit_options_row += '<option value="" selected>-- Ei valintaa --</option>'
            else:
                unit_options_row += '<option value="">-- Ei valintaa --</option>'

            for qu in quantity_units:
                selected = ""
                if qu["id"] == selected_qu_id:
                    selected = " selected"

                unit_options_row += (
                    f'<option value="{qu["id"]}"{selected}>'
                    f'{qu["name"]}'
                    f'</option>'
                )

            amount = ingredient["amount"]
            if amount is None:
                amount_text = ""
            else:
                amount_text = f"{amount:g}"

            unit_missing_marker = ""
            if ingredient.get("unit_missing"):
                unit_missing_marker = (
                    ' <span title="Yksikköä ei tunnistettu automaattisesti">⚠</span>'
                )

            name = ingredient["name"]

            ingredient_rows += f"""
            <tr>
                <td>
                    <input
                        type="number"
                        step="any"
                        name="amount_{index}"
                        id="amount_{index}"
                        value="{amount_text}"
                        style="width: 5rem;"
                    >
                </td>
                <td>
                    <select name="unit_{index}" id="unit_{index}" class="unit-select">
                        {unit_options_row}
                    </select>{unit_missing_marker}
                </td>
                <td>{name}</td>
                <td>
                    <select name="product_{index}" id="product_{index}">
                        {product_options_row}
                    </select>
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

        grocy_new_product_url = os.environ["GROCY_URL"].rstrip("/") + "/product/new"

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

                select.unit-select {{
                    min-width: 120px;
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

            <p>
                <a href="{grocy_new_product_url}" target="_blank" rel="noopener">
                    ↗ Lisää uusi tuote Grocyyn (uusi välilehti)
                </a>
                &nbsp;·&nbsp;
                <button type="button" onclick="refreshOptions()">
                    ↻ Päivitä valikot
                </button>
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
            function escapeHtml(text) {{
                const div = document.createElement("div");
                div.textContent = text;
                return div.innerHTML;
            }}

            function buildOptions(items, currentValue) {{
                let html = '<option value="">-- Ei valintaa --</option>';

                for (const item of items) {{
                    const selected = String(item.id) === currentValue ? " selected" : "";
                    html += `<option value="${{item.id}}"${{selected}}>${{escapeHtml(item.name)}}</option>`;
                }}

                return html;
            }}

            async function refreshOptions() {{
                let data;

                try {{
                    const response = await fetch("/refresh-options");
                    data = await response.json();
                }} catch (error) {{
                    alert("Valikoiden päivitys epäonnistui:\\n" + error);
                    return;
                }}

                document.querySelectorAll('select[id^="product_"]').forEach(select => {{
                    const current = select.value;
                    select.innerHTML = buildOptions(data.products, current);
                }});

                document.querySelectorAll('select[id^="unit_"]').forEach(select => {{
                    const current = select.value;
                    select.innerHTML = buildOptions(data.quantity_units, current);
                }});
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

        # Luetaan käyttäjän tekemät Grocy-tuote- ja yksikkövalinnat
        for index, ingredient in enumerate(ingredients):
            product_value = form_data.get(f"product_{index}")
            unit_value = form_data.get(f"unit_{index}")
            amount_value = form_data.get(f"amount_{index}")

            if not product_value:
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

            if not unit_value:
                return HTMLResponse(
                    f"""
                    <h1>Reseptiä ei tallennettu</h1>
                    <p>
                        Ainesosalle
                        <strong>{ingredient["name"]}</strong>
                        ei ole valittu Grocy-yksikköä.
                    </p>
                    <p><a href="javascript:history.back()">← Takaisin</a></p>
                    """,
                    status_code=400,
                )

            # Alkuperäinen reseptin määrä voidaan haluta muuttaa
            # (esim. eri yksikköön siirryttäessä), joten luetaan lomakkeelta.
            if amount_value:
                try:
                    ingredient["amount"] = float(str(amount_value).replace(",", "."))
                except ValueError:
                    return HTMLResponse(
                        f"""
                        <h1>Reseptiä ei tallennettu</h1>
                        <p>
                            Ainesosan
                            <strong>{ingredient["name"]}</strong>
                            määrä <strong>{amount_value}</strong> ei ole kelvollinen luku.
                        </p>
                        <p><a href="javascript:history.back()">← Takaisin</a></p>
                        """,
                        status_code=400,
                    )

            ingredient["grocy"]["matched_product_id"] = int(product_value)
            ingredient["grocy"]["status"] = "matched"
            ingredient["grocy_qu_id"] = int(unit_value)

            save_ingredient_mapping(
                ingredient["name"],
                int(product_value),
            )

            # Muistetaan yksikkövalinta vain, jos jäsentäjä tunnisti
            # reseptistä alkuperäisen yksikkötekstin - täysin tunnistamatta
            # jääneen (esim. "1 valkosipulinkynsi") kohdalla käyttäjä
            # valitsee yksikön joka kerta erikseen.
            if ingredient.get("unit"):
                save_unit_mapping(
                    ingredient["unit"],
                    int(unit_value),
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

@app.get("/refresh-options")
async def refresh_options():
    try:
        products = await get_grocy_products()
        products.sort(key=lambda p: p["name"].casefold())

        quantity_units = await get_grocy_quantity_units()
        quantity_units.sort(key=lambda u: u["name"].casefold())

        return {
            "products": [
                {"id": p["id"], "name": p["name"]}
                for p in products
            ],
            "quantity_units": [
                {"id": u["id"], "name": u["name"]}
                for u in quantity_units
            ],
        }

    except Exception as e:
        return JSONResponse(
            {"error": str(e)},
            status_code=400,
        )


