import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


SCHEMA = """
CREATE TABLE IF NOT EXISTS articles (
 id INTEGER PRIMARY KEY,
 source TEXT NOT NULL,
 title TEXT NOT NULL,
 url TEXT NOT NULL UNIQUE,
 published_at TEXT,
 section TEXT,
 snippet TEXT,
 content_excerpt TEXT,
 collected_at TEXT NOT NULL,
 importance_score INTEGER NOT NULL DEFAULT 0,
 duplicate_group TEXT,
 is_candidate INTEGER NOT NULL DEFAULT 0,
 created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS news_runs (
 id INTEGER PRIMARY KEY,
 started_at TEXT NOT NULL,
 finished_at TEXT,
 fetched_count INTEGER DEFAULT 0,
 unique_count INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS stock_universe (
 code TEXT PRIMARY KEY,
 name TEXT NOT NULL,
 market TEXT NOT NULL,
 updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ai_requests (
 request_id TEXT PRIMARY KEY,
 created_at TEXT NOT NULL,
 prompt_text TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ai_request_articles (
 request_id TEXT NOT NULL,
 article_id INTEGER NOT NULL,
 position INTEGER NOT NULL,
 PRIMARY KEY(request_id, article_id)
);

CREATE TABLE IF NOT EXISTS ai_analyses (
 id INTEGER PRIMARY KEY,
 analysis_request_id TEXT,
 analysis_time TEXT NOT NULL,
 created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ai_article_analysis (
 id INTEGER PRIMARY KEY,
 analysis_id INTEGER NOT NULL,
 article_id INTEGER NOT NULL,
 title TEXT NOT NULL,
 importance INTEGER NOT NULL,
 confidence TEXT NOT NULL,
 summary_json TEXT NOT NULL,
 UNIQUE(analysis_id, article_id)
);

CREATE TABLE IF NOT EXISTS ai_stock_impacts (
 id INTEGER PRIMARY KEY,
 analysis_id INTEGER NOT NULL,
 article_id INTEGER NOT NULL,
 side TEXT NOT NULL,
 name TEXT NOT NULL,
 code TEXT NOT NULL,
 market TEXT NOT NULL,
 impact INTEGER NOT NULL,
 reason TEXT NOT NULL
);
"""

DEFAULT_UNIVERSE = [
    ("000660", "SK하이닉스", "KOSPI"),
    ("005930", "삼성전자", "KOSPI"),
    ("042700", "한미반도체", "KOSPI"),
    ("373220", "LG에너지솔루션", "KOSPI"),
    ("000270", "기아", "KOSPI"),
]


def now():
    return datetime.now(timezone.utc).isoformat()


