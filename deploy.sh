#!/bin/bash
set -e

cd "$(dirname "$0")"

echo "==> Haetaan muutokset GitHubista"
git pull --ff-only

echo "==> Rakennetaan Docker-imaget"
docker compose build

echo "==> Käynnistetään palvelut"
docker compose up -d

echo "==> Palveluiden tila"
docker compose ps

echo "==> Deploy valmis"
