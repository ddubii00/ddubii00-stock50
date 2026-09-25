#!/usr/bin/env bash
set -euo pipefail

cd /var/www/stock50-7

echo "[1/7] GitHub main 반영"
git fetch origin
git reset --hard origin/main

echo "[2/7] Python dependency"
.venv/bin/pip install -r requirements.txt

echo "[3/7] Playwright Chromium"
.venv/bin/playwright install chromium

echo "[4/7] 문법 및 테스트"
.venv/bin/python -m py_compile app/main.py app/ai/schema.py app/services/universe.py app/services/top10.py app/collector/hankyung.py app/services/hankyung_auth.py
.venv/bin/python -m unittest discover -s tests -v

echo "[5/7] 한국 + 미국 Universe 갱신"
DATABASE_PATH=/var/www/stock50-7/data/stock50.db .venv/bin/python - <<'PY'
import asyncio
from app.db.repository import Repository
from app.services.universe import refresh_universe
repo = Repository('/var/www/stock50-7/data/stock50.db')
repo.init()
print(asyncio.run(refresh_universe(repo)))
PY

echo "[6/7] 서비스 재시작"
sudo systemctl restart stock50-7
sleep 3
sudo systemctl is-active stock50-7
curl -fsS http://127.0.0.1:8050/health
echo

echo "[7/7] Nginx 경유 확인"
curl -k -s -o /dev/null -w 'MAIN : %{http_code}\n' -H 'Host: 138.2.125.196' https://127.0.0.1/stock50-7/
curl -k -s -o /dev/null -w 'API  : %{http_code}\n' -H 'Host: 138.2.125.196' https://127.0.0.1/stock50-7/api/state
