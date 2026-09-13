#!/bin/bash
set -Eeuo pipefail

cd "$(dirname "$0")"

echo "==> Tarkistetaan Git-tila"

if [[ -n "$(git status --porcelain)" ]]; then
    echo "Virhe: työhakemistossa on paikallisia muutoksia."
    echo
    git status --short
    exit 1
fi

echo "==> Haetaan GitHubista uusimmat muutokset"
git fetch origin

LOCAL=$(git rev-parse HEAD)
REMOTE=$(git rev-parse origin/main)

if [[ "$LOCAL" == "$REMOTE" ]]; then
    echo "==> Palvelimella on jo uusin versio."
    exit 0
fi

echo "==> Päivitetään versioon $REMOTE"
git pull --ff-only origin main

echo "==> Rakennetaan Docker-imaget"
docker-compose build

echo "==> Käynnistetään palvelut"
docker-compose up -d

echo
echo "==> Palveluiden tila"
docker-compose ps

echo
echo "==> Deploy valmis"