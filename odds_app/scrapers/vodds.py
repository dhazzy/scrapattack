import logging
from datetime import datetime, timezone
from typing import Any

from odds_app.scrapers.base import OddsQuote
from odds_app.scrapers.live_parser import extract_quotes_from_payload

logger = logging.getLogger(__name__)

SPORTS = ["Football", "Tennis", "Basketball"]
LOGIN_BUTTON_LABELS = ["Login", "Sign In", "Log In", "Submit"]


def _normalize_sport(label: str) -> str:
    value = label.lower()
    if value == "football":
        return "soccer"
    if value in {"tennis", "basketball"}:
        return value
    return "soccer"


def _selection_normalize(value: str) -> str:
    val = value.strip().lower()
    if val in {"1", "home"}:
        return "home"
    if val in {"x", "draw", "0"}:
        return "draw"
    if val in {"2", "away"}:
        return "away"
    return val


def _extract_quotes_from_vodds_payload(payload: Any, sport_label: str) -> list[OddsQuote]:
    raw = extract_quotes_from_payload(source="ps3838", payload=payload, now=datetime.now(timezone.utc))
    sport = _normalize_sport(sport_label)
    quotes: list[OddsQuote] = []
    for quote in raw:
        quote.sport = sport
        quote.selection = _selection_normalize(quote.selection)
        quotes.append(quote)
    return quotes


def _is_cloudflare_challenge(title: str, html: str, url: str) -> bool:
    title_l = title.lower()
    html_l = html.lower()
    url_l = url.lower()
    return (
        "just a moment" in title_l
        or "challenge-platform" in html_l
        or "challenges.cloudflare.com" in html_l
        or "/cdn-cgi/challenge" in html_l
        or "/cdn-cgi/challenge" in url_l
        or "performance and security by cloudflare" in html_l
        or "verification successful. waiting for" in html_l
    )


