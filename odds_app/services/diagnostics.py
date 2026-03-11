import asyncio
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

import httpx

from odds_app.config import Settings
from odds_app.scrapers.live_parser import DEFAULT_HEADERS, extract_live_quotes


DIAGNOSTIC_OVERRIDE_FIELDS = {
    "scraper_enable_playwright",
    "scraper_request_timeout_sec",
    "scraper_proxy_url",
    "ps3838_proxy_url",
    "ps3838_cookie_header",
    "ps3838_referer_url",
    "ps3838_browser_only",
    "ps3838_enable_stealth",
    "ps3838_retry_count",
}


def settings_with_overrides(settings: Settings, overrides: dict[str, Any] | None) -> Settings:
    if not overrides:
        return settings
    updates: dict[str, Any] = {}
    for key, value in overrides.items():
        if key in DIAGNOSTIC_OVERRIDE_FIELDS and value is not None:
            updates[key] = value
    if not updates:
        return settings
    return settings.model_copy(update=updates)


def _cookie_names(cookie_header: str) -> list[str]:
    names: list[str] = []
    if not cookie_header.strip():
        return names
    for part in cookie_header.split(";"):
        token = part.strip()
        if "=" not in token:
            continue
        name, _ = token.split("=", 1)
        if name.strip():
            names.append(name.strip())
    return names


def _build_ps3838_headers(settings: Settings) -> dict[str, str]:
    headers = dict(DEFAULT_HEADERS)
    headers.update(
        {
            "Referer": settings.ps3838_referer_url,
            "Origin": "https://www.ps3838.com",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Dest": "document",
            "Upgrade-Insecure-Requests": "1",
        }
    )
    if settings.ps3838_cookie_header:
        headers["Cookie"] = settings.ps3838_cookie_header
    return headers


def _is_cloudflare_block(text: str, status_code: int) -> bool:
    lower = text.lower()
    return status_code in {403, 429, 503} and (
        "cloudflare" in lower or "attention required" in lower or "cf-chl" in lower
    )


async def _probe_proxy_reachability(proxy_url: str | None, timeout_sec: float) -> dict[str, Any]:
    if not proxy_url:
        return {"enabled": False, "ok": None, "status_code": None, "error": None}
    try:
        async with httpx.AsyncClient(timeout=timeout_sec, proxy=proxy_url) as client:
            resp = await client.get("https://www.ps3838.com/", follow_redirects=True)
            return {
                "enabled": True,
                "ok": True,
                "status_code": resp.status_code,
                "final_url": str(resp.url),
                "error": None,
            }
    except Exception as exc:
        return {
            "enabled": True,
            "ok": False,
            "status_code": None,
            "final_url": None,
            "error": f"{type(exc).__name__}: {exc}",
        }


async def _probe_direct_html(
    url: str,
    headers: dict[str, str],
    timeout_sec: float,
    proxy_url: str | None,
) -> dict[str, Any]:
    client_kwargs: dict[str, Any] = {"timeout": timeout_sec}
    if proxy_url:
        client_kwargs["proxy"] = proxy_url
    try:
        async with httpx.AsyncClient(**client_kwargs) as client:
            resp = await client.get(url, headers=headers, follow_redirects=True)
            text = resp.text[:10000]
            return {
                "ok": resp.status_code < 400,
                "status_code": resp.status_code,
                "final_url": str(resp.url),
                "cloudflare_blocked": _is_cloudflare_block(text, resp.status_code),
                "error": None,
            }
    except Exception as exc:
        return {
            "ok": False,
            "status_code": None,
            "final_url": None,
            "cloudflare_blocked": None,
            "error": f"{type(exc).__name__}: {exc}",
        }


async def _probe_playwright_navigation(
    url: str,
    headers: dict[str, str],
    timeout_sec: float,
    proxy_url: str | None,
    cookie_header: str,
    enable_stealth: bool,
) -> dict[str, Any]:
    try:
        from playwright.async_api import async_playwright
    except Exception as exc:
        return {
            "ok": False,
            "available": False,
            "status_code": None,
            "title": None,
            "json_response_count": 0,
            "cloudflare_blocked": None,
            "error": f"{type(exc).__name__}: {exc}",
        }

    launch_kwargs: dict[str, Any] = {"headless": True}
    if proxy_url:
        launch_kwargs["proxy"] = {"server": proxy_url}

    json_count = 0
    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(**launch_kwargs)
            context = await browser.new_context(
                locale="en-US",
                timezone_id="UTC",
                user_agent=headers.get("User-Agent", DEFAULT_HEADERS["User-Agent"]),
            )
            # Don't inject Cookie header directly; use browser cookies instead.
            context_headers = {k: v for k, v in headers.items() if k.lower() != "cookie"}
            if context_headers:
                await context.set_extra_http_headers(context_headers)

            if cookie_header.strip():
                parsed = urlparse(url)
                domain = parsed.hostname or ""
                cookies = []
                for part in cookie_header.split(";"):
                    token = part.strip()
                    if "=" not in token:
                        continue
                    name, value = token.split("=", 1)
                    cookies.append(
                        {"name": name.strip(), "value": value.strip(), "domain": domain, "path": "/"}
                    )
                if cookies:
                    await context.add_cookies(cookies)

            page = await context.new_page()
            if enable_stealth:
                await page.add_init_script(
                    """
                    Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                    Object.defineProperty(navigator, 'platform', { get: () => 'Win32' });
                    Object.defineProperty(navigator, 'language', { get: () => 'en-US' });
                    Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
                    """
                )

            async def _on_response(resp):
                nonlocal json_count
                ctype = (resp.headers.get("content-type") or "").lower()
                if "application/json" in ctype or resp.request.resource_type in {"xhr", "fetch"}:
                    json_count += 1

            page.on("response", _on_response)
            goto_resp = await page.goto(url, wait_until="domcontentloaded", timeout=int(timeout_sec * 1000))
            await page.wait_for_timeout(2500)
            status_code = goto_resp.status if goto_resp else None
            title = await page.title()
            content = await page.content()
            await context.close()
            await browser.close()
            return {
                "ok": status_code is not None and status_code < 400,
                "available": True,
                "status_code": status_code,
                "title": title,
                "json_response_count": json_count,
                "cloudflare_blocked": _is_cloudflare_block(content[:10000], status_code or 0),
                "error": None,
            }
    except Exception as exc:
        return {
            "ok": False,
            "available": True,
            "status_code": None,
            "title": None,
            "json_response_count": json_count,
            "cloudflare_blocked": None,
            "error": f"{type(exc).__name__}: {exc}",
        }