class Repository:
    def __init__(self, path: str):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.path = path

    def connect(self):
        con = sqlite3.connect(self.path)
        con.row_factory = sqlite3.Row
        return con

    def _ensure_column(self, con, table, column, definition):
        cols = {x["name"] for x in con.execute(f"PRAGMA table_info({table})")}
        if column not in cols:
            con.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    def init(self):
        with self.connect() as con:
            con.executescript(SCHEMA)
            self._ensure_column(con, "articles", "content_excerpt", "TEXT")
            self._ensure_column(con, "ai_analyses", "analysis_request_id", "TEXT")
            stamp = now()
            con.executemany(
                "INSERT OR IGNORE INTO stock_universe(code,name,market,updated_at) VALUES(?,?,?,?)",
                [(c, n, m, stamp) for c, n, m in DEFAULT_UNIVERSE],
            )

    def articles(self):
        with self.connect() as con:
            return [
                dict(x)
                for x in con.execute(
                    "SELECT * FROM articles ORDER BY importance_score DESC, published_at DESC, id DESC"
                )
            ]

    def candidates(self):
        return [x for x in self.articles() if x["is_candidate"]]

    def refresh_candidates(self, limit=50):
        with self.connect() as con:
            con.execute("UPDATE articles SET is_candidate=0")
            ids = [
                x["id"]
                for x in con.execute(
                    "SELECT id FROM articles WHERE importance_score > 0 "
                    "ORDER BY importance_score DESC, published_at DESC, id DESC LIMIT ?",
                    (limit,),
                )
            ]
            con.executemany(
                "UPDATE articles SET is_candidate=1 WHERE id=?",
                [(x,) for x in ids],
            )

    def upsert_article(self, a):
        with self.connect() as con:
            con.execute(
                """
                INSERT INTO articles(
                    source,title,url,published_at,section,snippet,content_excerpt,
                    collected_at,importance_score,duplicate_group,is_candidate,created_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(url) DO UPDATE SET
                    source=excluded.source,
                    title=excluded.title,
                    published_at=excluded.published_at,
                    section=excluded.section,
                    snippet=excluded.snippet,
                    content_excerpt=excluded.content_excerpt,
                    collected_at=excluded.collected_at,
                    importance_score=excluded.importance_score,
                    duplicate_group=excluded.duplicate_group,
                    is_candidate=excluded.is_candidate
                """,
                (
                    a["source"],
                    a["title"],
                    a["url"],
                    a.get("published_at"),
                    a.get("section"),
                    a.get("snippet"),
                    a.get("content_excerpt"),
                    now(),
                    a["importance_score"],
                    a.get("duplicate_group"),
                    a["is_candidate"],
                    now(),
                ),
            )

    def universe(self):
        with self.connect() as con:
            return [
                dict(x)
                for x in con.execute(
                    "SELECT code,name,market FROM stock_universe ORDER BY market,name"
                )
            ]

    def create_ai_request(self, request_id, article_ids, prompt_text):
        with self.connect() as con:
            con.execute(
                "INSERT INTO ai_requests(request_id,created_at,prompt_text) VALUES(?,?,?)",
                (request_id, now(), prompt_text),
            )
            con.executemany(
                "INSERT INTO ai_request_articles(request_id,article_id,position) VALUES(?,?,?)",
                [(request_id, int(aid), i) for i, aid in enumerate(article_ids)],
            )

    def request_article_ids(self, request_id):
        with self.connect() as con:
            return {
                x["article_id"]
                for x in con.execute(
                    "SELECT article_id FROM ai_request_articles WHERE request_id=? ORDER BY position",
                    (request_id,),
                )
            }

    def request_exists(self, request_id):
        with self.connect() as con:
            return (
                con.execute(
                    "SELECT 1 FROM ai_requests WHERE request_id=?",
                    (request_id,),
                ).fetchone()
                is not None
            )

    def save_analysis(self, payload):
        request_id = payload.get("analysis_request_id")
        with self.connect() as con:
            cur = con.execute(
                "INSERT INTO ai_analyses(analysis_request_id,analysis_time,created_at) VALUES(?,?,?)",
                (request_id, payload["analysis_time"], now()),
            )
            analysis_id = cur.lastrowid
            for a in payload["articles"]:
                con.execute(
                    """
                    INSERT INTO ai_article_analysis(
                        analysis_id,article_id,title,importance,confidence,summary_json
                    ) VALUES(?,?,?,?,?,?)
                    """,
                    (
                        analysis_id,
                        a["article_id"],
                        a["title"],
                        a["importance"],
                        a["confidence"],
                        json.dumps(a["summary"], ensure_ascii=False),
                    ),
                )
                for side in ("beneficiaries", "losers"):
                    for s in a[side]:
                        con.execute(
                            """
                            INSERT INTO ai_stock_impacts(
                                analysis_id,article_id,side,name,code,market,impact,reason
                            ) VALUES(?,?,?,?,?,?,?,?)
                            """,
                            (
                                analysis_id,
                                a["article_id"],
                                side,
                                s["name"],
                                s["code"],
                                s["market"],
                                s["impact"],
                                s["reason"],
                            ),
                        )
        return analysis_id

    def snapshots(self):
        with self.connect() as con:
            return [
                dict(x)
                for x in con.execute(
                    "SELECT id,analysis_request_id,analysis_time,created_at "
                    "FROM ai_analyses ORDER BY id DESC"
                )
            ]

    def snapshot(self, aid):
        with self.connect() as con:
            rows = [
                dict(x)
                for x in con.execute(
                    """
                    SELECT aa.*,a.url,a.published_at,a.section,a.duplicate_group
                    FROM ai_article_analysis aa
                    JOIN articles a ON a.id=aa.article_id
                    WHERE aa.analysis_id=?
                    ORDER BY aa.importance DESC, aa.id
                    """,
                    (aid,),
                )
            ]
            impacts = [
                dict(x)
                for x in con.execute(
                    "SELECT * FROM ai_stock_impacts WHERE analysis_id=? ORDER BY id",
                    (aid,),
                )
            ]

        by_article = {r["article_id"]: [] for r in rows}
        for impact in impacts:
            by_article.setdefault(impact["article_id"], []).append(impact)
        for row in rows:
            row["summary"] = json.loads(row.pop("summary_json"))
            row["impacts"] = by_article.get(row["article_id"], [])
        return rows