async def _collect_vodds_payloads(
    dashboard_url: str,
    username: str,
    password: str,
    headless: bool,
    timeout_sec: float,
    proxy_url: str | None,
) -> tuple[dict[str, Any], dict[str, list[Any]]]:
    from playwright.async_api import async_playwright

    payloads_by_sport: dict[str, list[Any]] = {sport: [] for sport in SPORTS}
    active_sport = {"value": "Football"}
    network_samples: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    json_response_count = 0
    challenge_request_count = 0

    launch_kwargs: dict[str, Any] = {
        "headless": headless,
        "args": ["--disable-blink-features=AutomationControlled"],
    }
    if proxy_url:
        launch_kwargs["proxy"] = {"server": proxy_url}

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(**launch_kwargs)
        context = await browser.new_context(
            locale="en-US",
            timezone_id="UTC",
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
            ),
        )
        await context.set_extra_http_headers(
            {
                "sec-ch-ua": '"Google Chrome";v="125", "Chromium";v="125", "Not.A/Brand";v="24"',
                "sec-ch-ua-mobile": "?0",
                "sec-ch-ua-platform": '"Windows"',
            }
        )
        page = await context.new_page()
        await page.add_init_script(
            """
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            Object.defineProperty(navigator, 'platform', { get: () => 'Win32' });
            Object.defineProperty(navigator, 'language', { get: () => 'en-US' });
            Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
            """
        )

        async def on_response(resp):
            nonlocal json_response_count
            nonlocal challenge_request_count
            ctype = (resp.headers.get("content-type") or "").lower()

            if (
                "challenge-platform" in resp.url
                or "challenges.cloudflare.com" in resp.url
                or "/cdn-cgi/challenge" in resp.url
            ):
                challenge_request_count += 1

            if resp.url not in seen_urls and (resp.request.resource_type in {"document", "xhr", "fetch"}):
                seen_urls.add(resp.url)
                network_samples.append(
                    {
                        "status": resp.status,
                        "method": resp.request.method,
                        "resource_type": resp.request.resource_type,
                        "url": resp.url,
                        "content_type": ctype,
                    }
                )

            if "application/json" not in ctype and resp.request.resource_type not in {"xhr", "fetch"}:
                return
            try:
                payload = await resp.json()
            except Exception:
                return
            json_response_count += 1
            payloads_by_sport.setdefault(active_sport["value"], []).append(payload)

        page.on("response", on_response)

        login_attempted = False
        login_button_clicked = False
        login_iframe_found = False
        login_iframe_fields_present = False
        clicked_sports: list[str] = []
        clicked_early = 0

        await page.goto(dashboard_url, wait_until="domcontentloaded", timeout=int(timeout_sec * 1000))
        await page.wait_for_timeout(5000)

        initial_title = await page.title()
        initial_url = page.url
        initial_html = await page.content()
        initial_login_form = await page.locator('input[type="password"]').count() > 0
        initial_challenge = _is_cloudflare_challenge(initial_title, initial_html[:20000], initial_url)

        if username and password:
            # Main auth is in /static/login iframe.
            login_frame = None
            for frame in page.frames:
                if "/static/login" in frame.url:
                    login_frame = frame
                    break
            login_iframe_found = login_frame is not None

            if login_frame is not None:
                frame_user = login_frame.locator('input[placeholder="Username"], input[type="text"]')
                frame_password = login_frame.locator('input[placeholder="Password"], input[type="password"]')
                if await frame_user.count() > 0 and await frame_password.count() > 0:
                    login_iframe_fields_present = True
                    login_attempted = True
                    await frame_user.first.fill(username)
                    await frame_password.first.fill(password)
                    play_now = login_frame.get_by_role("button", name="Play now")
                    if await play_now.count() > 0:
                        await play_now.first.click()
                        login_button_clicked = True
                    else:
                        await frame_password.first.press("Enter")
                    await page.wait_for_timeout(8000)

            if not login_attempted and initial_login_form:
                user_loc = page.locator(
                    'input[type="email"], input[name="email"], input[name="username"], input[type="text"]'
                )
                pass_loc = page.locator('input[type="password"], input[name="password"]')
                if await user_loc.count() and await pass_loc.count():
                    login_attempted = True
                    await user_loc.first.fill(username)
                    await pass_loc.first.fill(password)
                    for label in LOGIN_BUTTON_LABELS:
                        btn = page.get_by_role("button", name=label)
                        if await btn.count() > 0:
                            await btn.first.click()
                            login_button_clicked = True
                            break
                    if not login_button_clicked:
                        await page.keyboard.press("Enter")
                    await page.wait_for_timeout(6000)

        post_login_title = await page.title()
        post_login_url = page.url
        post_login_html = await page.content()
        post_login_login_form = await page.locator('input[type="password"]').count() > 0
        post_login_challenge = _is_cloudflare_challenge(post_login_title, post_login_html[:20000], post_login_url)

        for sport in SPORTS:
            active_sport["value"] = sport
            sport_loc = page.get_by_text(sport, exact=False)
            if await sport_loc.count() == 0:
                continue
            try:
                await sport_loc.first.click(timeout=2000)
                clicked_sports.append(sport)
                await page.wait_for_timeout(1400)
            except Exception:
                continue
            early_loc = page.get_by_text("EARLY", exact=False)
            if await early_loc.count() > 0:
                try:
                    await early_loc.first.click(timeout=2000)
                    clicked_early += 1
                    await page.wait_for_timeout(1400)
                except Exception:
                    pass

        await page.wait_for_timeout(2500)

        final_title = await page.title()
        final_url = page.url
        final_html = await page.content()
        final_challenge = _is_cloudflare_challenge(final_title, final_html[:20000], final_url)

        summary: dict[str, Any] = {
            "initial": {
                "url": initial_url,
                "title": initial_title,
                "has_login_form": initial_login_form,
                "cloudflare_challenge": initial_challenge,
            },
            "post_login": {
                "url": post_login_url,
                "title": post_login_title,
                "has_login_form": post_login_login_form,
                "cloudflare_challenge": post_login_challenge,
                "login_attempted": login_attempted,
                "login_button_clicked": login_button_clicked,
                "login_iframe_found": login_iframe_found,
                "login_iframe_fields_present": login_iframe_fields_present,
            },
            "final": {
                "url": final_url,
                "title": final_title,
                "cloudflare_challenge": final_challenge,
            },
            "ui": {
                "clicked_sports": clicked_sports,
                "clicked_early_count": clicked_early,
            },
            "network": {
                "json_response_count": json_response_count,
                "challenge_request_count": challenge_request_count,
                "sample_count": len(network_samples),
                "samples": network_samples[:20],
            },
        }

        await context.close()
        await browser.close()

    return summary, payloads_by_sport