async def run_ps3838_diagnostics(settings: Settings) -> dict[str, Any]:
    headers = _build_ps3838_headers(settings)
    proxy_url = settings.ps3838_proxy_url or settings.scraper_proxy_url or None
    cookie_names = _cookie_names(settings.ps3838_cookie_header)

    proxy_probe = await _probe_proxy_reachability(proxy_url, settings.scraper_request_timeout_sec)
    direct_probe = await _probe_direct_html(
        settings.ps3838_soccer_url, headers, settings.scraper_request_timeout_sec, proxy_url
    )
    browser_probe = await _probe_playwright_navigation(
        url=settings.ps3838_soccer_url,
        headers=headers,
        timeout_sec=max(45.0, settings.scraper_request_timeout_sec),
        proxy_url=proxy_url,
        cookie_header=settings.ps3838_cookie_header,
        enable_stealth=settings.ps3838_enable_stealth,
    )

    extraction_error = None
    extraction_quotes = 0
    sample_quote = None
    try:
        quotes = await extract_live_quotes(
            source="ps3838",
            url=settings.ps3838_soccer_url,
            timeout_sec=settings.scraper_request_timeout_sec,
            enable_playwright=settings.scraper_enable_playwright,
            headers=headers,
            proxy_url=proxy_url,
            cookie_header=settings.ps3838_cookie_header,
            enable_stealth=settings.ps3838_enable_stealth,
            browser_only=settings.ps3838_browser_only,
        )
        extraction_quotes = len(quotes)
        if quotes:
            first = quotes[0]
            sample_quote = {
                "external_event_id": first.external_event_id,
                "home_team": first.home_team,
                "away_team": first.away_team,
                "odds_decimal": str(first.odds_decimal),
                "kickoff_utc": first.kickoff_utc.isoformat() if first.kickoff_utc else None,
            }
    except Exception as exc:
        extraction_error = f"{type(exc).__name__}: {exc}"

    recommendations: list[str] = []
    if direct_probe.get("cloudflare_blocked") and not proxy_url:
        recommendations.append("PS3838 is Cloudflare-blocking this IP. Configure PS3838_PROXY_URL.")
    if direct_probe.get("cloudflare_blocked") and "cf_clearance" not in cookie_names:
        recommendations.append("Provide a valid browser session cookie in PS3838_COOKIE_HEADER.")
    if proxy_probe.get("enabled") and not proxy_probe.get("ok"):
        recommendations.append("Proxy is unreachable. Verify PS3838_PROXY_URL credentials and host.")
    if browser_probe.get("available") and browser_probe.get("cloudflare_blocked"):
        recommendations.append(
            "Browser mode still blocked. Try residential proxy + fresh cf_clearance cookie."
        )
    if extraction_quotes == 0 and not recommendations:
        recommendations.append("No quotes extracted. Inspect page payload changes and selector assumptions.")
    if extraction_quotes > 0:
        recommendations.append("Extraction succeeded. Save this config and monitor quote continuity.")

    return {
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "target_url": settings.ps3838_soccer_url,
        "config": {
            "use_mock_scrape_data": settings.use_mock_scrape_data,
            "scraper_enable_playwright": settings.scraper_enable_playwright,
            "ps3838_browser_only": settings.ps3838_browser_only,
            "ps3838_enable_stealth": settings.ps3838_enable_stealth,
            "ps3838_retry_count": settings.ps3838_retry_count,
            "proxy_configured": bool(proxy_url),
            "cookie_configured": bool(settings.ps3838_cookie_header.strip()),
            "cookie_names": cookie_names,
        },
        "layers": {
            "proxy_reachability": proxy_probe,
            "direct_html": direct_probe,
            "playwright_navigation": browser_probe,
            "extraction": {
                "ok": extraction_quotes > 0 and extraction_error is None,
                "quote_count": extraction_quotes,
                "sample_quote": sample_quote,
                "error": extraction_error,
            },
        },
        "recommendations": recommendations,
    }


def run_ps3838_diagnostics_sync(settings: Settings, overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    effective_settings = settings_with_overrides(settings, overrides)
    return asyncio.run(run_ps3838_diagnostics(effective_settings))
