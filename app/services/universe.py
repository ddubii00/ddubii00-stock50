import asyncio
import csv
import re
import zipfile
from datetime import datetime, timezone
from io import BytesIO, StringIO

import httpx


KIS_MASTER = {
    "KOSPI": {
        "url": "https://new.real.download.dws.co.kr/common/master/kospi_code.mst.zip",
        "member": "kospi_code.mst",
        "widths": [
            2,1,4,4,4,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,
            1,9,5,5,1,1,1,2,1,1,1,2,2,2,3,1,3,12,12,8,15,21,2,7,1,1,1,1,9,
            9,9,5,9,8,9,3,1,1,1,
        ],
        "etp_index": 12,
    },
    "KOSDAQ": {
        "url": "https://new.real.download.dws.co.kr/common/master/kosdaq_code.mst.zip",
        "member": "kosdaq_code.mst",
        "widths": [
            2,1,4,4,4,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,9,5,5,1,
            1,1,2,1,1,1,2,2,2,3,1,3,12,12,8,15,21,2,7,1,1,1,1,9,9,9,5,9,8,
            9,3,1,1,1,
        ],
        "etp_index": 8,
    },
}

NASDAQ_LISTED_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"
OTHER_LISTED_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt"

KR_RANGES = {
    "KOSPI": (600, 1300),
    "KOSDAQ": (1200, 2300),
}
US_MIN_TOTAL = 3000


def split_fixed(text, widths):
    values, pos = [], 0
    for width in widths:
        values.append(text[pos:pos + width])
        pos += width
    return values


def parse_kis_master(raw, market, widths, etp_index):
    text = raw.decode("cp949", errors="replace")
    tail_len = sum(widths)
    result = {}

    for original in text.splitlines():
        line = original.rstrip("\r\n")
        if len(line) <= tail_len + 21:
            continue
        head = line[:-tail_len]
        tail = line[-tail_len:]
        short_code = head[0:9].strip()
        name = head[21:].strip()
        fields = split_fixed(tail, widths)
        group = fields[0].strip()
        etp = fields[etp_index].strip()

        if group != "ST":
            continue
        if etp not in ("", "0"):
            continue
        if not re.fullmatch(r"\d{6}", short_code):
            continue
        if not name:
            continue

        result[short_code] = {
            "code": short_code,
            "name": name,
            "market": market,
        }
    return list(result.values())


async def download_kis_market(client, market):
    config = KIS_MASTER[market]
    response = await client.get(config["url"])
    response.raise_for_status()
    if not response.content.startswith(b"PK"):
        raise RuntimeError(f"{market} KIS Master가 ZIP 형식이 아닙니다.")

    with zipfile.ZipFile(BytesIO(response.content)) as z:
        names = z.namelist()
        member = config["member"]
        if member not in names:
            candidates = [x for x in names if x.lower().endswith(".mst")]
            if not candidates:
                raise RuntimeError(f"{market}: mst 파일이 없습니다.")
            member = candidates[0]
        raw = z.read(member)

    rows = parse_kis_master(raw, market, config["widths"], config["etp_index"])
    low, high = KR_RANGES[market]
    if not low <= len(rows) <= high:
        raise RuntimeError(f"{market} 주식 종목 수 비정상: {len(rows)}")
    return rows


def _clean_us_name(name):
    name = str(name or "").strip()
    for suffix in [
        " - Common Stock",
        " - Class A Common Stock",
        " - Class B Common Stock",
        " - Class C Common Stock",
        " Common Stock",
    ]:
        if name.endswith(suffix):
            name = name[: -len(suffix)].strip()
            break
    return name


def _parse_pipe_table(text):
    lines = [x for x in text.splitlines() if "|" in x and not x.startswith("File Creation Time")]
    if not lines:
        return []
    return list(csv.DictReader(StringIO("\n".join(lines)), delimiter="|"))


