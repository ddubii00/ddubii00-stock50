import asyncio
import json
import re
import xml.etree.ElementTree as ET

import httpx
from bs4 import BeautifulSoup

from app.scoring.rules import normalize, score, similar
from app.services.hankyung_auth import COOKIE_FILE, ensure_login


RSS_FEEDS = [
    ("증권", "https://www.hankyung.com/feed/finance"),
    ("경제", "https://www.hankyung.com/feed/economy"),
    ("IT", "https://www.hankyung.com/feed/it"),
    ("국제", "https://www.hankyung.com/feed/international"),
    ("부동산", "https://www.hankyung.com/feed/realestate"),
    ("전체뉴스", "https://www.hankyung.com/feed/all-news"),
]
MAX_PROCESS = 100
MAX_EXCERPT = 3000
MAX_CONCURRENT = 4


def clean_space(text):
    return re.sub(r"\s+", " ", text or "").strip()


def clean_html(text):
    if not text:
        return ""
    return clean_space(BeautifulSoup(text, "html.parser").get_text(" ", strip=True))


def strip_noise(text):
    text = clean_space(text)
    for pattern in [
        r"이미지 크게보기",
        r"기사 스크랩",
        r"글자크기 조절",
    ]:
        text = re.sub(pattern, " ", text, flags=re.I)
    return clean_space(text)


def load_cookies():
    jar = httpx.Cookies()
    data = json.loads(COOKIE_FILE.read_text(encoding="utf-8"))
    count = 0
    for c in data:
        name = str(c.get("name", "")).strip()
        value = str(c.get("value", ""))
        domain = str(c.get("domain", ".hankyung.com"))
        path = str(c.get("path", "/"))
        if not name or "hankyung.com" not in domain:
            continue
        jar.set(name, value, domain=domain, path=path)
        count += 1
    return jar, count


def child_text(node, name):
    direct = node.find(name)
    if direct is not None and direct.text:
        return direct.text.strip()
    for child in list(node):
        if child.tag.split("}")[-1] == name and child.text:
            return child.text.strip()
    return ""


def parse_feed(content):
    root = ET.fromstring(content)
    result = []
    for item in root.findall(".//item"):
        title = child_text(item, "title")
        link = child_text(item, "link")
        description = child_text(item, "description")
        published = child_text(item, "pubDate")
        if title and link:
            result.append(
                {
                    "title": clean_space(title),
                    "link": link.strip(),
                    "description": clean_html(description),
                    "published_at": published,
                }
            )
    return result


def extract_article_text(html):
    soup = BeautifulSoup(html, "html.parser")
    for bad in soup.select("script,style,noscript,svg,header,footer,nav,aside"):
        bad.decompose()

    candidates = []
    for selector in [
        "#articletxt",
        "[itemprop='articleBody']",
        ".article-body",
        ".article-body-content",
        ".article-body-wrap",
        ".news-body",
        ".article-content",
        "article",
    ]:
        node = soup.select_one(selector)
        if not node:
            continue
        paragraphs = node.select("p")
        if paragraphs:
            parts = []
            for p in paragraphs:
                text = clean_space(p.get_text(" ", strip=True))
                if len(text) >= 20 and "무단전재" not in text:
                    parts.append(text)
            text = strip_noise(" ".join(parts))
        else:
            text = strip_noise(node.get_text(" ", strip=True))
        if len(text) >= 100:
            candidates.append(text)

    if candidates:
        return max(candidates, key=len)[:MAX_EXCERPT]

    for attrs in ({"property": "og:description"}, {"name": "description"}):
        meta = soup.find("meta", attrs=attrs)
        if meta:
            text = strip_noise(meta.get("content", ""))
            if len(text) >= 60:
                return text[:MAX_EXCERPT]
    return ""


async def fetch_article(client, sem, item):
    async with sem:
        fallback = item.get("description", "")
        try:
            r = await client.get(item["link"])
            r.raise_for_status()
            text = extract_article_text(r.text)
            item["content_excerpt"] = (
                text if len(text) >= len(fallback) else fallback[:MAX_EXCERPT]
            )
        except Exception:
            item["content_excerpt"] = fallback[:MAX_EXCERPT]
        return item


