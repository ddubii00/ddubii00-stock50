# stock50-7

한국경제의 공개 RSS를 수집하고, 사용자가 ChatGPT에서 수동 분석한 JSON을 검증·저장하여 수혜/피해 종목을 계산하는 독립 웹앱입니다. LLM API는 사용하지 않습니다.

## Local run

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m unittest discover -s tests -v
DATABASE_PATH=data/stock50.db .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8050
```

`http://127.0.0.1:8050/stock50-7/health` 를 확인하세요. Nginx가 `/stock50-7/` 접두사를 upstream에 전달하는 구성입니다.

## Oracle deployment

다른 앱이나 그 환경 파일은 건드리지 않습니다. 먼저 포트 충돌을 확인하고 빈 포트를 골라 아래의 `8050`을 그 번호로 바꾸세요.

```bash
sudo mkdir -p /var/www/stock50-7
sudo chown -R $USER:$USER /var/www/stock50-7
cd /var/www/stock50-7
# 이 프로젝트 파일을 배포한 뒤 실행
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
mkdir -p data logs
sudo tee /etc/systemd/system/stock50-7.service >/dev/null <<'EOF'
[Unit]
Description=stock50-7 manual news analysis
After=network.target
[Service]
WorkingDirectory=/var/www/stock50-7
Environment=DATABASE_PATH=/var/www/stock50-7/data/stock50.db
ExecStart=/var/www/stock50-7/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8050 --proxy-headers
Restart=always
User=ubuntu
[Install]
WantedBy=multi-user.target
EOF
sudo systemctl daemon-reload
sudo systemctl enable --now stock50-7
```

Nginx `location /stock50-7/ { proxy_pass http://127.0.0.1:8050/; proxy_set_header Host $host; proxy_set_header X-Forwarded-Prefix /stock50-7; }` 를 사이트 설정에 추가한 후 `sudo nginx -t && sudo systemctl reload nginx` 를 실행하세요.
