#!/usr/bin/env python3
"""
Generoi testikuvia kuvareseptien tuonnin testaamiseen.
Luo kuviin tekstiä, joka OCR:n tulee pystyä lukemaan.
"""

from PIL import Image, ImageDraw, ImageFont
import os


def create_test_recipe_image(filename, recipe_text, width=800, height=600):
    """Luo testikuva, johon on kirjoitettu reseptin teksti."""
    img = Image.new('RGB', (width, height), color='white')
    draw = ImageDraw.Draw(img)
    
    # Yritä käyttää oletusfonttia - fallback jos käytettävissä
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 20)
        small_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 16)
    except (OSError, IOError):
        # Käytä oletusfonttia
        font = ImageFont.load_default()
        small_font = font
    
    # Piirrä teksti kuvaan
    y = 20
    line_height = 25
    
    for line in recipe_text.split('\n'):
        draw.text((20, y), line, fill='black', font=font if y < 100 else small_font)
        y += line_height
    
    img.save(filename)
    print(f"✓ Luotiin {filename}")


def main():
    fixtures_dir = os.path.dirname(os.path.abspath(__file__))
    images_dir = os.path.join(fixtures_dir, 'images')
    os.makedirs(images_dir, exist_ok=True)
    
    # Testikuva 1: Yksinkertainen omenapaistos
    recipe1 = """Omenapaistos
4 annosta

Ainekset
3 dl kaurahiutaleita
2 omenaa
100 g voita
100 g sokeria

Valmistus
Sekoita ainekset keskenään.
Paista uunissa 180 astetta 30 minuuttia.
Jäähdytä huoneenlämmössä."""
    
    create_test_recipe_image(
        os.path.join(images_dir, 'simple_recipe.png'),
        recipe1
    )
    
    # Testikuva 2: Pannukakku
    recipe2 = """PANNUKAKKU
(4 annosta)

Tarvikkeet
2 dl maitoa
3 munaa
2 dl vehnäjauhoja
1 tl suolaa
2 rkl sokeria
3 rkl voita

Tee näin
Sekoita maidon kanssa munat ja jauhot.
Lisää suola ja sokeri.
Vatkaa kunnes sileää.
Paista 200 asteessa."""
    
    create_test_recipe_image(
        os.path.join(images_dir, 'pannukakku.png'),
        recipe2
    )
    
    # Testikuva 3: Liharesepti
    recipe3 = """Lihapullat
(2 annosta)

Raaka-aineet
500 g jauhelihaa
1 kpl sipuli
2 dl leivän murua
1 kpl muna
2 tl suolaa
1 tl mustapippuria

Valmistusohje
Silppua sipuli ja sekoita lihaansa.
Lisää leivän murua, muna ja mausteet.
Muovaa palloksi.
Paista pannulla kunnes ruskea."""
    
    create_test_recipe_image(
        os.path.join(images_dir, 'lihapullat.png'),
        recipe3
    )
    
    print("\n✓ Kaikki testikuvat luotiin onnistuneesti!")


if __name__ == '__main__':
    main()
