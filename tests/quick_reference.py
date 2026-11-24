#!/usr/bin/env python3
"""
Quick reference -skripti testiympäristön käyttöön.
Tulosta tämä käynnistämällä: python tests/quick_reference.py
"""

def print_header(text):
    print(f"\n{'='*60}")
    print(f"  {text}")
    print(f"{'='*60}\n")

def main():
    print_header("RESEPTI-IMPORTTERI - TESTIEN QUICK REFERENCE")
    
    print("🚀 NOPEA ALOITUS\n")
    print("  # Aja kaikki testit")
    print("  make test\n")
    print("  # Aja Docker-testiympäristö")
    print("  make docker-up && make test-docker && make docker-down\n")
    
    print_header("TAVALLISIMMAT KOMENNOT")
    
    commands = [
        ("make test", "Aja kaikki paikalliset testit"),
        ("make test-unit", "Aja vain yksikkötestit"),
        ("make test-integration", "Aja integraatiotestit"),
        ("make coverage", "Näytä coverage-raportti"),
        ("make docker-up", "Käynnistä Docker-testiympäristö"),
        ("make docker-down", "Pysäytä Docker-testiympäristö"),
        ("make generate-images", "Generoi testikuvat"),
        ("make clean", "Siivoa väliaikaistiedostot"),
        ("./run_tests.sh", "Interaktiivinen menu"),
    ]
    
    for cmd, desc in commands:
        print(f"  {cmd:<35} → {desc}")
    
    print_header("PYTEST-KOMENNOT")
    
    pytest_cmds = [
        ("pytest tests/", "Aja kaikki testit"),
        ("pytest tests/ -v", "Yksityiskohtainen tulostus"),
        ("pytest tests/ -v -s", "Näytä print-lauseet"),
        ("pytest tests/test_image_integration.py -v", "Vain integraatiotestit"),
        ("pytest tests/ --co", "Listaa testit ilman ajamista"),
        ("pytest tests/ -x", "Pysäytä ensimmäisellä virheellä"),
        ("pytest tests/ -k 'yield'", "Aja testit nimellä 'yield'"),
    ]
    
    for cmd, desc in pytest_cmds:
        print(f"  {cmd:<50} → {desc}")
    
    print_header("DOCKER-KOMENNOT")
    
    docker_cmds = [
        ("docker-compose -f docker-compose.test.yml up -d", 
         "Käynnistä testiympäristö"),
        ("docker-compose -f docker-compose.test.yml ps", 
         "Näytä konttien status"),
        ("docker-compose -f docker-compose.test.yml logs grocy", 
         "Näytä Grocy:n lokit"),
        ("docker-compose -f docker-compose.test.yml exec recipe-importer-test python -m pytest tests/ -v",
         "Aja testit konteissa"),
        ("docker-compose -f docker-compose.test.yml down -v",
         "Pysäytä ja poista"),
    ]
    
    for cmd, desc in docker_cmds:
        print(f"  {cmd:<70}")
        print(f"    → {desc}\n")
    
    print_header("TIEDOSTOJEN SIJAINNIT")
    
    files = [
        ("tests/test_image_ocr.py", "Olemassa olevat yksikkötestit"),
        ("tests/test_image_integration.py", "Uudet integraatiotestit"),
        ("tests/integration/test_with_grocy.py", "Full-stack testit"),
        ("tests/fixtures/images/", "Testikuvat"),
        ("docker-compose.test.yml", "Docker-konfiguraatio"),
        ("pytest.ini", "Pytest-asetukset"),
        ("Makefile", "Makefile-komennot"),
        ("TESTING.md", "Pika-opas"),
        ("tests/README.md", "Yksityiskohtainen dokumentaatio"),
    ]
    
    for path, desc in files:
        print(f"  {path:<35} → {desc}")
    
    print_header("TESTIEN TILA")
    
    print("  ✅ 8 testia menee läpi")
    print("  ⏭️  3 testiä ohitetaan (pytesseract puuttuu)\n")
    print("  Testien jakautuminen:")
    print("    - RecipePreparationIntegrationTests (5 testia)")
    print("    - GrocyIntegrationMockTests (1 testi)")
    print("    - FullWorkflowIntegrationTests (2 testia)")
    print("    - ImageOCRIntegrationTests (3 skipped)")
    
    print_header("SEURAAVAT ASKELEET")
    
    print("  1. Aja testit: make test")
    print("  2. Tutki testidokumentaatiota: cat tests/README.md")
    print("  3. Käynnistä Docker: make docker-up")
    print("  4. Lisää uusia testejä seuraavasti:")
    print("     - Luo testitiedosto tests/test_*.py")
    print("     - Nimeä testifunktiot test_* alkuisiksi")
    print("     - Aja pytest: pytest tests/test_*.py -v")
    
    print_header("DOKUMENTAATIO")
    
    docs = [
        ("TESTING.md", "Pika-aloitus ja ohjeita"),
        ("tests/README.md", "Yksityiskohtainen testidokumentaatio"),
        ("TESTIYMPÄRISTÖ.md", "Mitä luotiin ja seuraavat askeleet"),
    ]
    
    for doc, desc in docs:
        print(f"  📖 {doc:<30} → {desc}")
    
    print_header("APUA")
    
    print("  Kysymyksiä? Katso:")
    print("    1. TESTING.md - Usein kysytyt kysymykset")
    print("    2. tests/README.md - Vianmääritys")
    print("    3. pytest --help - Pytest:n ohje")
    
    print(f"\n{'='*60}\n")

if __name__ == "__main__":
    main()
