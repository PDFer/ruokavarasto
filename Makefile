.PHONY: help test test-unit test-integration test-all test-docker generate-images docker-up docker-down coverage clean

help:
	@echo "Resepti-importteri - Testien käyttö"
	@echo ""
	@echo "Yksikkötestit:"
	@echo "  make test-unit          Aja yksikkötestit (ilman OCR)"
	@echo "  make test-integration   Aja integraatiotestit (ilman Grocy)"
	@echo "  make test               Aja kaikki paikalliset testit"
	@echo ""
	@echo "Docker-testit:"
	@echo "  make docker-up          Käynnistä Docker Compose -testiympäristö"
	@echo "  make docker-down        Pysäytä Docker Compose -testiympäristö"
	@echo "  make test-docker        Aja testit Docker-ympäristössä"
	@echo ""
	@echo "Muut:"
	@echo "  make generate-images    Generoi testikuvat"
	@echo "  make coverage           Näytä testien kattavuus"
	@echo "  make clean              Siivoa väliaikaistiedostot"

# Yksikkötestit
test-unit:
	@echo "🧪 Ajossa yksikkötestejä..."
	python -m pytest tests/test_image_ocr.py -v

# Integraatiotestit
test-integration:
	@echo "🔗 Ajossa integraatiotestejä..."
	python -m pytest tests/test_image_integration.py -v

# Kaikki paikalliset testit
test: test-unit test-integration
	@echo "✓ Kaikki testit menivät läpi"

# Docker Compose -ympäristö
docker-up:
	@echo "🐳 Käynnistetään Docker Compose -testiympäristö..."
	docker-compose -f docker-compose.test.yml up -d
	@echo "⏳ Odotetaan Grocy:n valmistumista (30-60 sekuntia)..."
	@sleep 10
	@docker-compose -f docker-compose.test.yml ps

docker-down:
	@echo "🛑 Pysäytetään Docker Compose -testiympäristö..."
	docker-compose -f docker-compose.test.yml down -v
	@echo "✓ Testiympäristö pysäytetty"

# Docker-testit
test-docker: docker-up
	@echo "🐳 Ajossa testejä Docker-ympäristössä..."
	docker-compose -f docker-compose.test.yml exec -T recipe-importer-test \
		python -m pytest tests/ -v --tb=short
	@$(MAKE) docker-down

# Testikuvien generointi
generate-images:
	@echo "🎨 Generoidaan testikuvia..."
	python tests/fixtures/generate_test_images.py
	@echo "✓ Testikuvat generoitu"

# Coverage-raportti
coverage:
	@echo "📊 Generoidaan coverage-raporttia..."
	python -m pytest tests/ \
		--cov=recipe_import \
		--cov=recipe_importer \
		--cov=normalizer \
		--cov-report=html \
		--cov-report=term-missing
	@echo "✓ Coverage-raportti: htmlcov/index.html"

# Siivous
clean:
	@echo "🧹 Siivotaan väliaikaistiedostot..."
	rm -rf .pytest_cache htmlcov .coverage *.pyc __pycache__
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	@echo "✓ Siivottu"
