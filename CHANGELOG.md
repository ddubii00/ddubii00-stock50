# 2026-09-25 종합본

- 종합 수혜주/피해주 TOP10의 `기사 N건`을 클릭하면 해당 종목 산정에 반영된 기사 제목과 3줄 요약을 펼쳐서 표시합니다.
- AI 분석 후보의 발행 날짜와 저장 snapshot 시간을 `ko-KR`, `Asia/Seoul` 기준 한글 날짜로 표시합니다.
- 한국 주식(KOSPI/KOSDAQ) + 미국 주식(NASDAQ/NYSE/NYSE American)을 수혜주/피해주에 함께 사용할 수 있습니다.
- 한국 Universe는 KIS 공식 종목 Master, 미국 Universe는 Nasdaq Trader Symbol Directory의 비ETF 상장주를 사용합니다.
- Top10 응답에 `market`, `article_ids`를 포함해 UI에서 기사 근거를 직접 연결합니다.
- AI 요청 snapshot과 `analysis_request_id`를 유지합니다.
- 잘못 삽입된 `source_citation`/ChatGPT UI citation 흔적을 JSON 파싱 전에 제거합니다.
- 한국경제 로그인 쿠키를 이용한 기사 본문 수집 구조를 포함합니다.
- 비밀정보/쿠키/DB는 GitHub에 포함하지 않습니다.

## 2026-09-25 performance hotfix
- `/api/state` no longer sends every article body on initial page load.
- Candidate table uses a lightweight 50-row query.
- Frontend now shows a visible loading error instead of staying on `기사 데이터를 불러오는 중…`.

## 2026-09-25 v3 initial-load reliability
- Frontend API requests use absolute `/stock50-7/` paths, so trailing-slash URL differences cannot send requests to the wrong endpoint.
- JS/CSS URLs are cache-busted.
- API fetches use `cache: no-store` and a 12-second timeout with a visible error.
- `/api/state` no longer returns article reference rows and limits snapshot metadata to 100 rows.