async def diagnose_vodds_access(
    dashboard_url: str,
    username: str,
    password: str,
    headless: bool = True,
    timeout_sec: float = 60.0,
    proxy_url: str | None = None,
) -> dict[str, Any]:
    try:
        summary, _ = await _collect_vodds_payloads(
            dashboard_url=dashboard_url,
            username=username,
            password=password,
            headless=headless,
            timeout_sec=timeout_sec,
            proxy_url=proxy_url,
        )
    except Exception as exc:
        return {
            "ok": False,
            "error": f"{type(exc).__name__}: {exc}",
            "summary": None,
            "recommendations": [
                "Playwright navigation failed before login; verify Chromium and proxy settings.",
            ],
        }

    recommendations: list[str] = []
    challenge_seen = bool(
        summary["initial"]["cloudflare_challenge"]
        or summary["network"].get("challenge_request_count", 0) > 0
    )
    if challenge_seen:
        recommendations.append(
            "Cloudflare challenge detected before login form. Use a residential proxy for Vodds/Cloudflare."
        )

    iframe_found = bool(summary["post_login"].get("login_iframe_found"))
    iframe_fields = bool(summary["post_login"].get("login_iframe_fields_present"))
    if not iframe_found and not challenge_seen:
        recommendations.append("Vodds login iframe (/static/login) not found; page structure likely changed.")
    if iframe_found and not iframe_fields and not challenge_seen:
        recommendations.append("Vodds login iframe found but Username/Password fields were not detected.")

    if summary["post_login"]["login_attempted"] and "member/dashboard" not in summary["final"]["url"]:
        recommendations.append("Login submit happened but did not land on /member/dashboard.")
    if summary["network"]["json_response_count"] == 0:
        recommendations.append("No JSON payloads captured from dashboard; odds API was not reached.")
    if not recommendations:
        recommendations.append("Vodds navigation/login looks healthy; investigate payload parser if quotes remain zero.")

    login_success = "member/dashboard" in summary["final"]["url"]
    return {
        "ok": (not challenge_seen) and login_success,
        "summary": summary,
        "recommendations": recommendations,
    }


async def scrape_ps3838_from_vodds(
    dashboard_url: str,
    username: str,
    password: str,
    headless: bool = True,
    timeout_sec: float = 60.0,
    proxy_url: str | None = None,
) -> list[OddsQuote]:
    try:
        summary, payloads_by_sport = await _collect_vodds_payloads(
            dashboard_url=dashboard_url,
            username=username,
            password=password,
            headless=headless,
            timeout_sec=timeout_sec,
            proxy_url=proxy_url,
        )
    except Exception as exc:
        logger.warning("Vodds scraping failed before payload capture: %s", exc)
        return []

    if summary["initial"]["cloudflare_challenge"]:
        logger.warning(
            "Vodds blocked by Cloudflare challenge before login (url=%s title=%s)",
            summary["initial"].get("url"),
            summary["initial"].get("title"),
        )

    all_quotes: list[OddsQuote] = []
    seen: set[tuple[str, str, str]] = set()
    for sport, payloads in payloads_by_sport.items():
        for payload in payloads:
            for quote in _extract_quotes_from_vodds_payload(payload, sport):
                key = (quote.external_event_id, quote.market_type, quote.selection)
                if key in seen:
                    continue
                seen.add(key)
                all_quotes.append(quote)

    if not all_quotes:
        logger.warning(
            "Vodds scrape produced no quotes (final_url=%s, json_responses=%s, clicked_sports=%s). "
            "Dashboard odds appear to be delivered on websocket binary streams (BESTODD_STREAM/ODD_STREAM), "
            "which are not decoded yet.",
            summary.get("final", {}).get("url"),
            summary.get("network", {}).get("json_response_count"),
            summary.get("ui", {}).get("clicked_sports"),
        )

    return all_quotes
