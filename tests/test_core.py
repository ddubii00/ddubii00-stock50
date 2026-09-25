import json
import tempfile
import unittest

from app.ai.schema import parse_json, validate
from app.db.repository import Repository
from app.scoring.rules import score, similar
from app.services.top10 import calculate


UNIVERSE = [
    {"code": "000660", "name": "SK하이닉스", "market": "KOSPI"},
    {"code": "NVDA", "name": "NVIDIA Corporation", "market": "NASDAQ"},
]


def payload(summary=None, confidence="HIGH", impact=5, code="000660", name="SK하이닉스", market="KOSPI"):
    return {
        "analysis_request_id": "REQ-1",
        "analysis_time": "2026-09-25T01:00:00Z",
        "articles": [
            {
                "article_id": 1,
                "title": "기사",
                "importance": 5,
                "confidence": confidence,
                "summary": summary or ["a", "b", "c"],
                "beneficiaries": [
                    {
                        "name": name,
                        "code": code,
                        "market": market,
                        "impact": impact,
                        "reason": "수혜",
                    }
                ],
                "losers": [],
            }
        ],
    }


class CoreTests(unittest.TestCase):
    def test_duplicate_title(self):
        self.assertTrue(similar("삼성전자 HBM 투자 확대", "삼성전자 HBM 투자 확대 발표"))

    def test_candidate_scoring(self):
        self.assertGreater(score("반도체 CAPEX 대규모 수주"), 30)

    def test_valid_json_and_fence(self):
        raw = "```json\n" + json.dumps(payload()) + "\n```"
        self.assertEqual(validate(raw, {1}, UNIVERSE, "REQ-1")["articles"][0]["article_id"], 1)

    def test_source_citation_artifact_is_removed(self):
        raw = '''{
          "analysis_request_id": "REQ-1",
          "analysis_time": "2026-09-25T01:00:00Z",
          "source_citation": ":chatgpt-content-reference{index="0"}",
          "articles": []
        }'''
        data = parse_json(raw)
        self.assertNotIn("source_citation", data)

    def test_bad_json(self):
        with self.assertRaises(ValueError):
            validate("{bad}", {1}, UNIVERSE, "REQ-1")

    def test_summary_short_and_long(self):
        for summary in (["a", "b"], ["a", "b", "c", "d"]):
            with self.assertRaises(ValueError):
                validate(json.dumps(payload(summary)), {1}, UNIVERSE, "REQ-1")

    def test_ranges_and_confidence_and_code(self):
        for change in [("importance", 0), ("impact", 6), ("confidence", "MAYBE")]:
            p = payload()
            target = p["articles"][0] if change[0] != "impact" else p["articles"][0]["beneficiaries"][0]
            target[change[0]] = change[1]
            with self.assertRaises(ValueError):
                validate(json.dumps(p), {1}, UNIVERSE, "REQ-1")
        p = payload()
        p["articles"][0]["beneficiaries"][0]["code"] = "ZZZZ"
        with self.assertRaises(ValueError):
            validate(json.dumps(p), {1}, UNIVERSE, "REQ-1")

    def test_us_stock_is_valid(self):
        p = payload(code="NVDA", name="NVIDIA", market="NASDAQ")
        data = validate(json.dumps(p), {1}, UNIVERSE, "REQ-1")
        stock = data["articles"][0]["beneficiaries"][0]
        self.assertEqual(stock["code"], "NVDA")
        self.assertEqual(stock["market"], "NASDAQ")
        self.assertEqual(stock["name"], "NVIDIA")

    def test_request_id_mismatch(self):
        with self.assertRaises(ValueError):
            validate(json.dumps(payload()), {1}, UNIVERSE, "REQ-2")

    def test_top10_coefficients_sign_and_article_ids(self):
        rows = []
        for aid, conf in [(1, "HIGH"), (2, "MEDIUM"), (3, "LOW")]:
            rows.append(
                {
                    "article_id": aid,
                    "duplicate_group": str(aid),
                    "importance": 5,
                    "confidence": conf,
                    "impacts": [
                        {
                            "side": "beneficiaries",
                            "name": "SK하이닉스",
                            "code": "000660",
                            "market": "KOSPI",
                            "impact": 4,
                            "reason": "x",
                        },
                        {
                            "side": "losers",
                            "name": "SK하이닉스",
                            "code": "000660",
                            "market": "KOSPI",
                            "impact": 1,
                            "reason": "y",
                        },
                    ],
                }
            )
        result = calculate(rows)
        self.assertEqual(result["beneficiaries"][0]["score"], 45)
        self.assertEqual(result["losers"][0]["score"], -11.25)
        self.assertEqual(result["beneficiaries"][0]["article_ids"], [1, 2, 3])

    def test_duplicate_group_not_inflated(self):
        rows = [
            {
                "article_id": i,
                "duplicate_group": "same",
                "importance": 5,
                "confidence": "HIGH",
                "impacts": [
                    {
                        "side": "beneficiaries",
                        "name": "SK하이닉스",
                        "code": "000660",
                        "market": "KOSPI",
                        "impact": 4,
                        "reason": "x",
                    }
                ],
            }
            for i in (1, 2)
        ]
        result = calculate(rows)["beneficiaries"][0]
        self.assertEqual(result["score"], 20)
        self.assertEqual(result["articles"], 1)

    def test_snapshot_save_and_read(self):
        with tempfile.TemporaryDirectory() as d:
            r = Repository(d + "/a.db")
            r.init()
            r.upsert_article(
                {
                    "source": "x",
                    "title": "기사",
                    "url": "https://example.test/1",
                    "importance_score": 1,
                    "is_candidate": 1,
                }
            )
            r.create_ai_request("REQ-1", [1], "prompt")
            aid = r.save_analysis(payload())
            self.assertEqual(len(r.snapshot(aid)), 1)
            self.assertEqual(r.snapshots()[0]["id"], aid)
            self.assertEqual(r.request_article_ids("REQ-1"), {1})

    def test_candidate_limit(self):
        with tempfile.TemporaryDirectory() as d:
            r = Repository(d + "/a.db")
            r.init()
            for i in range(55):
                r.upsert_article(
                    {
                        "source": "x",
                        "title": f"기사{i}",
                        "url": f"https://example.test/{i}",
                        "importance_score": i,
                        "is_candidate": 1,
                    }
                )
            r.refresh_candidates()
            self.assertEqual(len(r.candidates()), 50)


if __name__ == "__main__":
    unittest.main()
