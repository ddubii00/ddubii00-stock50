COEF = {"HIGH": 1.0, "MEDIUM": 0.75, "LOW": 0.5}


def calculate(rows):
    totals = {"beneficiaries": {}, "losers": {}}

    # 동일 사건(duplicate_group)에서 같은 종목이 반복 등장해도 최고 영향 1건만 반영.
    chosen = {}
    for article in rows:
        for stock in article["impacts"]:
            group = article.get("duplicate_group") or str(article["article_id"])
            key = (stock["side"], group, stock["code"])
            value = article["importance"] * stock["impact"] * COEF[article["confidence"]]
            if key not in chosen or value > chosen[key][0]:
                chosen[key] = (value, article, stock)

    for value, article, stock in chosen.values():
        bucket = totals[stock["side"]].setdefault(
            stock["code"],
            {
                "name": stock["name"],
                "code": stock["code"],
                "market": stock.get("market", ""),
                "score": 0,
                "article_ids": [],
                "high": 0,
                "reasons": [],
            },
        )
        bucket["score"] += value if stock["side"] == "beneficiaries" else -value
        if article["article_id"] not in bucket["article_ids"]:
            bucket["article_ids"].append(article["article_id"])
        bucket["high"] += int(article["confidence"] == "HIGH")
        bucket["reasons"].append(stock["reason"])

    def rank(side):
        data = totals[side].values()
        ranked = sorted(data, key=lambda x: abs(x["score"]), reverse=True)[:10]
        result = []
        for item in ranked:
            x = dict(item)
            x["articles"] = len(x["article_ids"])
            x["reason"] = x["reasons"][0] if x["reasons"] else ""
            result.append(x)
        return result

    return {
        "beneficiaries": rank("beneficiaries"),
        "losers": rank("losers"),
    }