def parse_nasdaq_listed(text):
    rows = {}
    for item in _parse_pipe_table(text):
        symbol = str(item.get("Symbol") or "").strip().upper()
        if not symbol or symbol == "SYMBOL":
            continue
        if str(item.get("Test Issue") or "").strip().upper() == "Y":
            continue
        if str(item.get("ETF") or "").strip().upper() == "Y":
            continue
        if not re.fullmatch(r"[A-Z][A-Z0-9.\-]{0,9}", symbol):
            continue
        rows[symbol] = {
            "code": symbol,
            "name": _clean_us_name(item.get("Security Name")),
            "market": "NASDAQ",
        }
    return list(rows.values())


def parse_other_listed(text):
    exchange_map = {
        "N": "NYSE",
        "A": "NYSEAMERICAN",
    }
    rows = {}
    for item in _parse_pipe_table(text):
        exchange = exchange_map.get(str(item.get("Exchange") or "").strip().upper())
        if not exchange:
            continue
        if str(item.get("Test Issue") or "").strip().upper() == "Y":
            continue
        if str(item.get("ETF") or "").strip().upper() == "Y":
            continue
        symbol = str(item.get("ACT Symbol") or "").strip().upper()
        if not re.fullmatch(r"[A-Z][A-Z0-9.\-]{0,9}", symbol):
            continue
        rows[symbol] = {
            "code": symbol,
            "name": _clean_us_name(item.get("Security Name")),
            "market": exchange,
        }
    return list(rows.values())


async def download_us_universe(client):
    nasdaq_res, other_res = await asyncio.gather(
        client.get(NASDAQ_LISTED_URL),
        client.get(OTHER_LISTED_URL),
    )
    nasdaq_res.raise_for_status()
    other_res.raise_for_status()

    nasdaq = parse_nasdaq_listed(nasdaq_res.text)
    other = parse_other_listed(other_res.text)
    combined = {x["code"]: x for x in nasdaq}
    for row in other:
        combined.setdefault(row["code"], row)

    if len(combined) < US_MIN_TOTAL:
        raise RuntimeError(f"미국 주식 Universe 종목 수 비정상: {len(combined)}")
    return list(combined.values())


async def refresh_universe(repo):
    timeout = httpx.Timeout(40, connect=15)
    headers = {"User-Agent": "stock50-7/2.0"}

    async with httpx.AsyncClient(
        timeout=timeout, follow_redirects=True, headers=headers
    ) as client:
        kospi = await download_kis_market(client, "KOSPI")
        kosdaq = await download_kis_market(client, "KOSDAQ")
        us = await download_us_universe(client)

    all_rows = []
    all_rows.extend(kospi)
    all_rows.extend(kosdaq)
    all_rows.extend(us)

    unique = {}
    for stock in all_rows:
        code = stock["code"].upper()
        if code in unique:
            # 한국 6자리 숫자와 미국 티커는 충돌하지 않는다.
            if unique[code]["market"] != stock["market"]:
                raise RuntimeError(f"중복 종목코드/티커: {code}")
            continue
        unique[code] = stock

    required = ["005930", "000660", "034020", "NVDA", "MSFT", "AAPL"]
    missing = [code for code in required if code not in unique]
    if missing:
        raise RuntimeError("필수 대표 종목코드/티커 누락: " + ", ".join(missing))

    stamp = datetime.now(timezone.utc).isoformat()
    with repo.connect() as con:
        con.execute("DELETE FROM stock_universe")
        con.executemany(
            "INSERT INTO stock_universe(code,name,market,updated_at) VALUES(?,?,?,?)",
            [
                (x["code"], x["name"], x["market"], stamp)
                for x in unique.values()
            ],
        )

    counts = {
        "KOSPI": len(kospi),
        "KOSDAQ": len(kosdaq),
        "US": len(us),
    }
    return {
        "total": len(unique),
        "kospi": counts["KOSPI"],
        "kosdaq": counts["KOSDAQ"],
        "us": counts["US"],
        "source": "KIS_MASTER+NASDAQ_TRADER",
    }


