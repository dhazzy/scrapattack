import hashlib
import logging
import re
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from odds_app.scrapers.base import OddsQuote
from odds_app.scrapers.live_parser import extract_quotes_from_payload

logger = logging.getLogger(__name__)

SPORTS = ["Football", "Tennis", "Basketball"]
LOGIN_BUTTON_LABELS = ["Login", "Sign In", "Log In", "Submit"]
MENU_TOKENS = {
    "ODDS Scanner",
    "PSPORTS",
    "Live Casino",
    "Slots and Games",
    "Virtual Sports",
    "Currency",
    "Odd format",
    "Football",
    "Tennis",
    "Basketball",
    "Watch List",
    "DEPOSIT",
    "FAVOURITE",
    "LIVE",
    "TODAY",
    "EARLY",
    "FT",
    "Time",
    "Match",
    "Type",
    "HDP",
    "Home",
    "Away",
    "OU",
    "Over",
    "Under",
}
DATE_RE = re.compile(r"^[A-Za-z]{3}-\d{1,2},\s*\d{2}:\d{2}$")
MATCH_RE = re.compile(r"^(.+?)\s+vs\s+(.+)$", re.IGNORECASE)
ODDS_RE = re.compile(r"^\d{1,2}\.\d{2,3}$")


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


def _clean_lines(text: str) -> list[str]:
    lines = []
    for raw in text.splitlines():
        ln = raw.replace("\xa0", " ").strip()
        if not ln:
            continue
        lines.append(ln)
    return lines


def _parse_kickoff(line: str, now: datetime) -> datetime | None:
    if not DATE_RE.match(line):
        return None
    try:
        dt = datetime.strptime(f"{line} {now.year}", "%b-%d, %H:%M %Y")
        dt = dt.replace(tzinfo=timezone.utc)
        if dt < now.replace(month=1, day=1):
            return dt
        # If crossing year-end, move early-month dates to next year.
        if (now.month >= 11) and (dt.month <= 2) and (dt < now - now.utcoffset() if now.utcoffset() else dt < now):
            dt = dt.replace(year=now.year + 1)
        return dt
    except Exception:
        return None


def _looks_like_league(line: str) -> bool:
    if line in MENU_TOKENS:
        return False
    if DATE_RE.match(line):
        return False
    if MATCH_RE.match(line):
        return False
    if ODDS_RE.match(line):
        return False
    if line.startswith("+") or line.startswith("-"):
        return False
    return " - " in line and any(ch.isalpha() for ch in line)


def _make_external_id(sport: str, league: str | None, home: str, away: str, kickoff: datetime | None) -> str:
    key = f"{sport}|{league or ''}|{home}|{away}|{kickoff.isoformat() if kickoff else ''}"
    return hashlib.md5(key.encode("utf-8")).hexdigest()[:16]


def _extract_quotes_from_dashboard_text(source: str, sport_label: str, text: str) -> list[OddsQuote]:
    sport = _normalize_sport(sport_label)
    now = datetime.now(timezone.utc)
    lines = _clean_lines(text)

    # Start from the table header if present.
    start_idx = 0
    for i, ln in enumerate(lines):
        if ln == "Time" and i + 5 < len(lines) and "Match" in lines[i + 1 : i + 8]:
            start_idx = i
            break

    quotes: list[OddsQuote] = []
    current_league: str | None = None
    pending_kickoff: datetime | None = None

    i = start_idx
    while i < len(lines):
        line = lines[i]

        if _looks_like_league(line):
            current_league = line
            i += 1
            continue

        maybe_dt = _parse_kickoff(line, now)
        if maybe_dt is not None:
            pending_kickoff = maybe_dt
            i += 1
            continue

        m = MATCH_RE.match(line)
        if not m:
            i += 1
            continue

        home = m.group(1).strip()
        away = m.group(2).strip()
        odds_values: list[Decimal] = []

        j = i + 1
        while j < len(lines) and (j - i) <= 18:
            nxt = lines[j]
            if MATCH_RE.match(nxt) or _parse_kickoff(nxt, now) is not None or _looks_like_league(nxt):
                break
            if ODDS_RE.match(nxt):
                try:
                    val = Decimal(nxt)
                    if val > 1:
                        odds_values.append(val)
                except Exception:
                    pass
            j += 1

        ext_id = _make_external_id(sport, current_league, home, away, pending_kickoff)

        # Heuristic mapping from row tail:
        # - Soccer usually exposes 3-way odds in this scanner row tail.
        # - Tennis/Basketball are 2-way.
        if sport == "soccer" and len(odds_values) >= 3:
            tail = odds_values[-3:]
            mapped = [("home", tail[0]), ("draw", tail[1]), ("away", tail[2])]
        elif len(odds_values) >= 2:
            tail = odds_values[-2:]
            mapped = [("home", tail[0]), ("away", tail[1])]
        else:
            mapped = []

        for selection, price in mapped:
            quotes.append(
                OddsQuote(
                    source=source,
                    sport=sport,
                    league=current_league,
                    external_event_id=ext_id,
                    home_team=home,
                    away_team=away,
                    kickoff_utc=pending_kickoff,
                    market_type="1x2",
                    selection=selection,
                    odds_decimal=price,
                    scraped_at=now,
                )
            )

        i = j

    return quotes


