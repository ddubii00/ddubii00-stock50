import json
import os
import time
from pathlib import Path

from playwright.async_api import async_playwright


CONFIG_DIR = Path.home() / ".config" / "stock50-7"
ACCOUNT_FILE = CONFIG_DIR / "hankyung-account.json"
COOKIE_FILE = CONFIG_DIR / "hankyung-cookies.json"
SESSION_MAX_AGE_HOURS = 12
LOGIN_URL = "https://id.hankyung.com/login/login.do"
HOME_URL = "https://www.hankyung.com/"


def _load_account():
    if not ACCOUNT_FILE.exists():
        raise RuntimeError(
            f"한국경제 계정 파일이 없습니다: {ACCOUNT_FILE}. "
            "서버에만 저장하고 GitHub에는 올리지 마세요."
        )
    data = json.loads(ACCOUNT_FILE.read_text(encoding="utf-8"))
    user_id = (
        data.get("email")
        or data.get("id")
        or data.get("user_id")
        or data.get("username")
    )
    password = data.get("password") or data.get("pw")
    if not user_id or not password:
        raise RuntimeError("한국경제 계정 파일에 email/id와 password가 필요합니다.")
    return str(user_id), str(password)


def auth_status():
    fresh = False
    age_hours = None
    if COOKIE_FILE.exists():
        age_hours = (time.time() - COOKIE_FILE.stat().st_mtime) / 3600
        fresh = age_hours < SESSION_MAX_AGE_HOURS
    return {
        "account_file": ACCOUNT_FILE.exists(),
        "cookie_file": COOKIE_FILE.exists(),
        "cookie_fresh": fresh,
        "cookie_age_hours": age_hours,
    }


async def _fill_first(page, selectors, value):
    for selector in selectors:
        loc = page.locator(selector)
        try:
            if await loc.count() and await loc.first.is_visible():
                await loc.first.fill(value)
                return True
        except Exception:
            continue
    return False


async def login():
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    os.chmod(CONFIG_DIR, 0o700)
    user_id, password = _load_account()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(locale="ko-KR")
        page = await context.new_page()
        page.set_default_timeout(15000)
        await page.goto(LOGIN_URL, wait_until="domcontentloaded")

        ok_id = await _fill_first(
            page,
            [
                'input[type="email"]',
                'input[name="email"]',
                'input[name="user_id"]',
                'input[name="userid"]',
                'input[name="id"]',
                'input[type="text"]',
            ],
            user_id,
        )
        ok_pw = await _fill_first(
            page,
            [
                'input[type="password"]',
                'input[name="password"]',
                'input[name="passwd"]',
                'input[name="pw"]',
            ],
            password,
        )
        if not ok_id or not ok_pw:
            await browser.close()
            raise RuntimeError("한국경제 로그인 입력칸을 찾지 못했습니다.")

        submitted = False
        for selector in [
            'button[type="submit"]',
            'input[type="submit"]',
            'button:has-text("로그인")',
            'a:has-text("로그인")',
        ]:
            try:
                loc = page.locator(selector)
                if await loc.count() and await loc.first.is_visible():
                    await loc.first.click()
                    submitted = True
                    break
            except Exception:
                continue
        if not submitted:
            await page.locator('input[type="password"]').first.press("Enter")

        try:
            await page.wait_for_url("https://www.hankyung.com/**", timeout=20000)
        except Exception:
            await page.wait_for_timeout(4000)

        if "login" in page.url.lower() and "id.hankyung.com" in page.url.lower():
            await browser.close()
            raise RuntimeError("한국경제 로그인 완료를 확인하지 못했습니다. CAPTCHA/2FA 여부를 확인하세요.")

        cookies = await context.cookies()
        COOKIE_FILE.write_text(
            json.dumps(cookies, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        os.chmod(COOKIE_FILE, 0o600)
        await browser.close()

    return {"ok": True, "refreshed": True, "cookie_count": len(cookies)}


async def ensure_login(force=False):
    status = auth_status()
    if not force and status["cookie_fresh"]:
        data = json.loads(COOKIE_FILE.read_text(encoding="utf-8"))
        return {"ok": True, "refreshed": False, "cookie_count": len(data)}
    return await login()
