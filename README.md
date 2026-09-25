# stock50-7

한국경제 기사 후보를 수집하고, 사용자가 ChatGPT에서 수동 분석한 JSON을 검증·저장한 뒤 한국/미국 상장사의 뉴스 수혜·피해 TOP10을 계산하는 웹앱입니다. LLM API는 사용하지 않습니다.

## 이번 종합본 기능

- TOP10의 `기사 N건`을 클릭하면 해당 종목 점수에 반영된 기사 제목과 3줄 요약이 펼쳐집니다.
- AI 분석 후보 날짜와 snapshot 시간을 한국 시간/한글 형식으로 표시합니다.
- 수혜주/피해주는 KOSPI/KOSDAQ뿐 아니라 NASDAQ/NYSE/NYSE American 상장 기업도 허용합니다.
- 한국 주식 Universe: KIS 공식 종목 Master.
- 미국 주식 Universe: Nasdaq Trader Symbol Directory, ETF 제외.
- AI 분석 요청마다 `analysis_request_id`와 기사 snapshot을 DB에 고정합니다.
- ChatGPT UI가 삽입한 `source_citation` 때문에 JSON이 깨지는 경우 파싱 전에 제거합니다.

## 보안

다음 파일은 GitHub에 올리지 않습니다.

- `~/.config/stock50-7/hankyung-account.json`
- `~/.config/stock50-7/hankyung-cookies.json`
- SQLite DB (`data/*.db`)

계정 파일 예시는 다음 구조를 사용합니다. 실제 값은 서버에서만 저장하세요.

```json
{
  "email": "YOUR_EMAIL",
  "password": "YOUR_PASSWORD"
}
```

권한 권장값:

```bash
chmod 700 ~/.config/stock50-7
chmod 600 ~/.config/stock50-7/hankyung-account.json
chmod 600 ~/.config/stock50-7/hankyung-cookies.json
```

## Local run

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/playwright install chromium
.venv/bin/python -m unittest discover -s tests -v
DATABASE_PATH=data/stock50.db .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8050
```

## Oracle 배포

현재 서버 기준:

- project: `/var/www/stock50-7`
- systemd: `stock50-7`
- uvicorn: `127.0.0.1:8050`
- nginx: `/stock50-7/`

GitHub main 브랜치에 이 종합본을 올린 후:

```bash
cd /var/www/stock50-7
git fetch origin
git reset --hard origin/main
.venv/bin/pip install -r requirements.txt
.venv/bin/playwright install chromium
DATABASE_PATH=/var/www/stock50-7/data/stock50.db .venv/bin/python -m unittest discover -s tests -v
sudo systemctl restart stock50-7
curl -fsS http://127.0.0.1:8050/health
```

미국 종목 Universe까지 즉시 갱신하려면 아래를 한 번 실행합니다.

```bash
cd /var/www/stock50-7
DATABASE_PATH=/var/www/stock50-7/data/stock50.db .venv/bin/python - <<'PY'
import asyncio
from app.db.repository import Repository
from app.services.universe import refresh_universe
repo = Repository('/var/www/stock50-7/data/stock50.db')
repo.init()
print(asyncio.run(refresh_universe(repo)))
PY
```

그 뒤 서비스를 재시작합니다.

```bash
sudo systemctl restart stock50-7
```

## Nginx

기존 서버에서 이미 동작하는 설정은 변경할 필요가 없습니다. 기본 형태는 다음과 같습니다.

```nginx
location /stock50-7/ {
    proxy_pass http://127.0.0.1:8050/;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Prefix /stock50-7;
}
```
