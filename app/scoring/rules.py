import re

WEIGHTS = {
    "실적": 22,
    "수주": 20,
    "capex": 18,
    "투자": 13,
    "반도체": 16,
    "ai": 14,
    "hbm": 18,
    "금리": 14,
    "환율": 13,
    "관세": 16,
    "정책": 14,
    "원전": 15,
    "전력": 14,
    "배터리": 14,
    "자동차": 12,
    "방산": 15,
    "조선": 14,
    "m&a": 18,
    "인수": 15,
    "수출": 12,
    "공급부족": 18,
    "가격 상승": 14,
}
STOP = {"뉴스", "한국", "경제", "관련", "대한", "위한", "통해", "에서", "으로", "있는", "한다"}


def score(title, text=""):
    s = (title + " " + text).lower()
    return min(100, sum(v for k, v in WEIGHTS.items() if k in s))


def normalize(title):
    return re.sub(
        r"\s+",
        " ",
        re.sub(r'''[\[\]【】()"“”'·:!?,.-]''', " ", title.lower()),
    ).strip()


def tokens(title):
    return {
        x
        for x in re.findall(r"[가-힣a-z0-9]+", normalize(title))
        if len(x) > 1 and x not in STOP
    }


def similar(a, b):
    x, y = tokens(a), tokens(b)
    return bool(x and y) and len(x & y) / len(x | y) >= 0.45
