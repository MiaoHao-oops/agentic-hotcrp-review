#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
sudo apt-get update
sudo apt-get install -y php-cli php-mysql php-intl php-mbstring php-xml php-curl php-gd mariadb-server poppler-utils python3-venv
sudo systemctl start mariadb
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python scripts/bootstrap.py
sudo mariadb < data/bootstrap.sql
rm data/bootstrap.sql
echo 'Setup complete. Run ./scripts/start.sh'
