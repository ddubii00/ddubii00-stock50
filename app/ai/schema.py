import json
import re

try:
    from json_repair import repair_json
except Exception:
    repair_json = None

CONF = {"HIGH", "MEDIUM", "LOW"}
KR_MARKETS = {"KOSPI", "KOSDAQ"}
US_MARKETS = {"NASDAQ", "NYSE", "NYSEAMERICAN"}


def strip_fence(text):
    text = str(text or "").strip()
    text = re.sub(r"^\s*```(?:json)?\s*", "", text, flags=re.I)
    text = re.sub(r"\s*```\s*$", "", text, flags=re.I)
    return text.strip()


def sanitize_ai_json_text(text):
    """Remove ChatGPT UI citation artifacts before JSON parsing."""
    text = strip_fence(text)
    cleaned = []
    for line in text.splitlines():
        stripped = line.strip()
        if re.match(r'^"source_citation"\s*:', stripped):
            continue
        if "chatgpt-content-reference" in stripped:
            continue
        cleaned.append(line)
    return "\n".join(cleaned).strip()


def parse_json(raw):
    cleaned = sanitize_ai_json_text(raw)
    if not cleaned:
        raise ValueError("JSON 내용이 비어 있습니다.")

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as first_error:
        if repair_json is None:
            raise ValueError(
                f"JSON 문법 오류: {first_error.msg} "
                f"(line {first_error.lineno}, column {first_error.colno})"
            )
        try:
            repaired = repair_json(cleaned)
            data = json.loads(repaired) if isinstance(repaired, str) else repaired
        except Exception:
            raise ValueError(
                f"JSON 문법 오류: {first_error.msg} "
                f"(line {first_error.lineno}, column {first_error.colno})"
            )

    if isinstance(data, str):
        inner = sanitize_ai_json_text(data)
        try:
            data = json.loads(inner)
        except Exception as exc:
            raise ValueError(f"JSON 전체 문자열의 내부 파싱에 실패했습니다: {exc}")

    if not isinstance(data, dict):
        raise ValueError("최상위 JSON은 객체({})여야 합니다.")
    return data


def _normalize_code(code):
    code = str(code or "").strip().upper()
    if code.isdigit():
        return code.zfill(6)
    return code


def validate(raw, article_ids, universe, expected_request_id=None):
    data = parse_json(raw)

    request_id = str(data.get("analysis_request_id") or "").strip()
    if not request_id:
        raise ValueError("analysis_request_id가 필요합니다.")
    if expected_request_id and request_id != expected_request_id:
        raise ValueError("analysis_request_id가 AI 분석 요청과 일치하지 않습니다.")

    if not isinstance(data.get("analysis_time"), str) or not data["analysis_time"].strip():
        raise ValueError("analysis_time이 필요합니다.")

    articles = data.get("articles")
    if not isinstance(articles, list):
        raise ValueError("articles 배열이 필요합니다.")
    if len(articles) > 20:
        raise ValueError("articles는 최대 20개입니다.")

    names = {}
    codes = {}
    for stock in universe:
        code = _normalize_code(stock["code"])
        item = {**stock, "code": code, "market": str(stock["market"]).upper()}
        codes[code] = item
        names.setdefault(str(stock["name"]).strip(), []).append(item)

    seen_ids = set()
    for article in articles:
        aid = article.get("article_id")
        if aid not in article_ids:
            raise ValueError(f"기사 ID {aid}: 해당 AI 분석 요청에 포함되지 않은 article_id입니다.")
        if aid in seen_ids:
            raise ValueError(f"기사 ID {aid}: 중복 article_id입니다.")
        seen_ids.add(aid)

        if not isinstance(article.get("title"), str) or not article["title"].strip():
            raise ValueError(f"기사 ID {aid}: title이 필요합니다.")
        if not isinstance(article.get("summary"), list) or len(article["summary"]) != 3:
            raise ValueError(f"기사 ID {aid}: summary는 정확히 3개여야 합니다.")
        if not all(isinstance(x, str) and x.strip() for x in article["summary"]):
            raise ValueError(f"기사 ID {aid}: summary 3개는 모두 문자열이어야 합니다.")

        importance = article.get("importance")
        if isinstance(importance, bool) or not isinstance(importance, int) or not 1 <= importance <= 5:
            raise ValueError(f"기사 ID {aid}: importance는 1~5 정수여야 합니다.")
        if article.get("confidence") not in CONF:
            raise ValueError(f"기사 ID {aid}: confidence는 HIGH/MEDIUM/LOW여야 합니다.")

        seen_stocks = set()
        for side in ("beneficiaries", "losers"):
            stocks = article.get(side, [])
            if not isinstance(stocks, list) or len(stocks) > 3:
                raise ValueError(f"기사 ID {aid}: {side}는 0~3개여야 합니다.")

            for stock in stocks:
                if not isinstance(stock, dict):
                    raise ValueError(f"기사 ID {aid}: {side} 종목 형식이 잘못되었습니다.")

                code = _normalize_code(stock.get("code"))
                name = str(stock.get("name") or "").strip()

                if not code and name in names and len(names[name]) == 1:
                    ref = names[name][0]
                    code = ref["code"]
                    stock["code"] = code

                ref = codes.get(code)
                if not ref:
                    raise ValueError(f"기사 ID {aid}: 잘못된 종목코드/티커 {code}")

                market = ref["market"]
                if market not in KR_MARKETS | US_MARKETS:
                    raise ValueError(f"기사 ID {aid}: 지원하지 않는 시장 {market}")

                stock["code"] = code
                stock["market"] = market
                if market in KR_MARKETS:
                    stock["name"] = ref["name"]
                elif not name:
                    stock["name"] = ref["name"]
                else:
                    stock["name"] = name

                impact = stock.get("impact")
                if isinstance(impact, bool) or not isinstance(impact, int) or not 1 <= impact <= 5:
                    raise ValueError(
                        f"기사 ID {aid}: {stock['name']} impact는 1~5 정수여야 합니다."
                    )

                reason = stock.get("reason")
                if not isinstance(reason, str) or not reason.strip():
                    raise ValueError(f"기사 ID {aid}: {stock['name']} reason이 필요합니다.")

                key = code
                if key in seen_stocks:
                    raise ValueError(f"기사 ID {aid}: 중복 종목 {stock['name']}")
                seen_stocks.add(key)

    return data
