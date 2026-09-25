import os
import secrets
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.ai.schema import parse_json, validate
from app.collector.hankyung import collect
from app.db.repository import Repository
from app.services.top10 import calculate
from app.services.universe import ensure_universe


repo = Repository(os.getenv("DATABASE_PATH", "data/stock50.db"))
repo.init()

app = FastAPI(title="stock50-7")
app.mount("/static", StaticFiles(directory="frontend"), name="static")


class RawAnalysis(BaseModel):
    raw: str


class PromptRequest(BaseModel):
    ids: list[int] = []


def make_request_id():
    now = datetime.now(ZoneInfo("Asia/Seoul"))
    return now.strftime("%Y%m%d-%H%M%S-") + secrets.token_hex(2)


def make_prompt(request_id, articles):
    blocks = []
    for i, article in enumerate(articles, 1):
        content = (
            article.get("content_excerpt")
            or article.get("snippet")
            or ""
        )[:2500]
        blocks.append(
            "\n".join(
                [
                    f"[기사 {i}]",
                    f"article_id: {article['id']}",
                    f"제목: {article['title']}",
                    f"발행시각: {article.get('published_at') or '-'}",
                    f"섹션: {article.get('section') or '-'}",
                    f"URL: {article['url']}",
                    "핵심 내용:",
                    content,
                ]
            )
        )

    instruction = f"""stock50-7 한국경제 뉴스 AI 분석

analysis_request_id: {request_id}

아래 기사 후보만 분석한다.
시장 영향도가 높은 비중복 기사 최대 20개를 선택한다.
동일 사건을 반복 기사로 여러 번 부풀리지 않는다.

[출력 규칙]
- 설명, Markdown 코드블록, source_citation 없이 파싱 가능한 JSON 객체만 반환한다.
- analysis_request_id는 반드시 위 값을 그대로 사용한다.
- analysis_time은 ISO8601 형식이다.
- 각 기사 summary는 정확히 3개의 문자열이다.
- importance는 1~5 정수다.
- confidence는 HIGH, MEDIUM, LOW 중 하나다.
- beneficiaries와 losers는 기사당 각각 최대 3개다.
- 종목 impact는 1~5 정수다.
- reason에는 해당 기사로부터 발생하는 직접적인 수혜/피해 경로를 한 문장으로 적는다.
- 한국 상장주뿐 아니라 미국 상장주도 포함할 수 있다.
- 한국 주식: code는 6자리 숫자, market은 KOSPI 또는 KOSDAQ.
- 미국 주식: code는 실제 티커(예: NVDA, MSFT), market은 NASDAQ, NYSE, NYSEAMERICAN 중 하나.
- ETF/ETN은 제외하고 실제 상장 기업만 선택한다.
- 기사와 직접적인 연결이 약하면 종목을 억지로 넣지 않는다.
- 전체 TOP10은 AI가 만들지 않는다. 서버가 결정론적으로 계산한다.
- 문자열 안의 큰따옴표는 표준 JSON 규칙에 맞게 escape한다.

[JSON 형식]
{{
  "analysis_request_id": "{request_id}",
  "analysis_time": "2026-09-25T16:00:00+09:00",
  "articles": [
    {{
      "article_id": 1,
      "title": "기사 제목",
      "importance": 5,
      "confidence": "HIGH",
      "summary": ["요약1", "요약2", "요약3"],
      "beneficiaries": [
        {{
          "name": "NVIDIA",
          "code": "NVDA",
          "market": "NASDAQ",
          "impact": 5,
          "reason": "수혜 이유"
        }}
      ],
      "losers": []
    }}
  ]
}}

[기사 후보]
"""
    return instruction + "\n\n".join(blocks)


def get_snapshot_payload(analysis_id):
    rows = repo.snapshot(analysis_id)
    if not rows:
        raise HTTPException(404, "Snapshot을 찾을 수 없습니다.")
    return {"articles": rows, "top10": calculate(rows)}


def validate_analysis(raw):
    parsed = parse_json(raw)
    request_id = str(parsed.get("analysis_request_id") or "").strip()
    if not request_id:
        raise ValueError("analysis_request_id가 필요합니다.")
    if not repo.request_exists(request_id):
        raise ValueError("알 수 없는 analysis_request_id입니다. AI 분석 복사부터 다시 실행하세요.")
    article_ids = repo.request_article_ids(request_id)
    if not article_ids:
        raise ValueError("해당 analysis_request_id에 연결된 기사 snapshot이 없습니다.")
    return validate(raw, article_ids, repo.universe(), expected_request_id=request_id)


@app.get("/health")
def health():
    return {"status": "ok", "provider": "manual"}


@app.get("/")
def index():
    return FileResponse("frontend/index.html")


@app.get("/api/state")
def state():
    # Initial page load must stay lightweight.  The browser only needs the
    # article count plus the 50 candidate rows; full article bodies remain in
    # SQLite and are read server-side when the AI prompt is generated.
    snapshots = repo.snapshots()
    latest = get_snapshot_payload(snapshots[0]["id"]) if snapshots else None
    article_count = repo.article_count()
    return {
        "article_count": article_count,
        "articles": [],
        "candidates": repo.candidate_summaries(),
        "snapshots": snapshots[:100],
        "latest": latest,
    }


@app.post("/api/collect")
async def run_collect():
    universe = await ensure_universe(repo)
    result = await collect(repo)
    return {
        "fetched": result["new"],
        "processed": result["processed"],
        "articles": result["total"],
        "candidates": result["candidates"],
        "auth_ok": result.get("auth_ok", False),
        "auth_refreshed": result.get("auth_refreshed", False),
        "cookie_count": result.get("cookie_count", 0),
        "universe": universe,
    }


@app.post("/api/prompt")
def prompt(body: PromptRequest):
    selected = {int(x) for x in body.ids}
    if not selected:
        selected = {a["id"] for a in repo.candidates()[:50]}

    articles = [a for a in repo.articles() if a["id"] in selected]
    articles.sort(key=lambda a: (-a["importance_score"], a["id"]))
    if not articles:
        raise HTTPException(400, "선택된 기사가 없습니다.")

    request_id = make_request_id()
    text = make_prompt(request_id, articles)
    repo.create_ai_request(request_id, [a["id"] for a in articles], text)
    return {"analysis_request_id": request_id, "text": text}


# 이전 프론트엔드와의 호환용. 새 프론트엔드는 POST를 사용한다.
@app.get("/api/prompt")
def prompt_legacy(ids: str = ""):
    selected = [int(x) for x in ids.split(",") if x.isdigit()]
    return prompt(PromptRequest(ids=selected))


@app.post("/api/analysis/validate")
def check(body: RawAnalysis):
    try:
        payload = validate_analysis(body.raw)
        return {"valid": True, "data": payload}
    except ValueError as exc:
        raise HTTPException(422, str(exc))


@app.post("/api/analysis/save")
def save(body: RawAnalysis):
    try:
        payload = validate_analysis(body.raw)
        analysis_id = repo.save_analysis(payload)
        return {"id": analysis_id}
    except ValueError as exc:
        raise HTTPException(422, str(exc))


@app.get("/api/snapshot/{analysis_id}")
def snapshot(analysis_id: int):
    return get_snapshot_payload(analysis_id)
