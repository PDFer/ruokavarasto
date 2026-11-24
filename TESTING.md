# 🚀 Testiympäristön pika-aloitus

Tämä dokumentaatio auttaa sinua pystyttämään ja käyttämään resepti-importterin testiympäristöä.

## 📋 Sisällysluettelo

- [Asennus](#asennus)
- [Nopea aloitus](#nopea-aloitus)
- [Testien ajaminen](#testien-ajaminen)
- [Docker-testiympäristö](#docker-testiympäristö)
- [Usein kysytyt kysymykset](#usein-kysytyt-kysymykset)

## 🔧 Asennus

### 1. Projektin riippuvuuksien asennus

```bash
# Asenna Python-riippuvuudet
pip install pytest pytest-asyncio recipe-scrapers grocy-mcp Pillow

# OCR:lle (valinnainen)
# macOS:
brew install tesseract
pip install pytesseract

# Ubuntu/Debian:
sudo apt-get install tesseract-ocr tesseract-ocr-fin
pip install pytesseract

# Fedora:
sudo dnf install tesseract
pip install pytesseract
```

### 2. Testikuvien generointi

```bash
# Generoi testikuvat fixtures/images/ -kansioon
python tests/fixtures/generate_test_images.py
```

Tai käytä Makefile:ia:

```bash
make generate-images
```

## 🎯 Nopea aloitus

### Yksiköt- ja integraatiotestit (ilman Grocy:ta)

```bash
# Aja kaikki paikalliset testit
make test

# Tai yksitellen:
make test-unit        # Vain yksikkötestit
make test-integration # Vain integraatiotestit
```

### Full-stack testit (Grocy-serverin kanssa)

```bash
# Käynnistä Docker Compose -testiympäristö
make docker-up

# Aja testit Docker-ympäristössä
make test-docker

# Tai
docker-compose -f docker-compose.test.yml exec recipe-importer-test \
  python -m pytest tests/ -v
```

## 📊 Testien ajaminen

### Perus pytest-komennot

```bash
# Kaikki testit
pytest tests/

# Vain tietyn tiedoston testit
pytest tests/test_image_integration.py -v

# Vain tietyn luokan testit
pytest tests/test_image_integration.py::RecipePreparationIntegrationTests -v

# Vain tietyn testifunktion testit
pytest tests/test_image_integration.py::RecipePreparationIntegrationTests::test_parse_yield_decimal -v

# Testit merkitsijöillä
pytest tests/ -m "not integration"  # Ohita integraatiotestit
pytest tests/ -m "integration"      # Vain integraatiotestit

# Coverage-raportti
pytest tests/ --cov=recipe_import --cov-report=html
open htmlcov/index.html
```

### Makefile-komennot

```bash
make test              # Aja kaikki paikalliset testit
make test-unit         # Aja vain yksikkötestit
make test-integration  # Aja vain integraatiotestit
make coverage          # Näytä coverage-raportti
make clean             # Siivoa väliaikaistiedostot
```

## 🐳 Docker-testiympäristö

### Käynnistäminen

```bash
# Käynnistä Grocy ja muut palvelut
docker-compose -f docker-compose.test.yml up -d

# Tarkista palvelut
docker-compose -f docker-compose.test.yml ps

# Tarkista Grocy:n lokit
docker-compose -f docker-compose.test.yml logs grocy

# Pääsy Grocy:hin selaimessa
# http://localhost:8080
```

### Testien ajaminen Docker-ympäristössä

```bash
# Aja testit recipe-importer-kontissa
docker-compose -f docker-compose.test.yml exec recipe-importer-test \
  python -m pytest tests/ -v

# Tai käytä Makefile:ia
make test-docker
```

### Pysäyttäminen

```bash
# Pysäytä ja poista kontti ja tiedot
docker-compose -f docker-compose.test.yml down -v

# Tai käytä Makefile:ia
make docker-down
```

### Grocy-tietokannan nollaus

Jos Grocy ei toimi oikein:

```bash
# Poista kaikki data
docker volume rm ruokavarasto_grocy_data

# Poista kontti
docker-compose -f docker-compose.test.yml down -v

# Käynnistä uudelleen
docker-compose -f docker-compose.test.yml up -d
```

## 📈 Coverage-raportti

```bash
# Generoi coverage-raportti
make coverage

# Tai suoraan pytest:llä
pytest tests/ \
  --cov=recipe_import \
  --cov=recipe_importer \
  --cov=normalizer \
  --cov-report=html \
  --cov-report=term-missing

# Avaa raportti selaimessa
open htmlcov/index.html  # macOS
firefox htmlcov/index.html  # Linux
```

## ❓ Usein kysytyt kysymykset

### K: Mitä tehdä, jos testit epäonnistuvat?

V: Tarkista ensin lokit:
```bash
# Paikalliset testit - pyydä yksityiskohtaisempaa tulostusta
pytest tests/ -v -s

# Docker-testit - tarkista kontin lokit
docker-compose -f docker-compose.test.yml logs recipe-importer-test
docker-compose -f docker-compose.test.yml logs grocy
```

### K: Missä testikuvat sijaitsevat?

V: Testikuvat sijaitsevat `tests/fixtures/images/` -kansiossa. Ne generoidaan seuraavalla komennolla:
```bash
python tests/fixtures/generate_test_images.py
```

### K: Mitä on pitää tehdä, jos pytesseract ei ole asennettu?

V: OCR-testit ohitetaan automaattisesti. Voit asentaa pytesseract:in:
```bash
pip install pytesseract
```

Mutta tarvitset myös Tesseract-ohjelman järjestelmässä.

### K: Kuinka käyttää useita Python-versiota testeihin?

V: Käytä `tox`:ia:
```bash
pip install tox
tox
```

Muokkaa `tox.ini` -tiedostoa hallitaksesi Python-versioita.

### K: Kuinka lisätä uusia testejä?

V: Lue [tests/README.md](tests/README.md) -tiedostosta lisäohjeita.

### K: Kuinka debugata tiettyä testiä?

V: Käytä pytest:n `-s` -lipun kanssa:
```bash
pytest tests/test_image_integration.py::RecipePreparationIntegrationTests::test_parse_yield_decimal -v -s

# Tai käytä pdb:tä
pytest tests/test_image_integration.py::RecipePreparationIntegrationTests::test_parse_yield_decimal -v --pdb
```

## 📚 Lisäresurssit

- [pytest dokumentaatio](https://docs.pytest.org/)
- [unittest dokumentaatio](https://docs.python.org/3/library/unittest.html)
- [Grocy dokumentaatio](https://docs.grocy.de/)
- [Tesseract OCR dokumentaatio](https://github.com/UB-Mannheim/tesseract/wiki)
- [Docker Compose dokumentaatio](https://docs.docker.com/compose/)

---

Ongelmat? Katso [tests/README.md](tests/README.md) yksityiskohtaisempaa dokumentaatiota varten!