async def ensure_universe(repo):
    """
    기사 수집용 Universe 확인.

    원칙:
    1. 정상적인 한국 Universe가 DB에 있으면 절대 다시 다운로드하지 않는다.
    2. 미국 Universe만 없으면 미국 종목만 별도로 추가한다.
    3. 미국 Universe 다운로드 실패가 기사 수집 실패로 이어지지 않는다.
    4. 기존 한국 Universe는 보존한다.
    """

    with repo.connect() as con:
        rows = con.execute(
            "SELECT market,count(*) AS n "
            "FROM stock_universe GROUP BY market"
        ).fetchall()

    counts = {
        x["market"]: x["n"]
        for x in rows
    }

    kospi = counts.get("KOSPI", 0)
    kosdaq = counts.get("KOSDAQ", 0)

    us = sum(
        counts.get(market, 0)
        for market in (
            "NASDAQ",
            "NYSE",
            "NYSEAMERICAN",
        )
    )

    kr_valid = (
        KR_RANGES["KOSPI"][0]
        <= kospi
        <= KR_RANGES["KOSPI"][1]
        and
        KR_RANGES["KOSDAQ"][0]
        <= kosdaq
        <= KR_RANGES["KOSDAQ"][1]
    )

    # -------------------------------------------------
    # 한국 Universe가 이미 정상인 경우
    # KIS를 다시 받지 않는다.
    # -------------------------------------------------
    if kr_valid:

        # 미국 Universe도 이미 있으면 즉시 사용
        if us >= US_MIN_TOTAL:
            return {
                "total": sum(counts.values()),
                "kospi": kospi,
                "kosdaq": kosdaq,
                "us": us,
                "source": "LOCAL_DB",
                "refreshed": False,
            }

        # 미국 Universe만 별도로 추가 시도
        try:
            timeout = httpx.Timeout(
                40,
                connect=15,
            )

            headers = {
                "User-Agent": "stock50-7/2.1"
            }

            async with httpx.AsyncClient(
                timeout=timeout,
                follow_redirects=True,
                headers=headers,
            ) as client:

                us_rows = await download_us_universe(
                    client
                )

            stamp = datetime.now(
                timezone.utc
            ).isoformat()

            with repo.connect() as con:

                # 미국시장 데이터만 제거
                # 한국 KOSPI/KOSDAQ은 절대 건드리지 않는다.
                con.execute(
                    """
                    DELETE FROM stock_universe
                    WHERE market IN (
                        'NASDAQ',
                        'NYSE',
                        'NYSEAMERICAN'
                    )
                    """
                )

                con.executemany(
                    """
                    INSERT OR REPLACE INTO stock_universe(
                        code,
                        name,
                        market,
                        updated_at
                    )
                    VALUES(?,?,?,?)
                    """,
                    [
                        (
                            x["code"],
                            x["name"],
                            x["market"],
                            stamp,
                        )
                        for x in us_rows
                    ],
                )

            return {
                "total": kospi + kosdaq + len(us_rows),
                "kospi": kospi,
                "kosdaq": kosdaq,
                "us": len(us_rows),
                "source": "LOCAL_KR+NASDAQ_TRADER",
                "refreshed": True,
            }

        except Exception as exc:

            # 미국 Universe 실패 때문에
            # 기사 수집 전체가 실패하면 안 된다.
            return {
                "total": kospi + kosdaq + us,
                "kospi": kospi,
                "kosdaq": kosdaq,
                "us": us,
                "source": "LOCAL_KR",
                "refreshed": False,
                "warning": (
                    "미국 Universe 갱신 실패: "
                    + str(exc)
                ),
            }

    # -------------------------------------------------
    # 한국 Universe 자체가 비정상일 때만
    # 전체 갱신을 시도한다.
    # -------------------------------------------------
    try:
        result = await refresh_universe(repo)
        result["refreshed"] = True
        return result

    except Exception as exc:

        # 완전히 빈 DB가 아니라면 기존 Universe로
        # 기사 수집을 계속한다.
        total = sum(counts.values())

        if total > 0:
            return {
                "total": total,
                "kospi": kospi,
                "kosdaq": kosdaq,
                "us": us,
                "source": "LOCAL_DB_FALLBACK",
                "refreshed": False,
                "warning": (
                    "Universe 전체 갱신 실패: "
                    + str(exc)
                ),
            }

        raise

