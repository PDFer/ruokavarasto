from io import BytesIO
from html import escape
import warnings

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse
from PIL import Image, UnidentifiedImageError
from starlette.concurrency import run_in_threadpool

from recipe_importer import (
    import_recipe,
    prepare_recipe,
    match_ingredients,
    format_recipe_preview,
    save_recipe_to_grocy,
    save_ingredient_mapping,
    get_unit_mapping,
    save_unit_mapping,
)
from recipe_import.image_ocr import parse_ocr_recipe, read_image_text
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

MAX_IMAGE_BYTES = 10 * 1024 * 1024
MAX_IMAGE_PIXELS = 20_000_000
IMAGE_FORMATS = {"JPEG", "PNG"}


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

        <h2>Reseptikuva</h2>
        <form method="post" action="/image" enctype="multipart/form-data">
            <label for="image">Valitse yksi JPEG- tai PNG-kuva (enintään 10 Mt):</label><br>
            <input type="file" id="image" name="image" accept="image/jpeg,image/png" required>
            <br><br>
            <button type="submit">Lue kuva</button>
        </form>
    </body>
    </html>
    """


def image_error(message, status_code=400):
    return HTMLResponse(
        f'<h1>Kuvan käsittely epäonnistui</h1><p>{escape(message)}</p>'
        '<p><a href="/">← Takaisin</a></p>',
        status_code=status_code,
    )


def image_editor(text, recipe=None, message=None, prepared=None):
    notice = f'<p role="alert">{escape(message)}</p>' if message else ""
    fields = ""
    if recipe is not None:
        ingredients = "\n".join(recipe["ingredients"])
        instructions = "\n".join(recipe["instructions"])
        fields = f"""
        <h2>Korjaa reseptin tiedot</h2>
        <form method="post" action="/image/preview">
            <input type="hidden" name="source_text" value="{escape(text, quote=True)}">
            <label for="name">Nimi</label><br>
            <input id="name" name="name" value="{escape(recipe["name"], quote=True)}" required><br>
            <label for="yield">Annokset</label><br>
            <input id="yield" name="yield_value" value="{escape(recipe["yield"] or "", quote=True)}"><br>
            <label for="ingredients">Ainesosat, yksi riville</label><br>
            <textarea id="ingredients" name="ingredients" rows="10" cols="60" required>{escape(ingredients)}</textarea><br>
            <label for="instructions">Valmistusohje, yksi vaihe riville</label><br>
            <textarea id="instructions" name="instructions" rows="10" cols="60">{escape(instructions)}</textarea><br>
            <button type="submit">Esikatsele korjaukset</button>
        </form>
        """

    preview = ""
    if prepared is not None:
        rows = "".join(
            f"<li>{escape(item['raw'])} → {escape(item['name'])}"
            f" ({escape(str(item['amount']))} {escape(item['unit'] or 'yksikkö puuttuu')})</li>"
            for item in prepared["ingredients"]
        )
        untracked = "".join(
            f"<li>{escape(item['raw'])} → {escape(item['name'])}</li>"
            for item in prepared["untracked_ingredients"]
        )
        preview = f"""
        <h2>Jäsennetyt ainesosat</h2>
        <ul>{rows}</ul>
        <h3>Ilman määrää (ei varastoseurantaa)</h3>
        <ul>{untracked}</ul>
        """

    return f"""
    <!DOCTYPE html>
    <html lang="fi">
    <head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Kuvareseptin esikatselu</title></head>
    <body>
        <h1>Kuvareseptin esikatselu</h1>
        <p>Tarkista OCR-tulos. Kuvareseptin tallennus Grocyyn ei ole vielä käytettävissä;
        tietoja ei säilytetä, kun poistut sivulta.</p>
        {notice}
        <form method="post" action="/image/text">
            <label for="text">Kuvasta tunnistettu teksti</label><br>
            <textarea id="text" name="text" rows="15" cols="60" required>{escape(text)}</textarea><br>
            <p>Tekstin uudelleenjäsentäminen korvaa alla olevat reseptikentät.</p>
            <button type="submit">Jäsennä teksti uudelleen</button>
        </form>
        {fields}
        {preview}
        <p><a href="/">← Takaisin</a></p>
    </body></html>
    """


def validate_image(data):
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(data)) as image:
                if image.format not in IMAGE_FORMATS:
                    raise ValueError("Valitse JPEG- tai PNG-kuva.")
                if image.width * image.height > MAX_IMAGE_PIXELS:
                    raise ValueError("Kuva on liian suuri (enintään 20 megapikseliä).")
                image.verify()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError,
            Image.DecompressionBombWarning) as error:
        raise ValueError("Kuvaa ei voi avata tai se on liian suuri.") from error


@app.post("/image", response_class=HTMLResponse)
async def image_upload(image: UploadFile = File(...)):
    try:
        data = await image.read(MAX_IMAGE_BYTES + 1)
        if len(data) > MAX_IMAGE_BYTES:
            return image_error("Kuva on liian suuri (enintään 10 Mt).")
        await run_in_threadpool(validate_image, data)
        text = await run_in_threadpool(read_image_text, BytesIO(data))
        if not text.strip():
            return image_error("Kuvasta ei saatu luettua tekstiä.")
        return image_text_preview(text)
    except ValueError as error:
        return image_error(str(error))
    except Exception:
        logger.exception("Kuvan OCR epäonnistui")
        return image_error("Kuvan tekstintunnistus epäonnistui. Tarkista palvelimen loki.", 500)
    finally:
        await image.close()


@app.post("/image/text", response_class=HTMLResponse)
def image_text_preview(text: str = Form(...)):
    try:
        recipe = parse_ocr_recipe(text)
    except ValueError as error:
        return HTMLResponse(image_editor(text, message=str(error)), status_code=400)
    return HTMLResponse(image_editor(text, recipe))


@app.post("/image/preview", response_class=HTMLResponse)
def image_recipe_preview(
    name: str = Form(...),
    ingredients: str = Form(...),
    yield_value: str = Form(""),
    instructions: str = Form(""),
    source_text: str = Form(""),
):
    recipe = {
        "name": name.strip(),
        "description": None,
        "yield": yield_value.strip() or None,
        "ingredients": [line.strip() for line in ingredients.splitlines() if line.strip()],
        "instructions": [line.strip() for line in instructions.splitlines() if line.strip()],
    }
    text = source_text or "\n".join(
        [recipe["name"], recipe["yield"] or "", "Ainekset", ingredients, "Valmistus", instructions]
    )
    if not recipe["name"] or not recipe["ingredients"]:
        return HTMLResponse(
            image_editor(text, recipe, "Anna reseptin nimi ja vähintään yksi ainesosa."),
            status_code=400,
        )
    try:
        prepared = prepare_recipe(recipe)
    except (ValueError, ZeroDivisionError):
        return HTMLResponse(
            image_editor(text, recipe, "Ainesosien jäsentäminen epäonnistui. Tarkista määrät."),
            status_code=400,
        )
    except Exception:
        logger.exception("Kuvareseptin jäsentäminen epäonnistui")
        return HTMLResponse(
            image_editor(text, recipe, "Reseptin jäsentäminen epäonnistui. Tarkista tiedot ja palvelimen loki."),
            status_code=500,
        )
    return HTMLResponse(image_editor(text, recipe, prepared=prepared))


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

        # GROCY_URL on sisäverkon (kontti-verkon) osoite, jota selain ei
        # pysty avaamaan - linkkiä varten tarvitaan julkinen osoite erikseen.
        grocy_browser_base = os.environ.get("GROCY_PUBLIC_URL") or os.environ["GROCY_URL"]
        grocy_new_product_url = grocy_browser_base.rstrip("/") + "/product/new"

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


