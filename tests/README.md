# Testiympäristö - Resepti-importteri

Tämä hakemisto sisältää testejä resepti-importterille.

## 📋 Rakenteen yleiskatsaus

```
tests/
├── fixtures/                      # Testidataa ja apufunktioita
│   ├── generate_test_images.py    # Skripti testikuvien generointiin
│   ├── images/                    # Testikuvat (generoitu)
│   └── ocr_text/                  # OCR-teksti-esimerkkejä
├── integration/                   # Integraatiotestit Grocy:n kanssa
│   ├── __init__.py
│   └── test_with_grocy.py        # Full-stack testit
├── test_image_ocr.py             # Yksikkötestit OCR:lle
├── test_image_web.py             # Web-API:n testit
└── test_image_integration.py      # Integraatiotestit
```

## 🚀 Pika-aloitus

### 1. Testikuvien generointi

```bash
cd tests/fixtures
python generate_test_images.py
```

Tämä luo kolme testikuvaa:
- `simple_recipe.png` - Yksinkertainen omenapaistos
- `pannukakku.png` - Pannukakun resepti
- `lihapullat.png` - Lihapullat-resepti

### 2. Yksikkötestien ajo (ilman ulkoisia palveluita)

```bash
# Aja kaikki yksikkötestit
python -m pytest tests/ -v -m "not integration"

# Aja vain OCR-testit
python -m pytest tests/test_image_ocr.py -v

# Aja vain integraatiotestit (ilman Grocy:ta)
python -m pytest tests/test_image_integration.py -v
```

### 3. Full-stack integraatiotestit (Grocy:n kanssa)

```bash
# 1. Käynnistä test-ympäristö
docker-compose -f docker-compose.test.yml up -d

# 2. Odota, että Grocy on valmis (noin 30-60 sekuntia)
docker-compose -f docker-compose.test.yml ps

# 3. Aja integraatiotestit
docker-compose -f docker-compose.test.yml exec recipe-importer-test \
  python -m pytest tests/integration/ -v

# 4. Pysäytä test-ympäristö
docker-compose -f docker-compose.test.yml down
```

## 📝 Testien tyypit

### Yksikkötestit (`test_image_ocr.py`, `test_image_web.py`)

Testaavat yksittäisiä komponentteja erillään:
- OCR-tekstitunnistus
- Reseptin jäsentäminen
- Ainesosien normalisointi

```bash
python -m pytest tests/test_image_ocr.py -v
```

### Integraatiotestit (`test_image_integration.py`)

Testaavat komponenttien yhdessä toimimista ilman ulkoisia palveluita:
- OCR + reseptin jäsentäminen
- Reseptin valmistelu
- Annosten jäsentäminen

```bash
python -m pytest tests/test_image_integration.py -v
```

### Full-stack testit (`tests/integration/test_with_grocy.py`)

Testaavat koko workflow:ta Grocy-serverin kanssa (edellyttää Docker Compose):
- Reseptin tallennus Grocy:hin
- Ainesosien yhdistäminen Grocy-tuotteisiin
- Yksikkömappaukset

```bash
docker-compose -f docker-compose.test.yml exec recipe-importer-test \
  python -m pytest tests/integration/ -v
```

## 🛠 Testiympäristön konfiguraatio

### Muuttujat

| Muuttuja | Oletusarvo | Kuvaus |
|----------|-----------|--------|
| `GROCY_URL` | `http://grocy` | Grocy-serverin URL |
| `GROCY_API_KEY` | `demo_key` | Grocy API-avain |
| `DB_PATH` | `/app/data/normalization.db` | Normalization-tietokannan polku |
| `LOG_LEVEL` | `INFO` | Loki-taso |

### Grocy-tietokannan nollaus

Jos Grocy ei toimi oikein, nollaa se:

```bash
# Poista Grocy-data
docker volume rm ruokavarasto_grocy_data

# Poista kontti
docker-compose -f docker-compose.test.yml down -v

# Käynnistä uudelleen
docker-compose -f docker-compose.test.yml up -d
```

## 📊 Testin kattavuus

Coverage-raportin generointi:

```bash
python -m pytest tests/ --cov=recipe_import --cov=recipe_importer --cov-report=html

# Avaa raportti
open htmlcov/index.html  # macOS
firefox htmlcov/index.html  # Linux
```

## 🐛 Vianmääritys

### Tesseract ei ole asennettu

```bash
# macOS
brew install tesseract

# Ubuntu/Debian
sudo apt-get install tesseract-ocr tesseract-ocr-fin

# Fedora
sudo dnf install tesseract
```

### PIL/Pillow-virhe

```bash
pip install Pillow
```

### Grocy-yhteys epäonnistuu

```bash
# Tarkista, että kontti on käynnissä
docker-compose -f docker-compose.test.yml ps

# Tarkista lokit
docker-compose -f docker-compose.test.yml logs grocy

# Testaa yhteys
curl -H "GROCY-API-KEY: demo_key" http://localhost:8080/api/system/info
```

### Testikuvat puuttuvat

```bash
# Generoi testikuvat
python tests/fixtures/generate_test_images.py
```

## 📚 Lisäresurssit

- [pytest dokumentaatio](https://docs.pytest.org/)
- [unittest dokumentaatio](https://docs.python.org/3/library/unittest.html)
- [Grocy API dokumentaatio](https://docs.grocy.de/)
- [Tesseract OCR dokumentaatio](https://github.com/UB-Mannheim/tesseract/wiki)

## 🤝 Ohjeet kehittäjille

Kun lisäät uusia testejä:

1. Sijoita testi sopivaan tiedostoon (`test_image_integration.py` jne.)
2. Merkitse testi sopivalla merkitsijällä (`@pytest.mark.integration` jne.)
3. Käytä kuvaavaa nimea: `test_<component>_<behavior>`
4. Lisää docstring: `"""Testaa, että ..."""`
5. Varmista, että testi on itsenäinen eikä riipu muista testeista

Esimerkki:

```python
def test_ocr_finnish_recipe():
    """Testaa, että OCR lukee suomalaista tekstiä oikein."""
    image_path = fixtures_dir / "suomalainen_resepti.png"
    
    recipe = extract_recipe_from_image(image_path)
    
    assert recipe["name"] is not None
    assert len(recipe["ingredients"]) > 0
```

---

**Huomio**: Testit on käynnistetty pytest:lla. Suoraan Python-ajon sijaan käytä:

```bash
python -m pytest tests/test_image_ocr.py -v
```

Tämä varmistaa, että importit toimivat oikein.