async def _collect_vodds_payloads(
    dashboard_url: str,
    username: str,
    password: str,
    headless: bool,
    timeout_sec: float,
    proxy_url: str | None,
) -> tuple[dict[str, Any], dict[str, list[Any]], dict[str, list[str]]]:
    from playwright.async_api import async_playwright

    payloads_by_sport: dict[str, list[Any]] = {sport: [] for sport in SPORTS}
    dom_text_by_sport: dict[str, list[str]] = {sport: [] for sport in SPORTS}
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
                    await page.wait_for_timeout(9000)

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
                    await page.wait_for_timeout(7000)

        post_login_title = await page.title()
        post_login_url = page.url
        post_login_html = await page.content()
        post_login_login_form = await page.locator('input[type="password"]').count() > 0
        post_login_challenge = _is_cloudflare_challenge(post_login_title, post_login_html[:20000], post_login_url)

        # Remove tour/intro overlays that intercept click events.
        await page.evaluate(
            """
            (() => {
              for (const sel of ['.introjs-overlay', '.introjs-helperLayer', '.introjs-tooltipReferenceLayer']) {
                for (const el of document.querySelectorAll(sel)) el.remove();
              }
              const skip = document.querySelector('.introjs-skipbutton');
              if (skip) skip.click();
            })();
            """
        )
        await page.wait_for_timeout(500)

        for sport in SPORTS:
            active_sport["value"] = sport
            # Direct DOM click is more reliable than pointer click when tutorial overlay exists.
            await page.evaluate(
                """
                (sportName) => {
                  const spans = [...document.querySelectorAll('.sport-cat-tabs li span')];
                  const s = spans.find(e => (e.textContent || '').trim().toUpperCase() === sportName.toUpperCase());
                  if (s) s.click();
                  const pars = [...document.querySelectorAll('p')];
                  const early = pars.find(e => (e.textContent || '').trim().toUpperCase() === 'EARLY');
                  if (early) early.click();
                }
                """,
                sport,
            )
            await page.wait_for_timeout(2800)

            # DOM text snapshot fallback parser.
            try:
                dom_text = await page.inner_text('body')
                if dom_text.strip():
                    dom_text_by_sport[sport].append(dom_text)
                    clicked_sports.append(sport)
                    clicked_early += 1
            except Exception:
                pass

        await page.wait_for_timeout(2000)

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
                "dom_snapshot_counts": {k: len(v) for k, v in dom_text_by_sport.items()},
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

    return summary, payloads_by_sport, dom_text_by_sport


async def diagnose_vodds_access(
    dashboard_url: str,
    username: str,
    password: str,
    headless: bool = True,
    timeout_sec: float = 60.0,
    proxy_url: str | None = None,
) -> dict[str, Any]:
    try:
        summary, _, dom_text_by_sport = await _collect_vodds_payloads(
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

    dom_counts = {k: len(v) for k, v in dom_text_by_sport.items()}
    if not any(dom_counts.values()):
        recommendations.append("No DOM snapshots captured after sport/EARLY clicks.")

    if summary["network"]["json_response_count"] == 0:
        recommendations.append("No JSON payloads captured from dashboard; odds API was not reached.")

    if not recommendations:
        recommendations.append("Vodds navigation/login looks healthy; inspect payload/DOM parser if quotes remain zero.")

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
        summary, payloads_by_sport, dom_text_by_sport = await _collect_vodds_payloads(
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

    # Primary attempt: payload-based extraction.
    for sport, payloads in payloads_by_sport.items():
        for payload in payloads:
            for quote in _extract_quotes_from_vodds_payload(payload, sport):
                key = (quote.external_event_id, quote.market_type, quote.selection)
                if key in seen:
                    continue
                seen.add(key)
                all_quotes.append(quote)

    # Fallback: rendered DOM text extraction.
    for sport, snapshots in dom_text_by_sport.items():
        for snap in snapshots:
            for quote in _extract_quotes_from_dashboard_text("ps3838", sport, snap):
                key = (quote.external_event_id, quote.market_type, quote.selection)
                if key in seen:
                    continue
                seen.add(key)
                all_quotes.append(quote)

    if not all_quotes:
        logger.warning(
            "Vodds scrape produced no quotes (final_url=%s, json_responses=%s, clicked_sports=%s). "
            "Dashboard odds may still require websocket binary decoding for complete coverage.",
            summary.get("final", {}).get("url"),
            summary.get("network", {}).get("json_response_count"),
            summary.get("ui", {}).get("clicked_sports"),
        )

    return all_quotes
