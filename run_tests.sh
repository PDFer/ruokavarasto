#!/bin/bash
# Skripti testien ajamiseen ja testiympäristön hallintaan

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Värit
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

print_header() {
    echo -e "\n${BLUE}=== $1 ===${NC}\n"
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_info() {
    echo -e "${YELLOW}ℹ $1${NC}"
}

# Pää-menu
show_menu() {
    print_header "Resepti-importteri - Testiympäristö"
    echo "1. Aja yksikkötestit (ilman OCR:ta)"
    echo "2. Aja integraatiotestit (ilman Grocy:ta)"
    echo "3. Generoi testikuvat"
    echo "4. Käynnistä Docker Compose -testiympäristö"
    echo "5. Pysäytä Docker Compose -testiympäristö"
    echo "6. Aja kaikki testit (Docker-ympäristöissä)"
    echo "7. Näytä testien kattavuus"
    echo "0. Poistu"
    echo
    read -p "Valitse vaihtoehto (0-7): " choice
}

# Yksikkötestit
run_unit_tests() {
    print_header "Ajossa yksikkötestejä"
    if ! python -m pytest tests/test_image_ocr.py -v; then
        print_error "Yksikkötestit epäonnistuivat"
        exit 1
    fi
    print_success "Yksikkötestit menivät läpi"
}

# Integraatiotestit ilman Grocy:ta
run_integration_tests() {
    print_header "Ajossa integraatiotestejä (ilman Grocy:ta)"
    if ! python -m pytest tests/test_image_integration.py -v; then
        print_error "Integraatiotestit epäonnistuivat"
        exit 1
    fi
    print_success "Integraatiotestit menivät läpi"
}

# Generoi testikuvat
generate_test_images() {
    print_header "Generoidaan testikuvia"
    if ! python tests/fixtures/generate_test_images.py; then
        print_error "Testikuvien generointi epäonnistui"
        exit 1
    fi
    print_success "Testikuvat generoitu"
}

# Käynnistä Docker Compose
start_docker() {
    print_header "Käynnistetään Docker Compose -testiympäristö"
    if ! command -v docker-compose &> /dev/null; then
        print_error "docker-compose ei ole asennettu"
        exit 1
    fi
    
    docker-compose -f docker-compose.test.yml up -d
    print_info "Odotetaan, että Grocy on valmis (noin 30-60 sekuntia)..."
    
    # Odota Grocy:n terveystarkkailua
    local max_attempts=30
    local attempt=0
    while [ $attempt -lt $max_attempts ]; do
        if docker-compose -f docker-compose.test.yml exec -T grocy curl -f http://localhost:80/api/system/info > /dev/null 2>&1; then
            print_success "Grocy on valmis!"
            return 0
        fi
        attempt=$((attempt + 1))
        sleep 2
    done
    
    print_error "Grocy ei vastannut ajoissa"
    docker-compose -f docker-compose.test.yml logs grocy
    exit 1
}

# Pysäytä Docker Compose
stop_docker() {
    print_header "Pysäytetään Docker Compose -testiympäristö"
    if ! command -v docker-compose &> /dev/null; then
        print_error "docker-compose ei ole asennettu"
        exit 1
    fi
    
    docker-compose -f docker-compose.test.yml down -v
    print_success "Docker Compose -testiympäristö pysäytetty"
}

# Aja kaikki testit Docker:issa
run_all_tests_docker() {
    print_header "Ajossa kaikkia testejä Docker-ympäristöissä"
    
    start_docker
    
    print_header "Ajossa testejä recipe-importer -kontissa"
    docker-compose -f docker-compose.test.yml exec -T recipe-importer-test \
        python -m pytest tests/ -v --tb=short
    
    if [ $? -eq 0 ]; then
        print_success "Kaikki testit menivät läpi"
    else
        print_error "Jotkut testit epäonnistuivat"
    fi
    
    stop_docker
}

# Näytä testien kattavuus
show_coverage() {
    print_header "Generoidaan coverage-raportti"
    
    if ! command -v coverage &> /dev/null; then
        print_info "coverage ei ole asennettu, asennetaan..."
        pip install -q coverage
    fi
    
    python -m pytest tests/ \
        --cov=recipe_import \
        --cov=recipe_importer \
        --cov=normalizer \
        --cov-report=html \
        --cov-report=term-missing
    
    print_success "Coverage-raportti generoitu: htmlcov/index.html"
    
    # Yritä avata raportti
    if command -v xdg-open &> /dev/null; then
        xdg-open htmlcov/index.html
    elif command -v open &> /dev/null; then
        open htmlcov/index.html
    fi
}

# Pääsilmukka
while true; do
    show_menu
    
    case $choice in
        1)
            run_unit_tests
            ;;
        2)
            run_integration_tests
            ;;
        3)
            generate_test_images
            ;;
        4)
            start_docker
            ;;
        5)
            stop_docker
            ;;
        6)
            run_all_tests_docker
            ;;
        7)
            show_coverage
            ;;
        0)
            print_info "Poistutaan"
            exit 0
            ;;
        *)
            print_error "Virheellinen valinta"
            ;;
    esac
    
    read -p "Paina Enter jatkaaksesi..."
done