async def collect(repo, progress=None):
    # STOCK50_REAL_PROGRESS_COLLECTOR
    def report(stage, current=0, total=0, message=""):
        if progress is None:
            return
        try:
            progress(
                stage,
                int(current or 0),
                int(total or 0),
                str(message or ""),
            )
        except Exception:
            # 진행률 표시 오류가 실제 기사 수집을 방해하면 안 된다.
            pass

    report(
        "login",
        0,
        0,
        "한국경제 로그인 상태를 확인하고 있습니다.",
    )

    auth = await ensure_login(force=False)

    report(
        "feeds",
        0,
        0,
        "한국경제 뉴스 피드를 불러오고 있습니다.",
    )
    cookies, cookie_count = load_cookies()
    existing = repo.articles()
    existing_urls = {x["url"] for x in existing}
    prior_titles = [x["title"] for x in existing[:300] if x.get("title")]

    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux aarch64) AppleWebKit/537.36 Chrome/153 Safari/537.36",
        "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.7",
    }
    timeout = httpx.Timeout(20, connect=10)
    raw, seen = [], set()
    order = 0

    async with httpx.AsyncClient(
        timeout=timeout, headers=headers, cookies=cookies, follow_redirects=True
    ) as client:
        for section, url in RSS_FEEDS:
            try:
                r = await client.get(url)
                r.raise_for_status()
                items = parse_feed(r.content)
            except Exception:
                continue
            for item in items:
                link = item["link"]
                if link in seen:
                    continue
                seen.add(link)
                item["section"] = section
                item["_order"] = order
                order += 1
                item["_pre_score"] = score(item["title"], item.get("description", ""))
                raw.append(item)

        raw.sort(key=lambda x: (x["_pre_score"], -x["_order"]), reverse=True)
        targets = raw[:MAX_PROCESS]
        total_targets = len(targets)

        report(
            "articles",
            0,
            total_targets,
            f"0/{total_targets} 기사 처리 중",
        )

        sem = asyncio.Semaphore(MAX_CONCURRENT)
        completed = 0

        async def fetch_with_progress(item):
            nonlocal completed

            result = await fetch_article(
                client,
                sem,
                item,
            )

            completed += 1

            report(
                "articles",
                completed,
                total_targets,
                f"{completed}/{total_targets} 기사 처리 중",
            )

            return result

        targets = await asyncio.gather(
            *[
                fetch_with_progress(item)
                for item in targets
            ]
        )

    report(
        "saving",
        len(targets),
        len(targets),
        "수집한 기사 데이터를 저장하고 있습니다.",
    )

    new_count = 0
    for item in targets:
        title = item["title"]
        link = item["link"]
        description = item.get("description", "")
        content = item.get("content_excerpt", "")
        points = score(title, content or description)
        duplicate_group = normalize(title)
        for previous in prior_titles:
            if similar(title, previous):
                duplicate_group = normalize(previous)
                break

        repo.upsert_article(
            {
                "source": "한국경제",
                "title": title,
                "url": link,
                "published_at": item.get("published_at", ""),
                "section": item.get("section", ""),
                "snippet": description[:500],
                "content_excerpt": content[:MAX_EXCERPT],
                "importance_score": points,
                "duplicate_group": duplicate_group,
                "is_candidate": int(points > 0),
            }
        )
        if link not in existing_urls:
            new_count += 1
        prior_titles.append(title)

    repo.refresh_candidates(50)

    report(
        "done",
        len(targets),
        len(targets),
        "기사 수집이 완료되었습니다.",
    )
    return {
        "new": new_count,
        "processed": len(targets),
        "total": len(repo.articles()),
        "candidates": len(repo.candidates()),
        "auth_ok": True,
        "auth_refreshed": bool(auth.get("refreshed")),
        "cookie_count": cookie_count,
    }
