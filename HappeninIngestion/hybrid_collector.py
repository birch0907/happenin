"""Happenin' hybrid config-driven event collector.

Reads venues.json and runs reusable collectors without per-venue scrapers:
  - tunehatch        : Public TuneHatch /api/v1/shows collector (Cantab Lounge & Underground, etc.)
  - tribe_api        : WordPress The Events Calendar REST API (Lizard Lounge, The Rockwell, etc.)
  - squarespace_json : Squarespace ?format=json events collector (Remnant Satellite & Bow Market, etc.)
  - bentobox_jsonld  : Deterministic schema.org/Event JSON-LD + visible time parser (Mad Monkfish, etc.)
  - ics              : Reusable public ICS calendar collector (ManRay, etc.)
  - recurring        : Deterministic weekly/nightly rule expansion (Havana Club, Phoenix Landing, McCarthy's)
  - llm_html         : Hash-cached HTML-to-JSON extraction via Gemini or OpenAI REST API (Middlesex, etc.)

Non-destructive: writes ONLY prototype_events.json and cache/llm_html_cache.json.
Does not touch events.json or ingest.py.

Usage:
  python hybrid_collector.py                  # Run all enabled venues in venues.json
  python hybrid_collector.py --dry-run        # Run deterministic collectors; preview LLM payloads
  python hybrid_collector.py --venue cantab-lounge
  python hybrid_collector.py --no-cache       # Bypass LLM content-hash cache
"""
import argparse
import hashlib
import html as html_lib
import json
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent
VENUES_PATH = ROOT / "venues.json"
CACHE_PATH = ROOT / "cache" / "llm_html_cache.json"
OUTPUT_PATH = ROOT / "prototype_events.json"


def _load_local_env():
    env_file = ROOT / ".env"
    if not env_file.exists():
        return
    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if k and v and k not in os.environ:
            os.environ[k] = v


_load_local_env()

EASTERN = ZoneInfo("America/New_York")
DAYS_AHEAD = 14
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/128.0.0.0 Safari/537.36"
    )
}
WEEKDAY_MAP = {"MON": 0, "TUE": 1, "WED": 2, "THU": 3, "FRI": 4, "SAT": 5, "SUN": 6}
CLOSURE_RE = re.compile(
    r"\b(no event|no live music|closed for|closing at .* private party|private event|closed today|closed\b)\b",
    re.I,
)


# ---------------------------------------------------------------------------
# SHARED HELPERS
# ---------------------------------------------------------------------------

def base_event(
    venue_cfg,
    *,
    title,
    start,
    end,
    url,
    description="",
    source_id=None,
    image_url=None,
    price=None,
    genre=None,
    ages=None,
    extra=None,
):
    """Build a normalized Happenin' event stamped with verified venue coordinates."""
    record = {
        "id": source_id or f"{venue_cfg['id']}:{hashlib.sha256(f'{title}|{start}'.encode()).hexdigest()[:12]}",
        "title": title.strip(),
        "start": start,
        "end": end,
        "venue": venue_cfg["venue"],
        "address": venue_cfg.get("address"),
        "city": venue_cfg.get("city"),
        "state": venue_cfg.get("state"),
        "postal_code": venue_cfg.get("postal_code"),
        "latitude": venue_cfg.get("latitude"),
        "longitude": venue_cfg.get("longitude"),
        "location_precision": "street" if venue_cfg.get("latitude") is not None else "unknown",
        "source_type": "venue_website",
        "source_name": venue_cfg["venue"],
        "source_url": url,
        "description": description.strip(),
        "image_url": image_url,
        "price": price or venue_cfg.get("default_price"),
        "admission_type": (
            "free"
            if str(price or "").strip().lower() in {"free", "$0", "no cover"}
            else venue_cfg.get("default_admission")
        ),
        "genre": genre,
        "ages": ages,
        "default_category": venue_cfg.get("default_category"),
    }
    if extra:
        record.update(extra)
    return record


def in_window(start_dt, end_dt, window_start, window_end):
    effective_end = end_dt if end_dt is not None else start_dt + timedelta(hours=4)
    return start_dt < window_end and effective_end > window_start


def html_to_clean_text(raw_html):
    soup = BeautifulSoup(raw_html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg", "iframe"]):
        tag.decompose()
    lines = [line.strip() for line in soup.get_text("\n").splitlines() if line.strip()]
    return "\n".join(lines)


def strip_html_inline(raw_html):
    if not raw_html:
        return ""
    soup = BeautifulSoup(str(raw_html), "html.parser")
    text = html_lib.unescape(soup.get_text(" ", strip=True))
    return re.sub(r"\s+", " ", text).strip()


def load_cache():
    if CACHE_PATH.exists():
        try:
            return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            pass
    return {}


def save_cache(cache):
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = CACHE_PATH.with_name(CACHE_PATH.name + ".tmp")
    tmp.write_text(json.dumps(cache, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(CACHE_PATH)


def parse_iso_eastern(value):
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt.replace(tzinfo=EASTERN) if dt.tzinfo is None else dt.astimezone(EASTERN)
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# 1. DETERMINISTIC: TUNEHATCH PUBLIC API COLLECTOR
# ---------------------------------------------------------------------------

def collect_tunehatch(venue_cfg, window_start, window_end):
    venue_id = venue_cfg["tunehatch_venue_id"]
    params = {
        "venue_id": venue_id,
        "starts_after": (window_start - timedelta(hours=6)).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "starts_before": window_end.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "limit": 100,
    }
    resp = requests.get("https://tunehatch.com/api/v1/shows", params=params, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    payload = resp.json()
    shows = payload.get("data") or []

    events = []
    for show in shows:
        if show.get("private") or show.get("published") is False or show.get("deletedAt"):
            continue
        status = str(show.get("status") or "").lower()
        if status in {"cancelled", "canceled", "draft"}:
            continue

        # Double-check venueID matches requested room (prevents cross-room duplicates).
        if show.get("venueID") and show.get("venueID") != venue_id:
            continue

        title = html_lib.unescape(str(show.get("name") or "")).strip()
        if not title or CLOSURE_RE.search(title):
            continue

        start_dt = parse_iso_eastern(show.get("startsAt") or show.get("doorsAt"))
        if start_dt is None:
            continue
        end_dt = parse_iso_eastern(show.get("endsAt"))
        if end_dt is not None and end_dt <= start_dt:
            end_dt = None

        if not in_window(start_dt, end_dt, window_start, window_end):
            continue

        slug = show.get("slug")
        event_url = show.get("externalTicketURL") or (f"https://tunehatch.com/shows/{slug}" if slug else venue_cfg["url"])

        # Extract lowest ticket price if pricingConfig exposes tiers.
        price = None
        pricing = show.get("pricingConfig")
        if isinstance(pricing, dict):
            tiers = pricing.get("tiers") or pricing.get("ticketTiers") or []
            prices = []
            for t in tiers:
                if isinstance(t, dict):
                    p = t.get("price") or t.get("amount")
                    if isinstance(p, (int, float)) and p >= 0:
                        prices.append(p)
            if prices:
                low = min(prices)
                price = "Free" if low == 0 else f"${int(round(low))}"

        min_age = show.get("minAge") or show.get("venueMinAge")
        ages = f"{min_age}+" if isinstance(min_age, int) and min_age > 0 else ("All Ages" if min_age == 0 else None)

        performers = show.get("performerNames") or []
        about = strip_html_inline(show.get("about") or "")
        if performers and not about:
            about = "Featuring: " + ", ".join(str(p) for p in performers[:6])

        genre = show.get("genre")
        if isinstance(genre, list):
            genre = genre[0] if genre else None

        events.append(base_event(
            venue_cfg,
            title=title,
            start=start_dt.isoformat(),
            end=end_dt.isoformat() if end_dt else None,
            url=event_url,
            description=about,
            source_id=f"tunehatch:{show.get('id')}",
            image_url=show.get("flyerURL"),
            price=price,
            genre=str(genre) if genre else None,
            ages=ages,
            extra={"collector": "tunehatch"},
        ))

    return sorted(events, key=lambda e: e["start"])


# ---------------------------------------------------------------------------
# 2. DETERMINISTIC: WORDPRESS TRIBE / THE EVENTS CALENDAR REST API
# ---------------------------------------------------------------------------

def collect_tribe_api(venue_cfg, window_start, window_end):
    base_url = venue_cfg["tribe_base_url"].rstrip("/")
    api_url = f"{base_url}/wp-json/tribe/events/v1/events"
    params = {
        "start_date": (window_start - timedelta(hours=6)).strftime("%Y-%m-%d %H:%M:%S"),
        "end_date": window_end.strftime("%Y-%m-%d %H:%M:%S"),
        "per_page": 50,
    }
    if venue_cfg.get("tribe_category"):
        params["categories"] = venue_cfg["tribe_category"]
    events = []
    page = 1
    while page <= 5:
        params["page"] = page
        resp = requests.get(api_url, params=params, headers=HEADERS, timeout=20)
        if resp.status_code == 404 and page > 1:
            break
        resp.raise_for_status()
        data = resp.json()
        batch = data.get("events") or []
        if not batch:
            break

        for item in batch:
            if item.get("all_day"):
                continue
            title = html_lib.unescape(str(item.get("title") or "")).strip()
            if not title or CLOSURE_RE.search(title):
                continue

            start_str = item.get("start_date")
            end_str = item.get("end_date")
            try:
                start_dt = datetime.strptime(start_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=EASTERN)
            except (TypeError, ValueError):
                continue

            end_dt = None
            if end_str:
                try:
                    parsed_end = datetime.strptime(end_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=EASTERN)
                    if parsed_end > start_dt:
                        end_dt = parsed_end
                except ValueError:
                    pass

            if not in_window(start_dt, end_dt, window_start, window_end):
                continue

            desc = strip_html_inline(item.get("description") or item.get("excerpt") or "")
            if len(desc) > 500:
                desc = desc[:497].rsplit(" ", 1)[0] + "..."

            cost = html_lib.unescape(str(item.get("cost") or "")).strip() or None
            img = item.get("image")
            image_url = img.get("url") if isinstance(img, dict) else None
            cats = item.get("categories") or []
            genre = html_lib.unescape(cats[0]["name"]) if cats and isinstance(cats[0], dict) and cats[0].get("name") else None

            events.append(base_event(
                venue_cfg,
                title=title,
                start=start_dt.isoformat(),
                end=end_dt.isoformat() if end_dt else None,
                url=item.get("url") or venue_cfg["url"],
                description=desc,
                source_id=f"tribe:{venue_cfg['id']}:{item.get('id')}",
                image_url=image_url,
                price=cost,
                genre=genre,
                extra={"collector": "tribe_api"},
            ))

        if page >= int(data.get("total_pages") or 1):
            break
        page += 1

    return sorted(events, key=lambda e: e["start"])


# ---------------------------------------------------------------------------
# 3. DETERMINISTIC: SQUARESPACE ?format=json COLLECTOR
# ---------------------------------------------------------------------------

def collect_squarespace_json(venue_cfg, window_start, window_end):
    url = venue_cfg["url"]
    json_url = url + ("&" if "?" in url else "?") + "format=json"
    resp = requests.get(json_url, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    data = resp.json()
    items = data.get("upcoming") or data.get("items") or []

    location_match = (venue_cfg.get("location_match") or "").lower().strip()
    origin = re.match(r"https?://[^/]+", url).group(0)

    events = []
    for item in items:
        title = html_lib.unescape(str(item.get("title") or "")).strip()
        if not title or CLOSURE_RE.search(title):
            continue

        loc = item.get("location") or {}
        loc_blob = " ".join(
            str(loc.get(k) or "") for k in ("addressTitle", "addressLine1", "addressLine2", "addressCountry")
        ).lower()
        if location_match and location_match not in loc_blob and location_match not in title.lower():
            continue

        start_ms = item.get("startDate")
        if not isinstance(start_ms, (int, float)):
            continue
        start_dt = datetime.fromtimestamp(start_ms / 1000, tz=timezone.utc).astimezone(EASTERN)

        end_dt = None
        end_ms = item.get("endDate")
        if isinstance(end_ms, (int, float)) and end_ms > start_ms:
            end_dt = datetime.fromtimestamp(end_ms / 1000, tz=timezone.utc).astimezone(EASTERN)
            # Ignore multi-day closure/banner items spanning >16 hours
            if (end_dt - start_dt) > timedelta(hours=16):
                continue

        if not in_window(start_dt, end_dt, window_start, window_end):
            continue

        # Strip redundant "[Satellite]" or "[Taproom]" prefix if present
        clean_title = re.sub(r"^\[[^\]]+\]\s*", "", title).strip()
        full_url = item.get("fullUrl") or ""
        event_url = (origin + full_url) if full_url.startswith("/") else (full_url or url)
        desc = strip_html_inline(item.get("excerpt") or item.get("body") or "")
        if len(desc) > 500:
            desc = desc[:497].rsplit(" ", 1)[0] + "..."

        events.append(base_event(
            venue_cfg,
            title=clean_title,
            start=start_dt.isoformat(),
            end=end_dt.isoformat() if end_dt else None,
            url=event_url,
            description=desc,
            source_id=f"sqsp:{venue_cfg['id']}:{item.get('id')}",
            image_url=item.get("assetUrl"),
            extra={"collector": "squarespace_json"},
        ))

    return sorted(events, key=lambda e: e["start"])


# ---------------------------------------------------------------------------
# 4. DETERMINISTIC: BENTOBOX / SCHEMA.ORG JSON-LD COLLECTOR
# ---------------------------------------------------------------------------

BENTOBOX_TIME_RE = re.compile(
    r"([A-Z][a-z]+ \d{1,2}, \d{4} \d{1,2}:\d{2} [AP]M)"
    r"(?:\s+until\s+([A-Z][a-z]+ \d{1,2}, \d{4} \d{1,2}:\d{2} [AP]M))?",
    re.I,
)
TITLE_DATE_PREFIX_RE = re.compile(r"^\d{1,2}/\d{1,2}\s+")


def parse_eastern_dt(text):
    for fmt in ("%B %d, %Y %I:%M %p", "%b %d, %Y %I:%M %p"):
        try:
            return datetime.strptime(text.strip(), fmt).replace(tzinfo=EASTERN)
        except ValueError:
            continue
    return None


def iter_jsonld_events(soup):
    for script in soup.find_all("script", type="application/ld+json"):
        raw = (script.string or "").strip()
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        items = data if isinstance(data, list) else [data]
        for item in items:
            if not isinstance(item, dict):
                continue
            if "@graph" in item and isinstance(item["@graph"], list):
                for node in item["@graph"]:
                    if isinstance(node, dict) and node.get("@type") == "Event":
                        yield node
            elif item.get("@type") == "Event":
                yield item


def collect_bentobox_jsonld(venue_cfg, window_start, window_end):
    session = requests.Session()
    session.headers.update(HEADERS)

    resp = session.get(venue_cfg["url"], timeout=20)
    resp.raise_for_status()
    index_soup = BeautifulSoup(resp.text, "html.parser")

    event_urls = []
    for node in iter_jsonld_events(index_soup):
        url = node.get("url")
        if url and url not in event_urls:
            event_urls.append(url)

    events = []
    for url in event_urls:
        try:
            detail_resp = session.get(url, timeout=20)
            detail_resp.raise_for_status()
        except requests.RequestException as exc:
            print(f"  [warn] failed detail page {url}: {exc}")
            continue

        detail_soup = BeautifulSoup(detail_resp.text, "html.parser")
        ld_event = next(iter_jsonld_events(detail_soup), None)
        if not ld_event:
            continue

        raw_title = html_lib.unescape(str(ld_event.get("name") or "")).strip()
        title = TITLE_DATE_PREFIX_RE.sub("", raw_title).strip() or raw_title
        if not title or CLOSURE_RE.search(title):
            continue

        clean_text = html_to_clean_text(detail_resp.text)
        start_dt = parse_iso_eastern(ld_event.get("startDate")) if "T" in str(ld_event.get("startDate") or "") else None
        end_dt = parse_iso_eastern(ld_event.get("endDate")) if "T" in str(ld_event.get("endDate") or "") else None

        if start_dt is None:
            m = BENTOBOX_TIME_RE.search(clean_text)
            if m:
                start_dt = parse_eastern_dt(m.group(1))
                if m.group(2):
                    end_dt = parse_eastern_dt(m.group(2))

        if start_dt is None or not in_window(start_dt, end_dt, window_start, window_end):
            continue

        description = html_lib.unescape(str(ld_event.get("description") or "")).strip()
        image = ld_event.get("image")
        image_url = image.get("url") if isinstance(image, dict) else (image if isinstance(image, str) else None)

        events.append(base_event(
            venue_cfg,
            title=title,
            start=start_dt.isoformat(),
            end=end_dt.isoformat() if end_dt else None,
            url=url,
            description=description,
            image_url=image_url,
            extra={"collector": "bentobox_jsonld"},
        ))

    return sorted(events, key=lambda e: e["start"])


# ---------------------------------------------------------------------------
# 5. DETERMINISTIC: RECURRING RULE COLLECTOR
# ---------------------------------------------------------------------------

def collect_recurring(venue_cfg, window_start, window_end):
    events = []
    start_day = window_start.date() - timedelta(days=1)
    end_day = window_end.date()

    for rule in venue_cfg.get("rules", []):
        target_weekdays = {WEEKDAY_MAP[d.upper()] for d in rule.get("weekdays", []) if d.upper() in WEEKDAY_MAP}
        sh, sm = (int(x) for x in rule["start_time"].split(":"))
        eh, em = ((int(x) for x in rule["end_time"].split(":")) if rule.get("end_time") else (None, None))

        day = start_day
        while day <= end_day:
            if day.weekday() in target_weekdays:
                start_dt = datetime(day.year, day.month, day.day, sh, sm, tzinfo=EASTERN)
                end_dt = None
                if eh is not None:
                    end_day_dt = day + timedelta(days=1) if (eh, em) <= (sh, sm) else day
                    end_dt = datetime(end_day_dt.year, end_day_dt.month, end_day_dt.day, eh, em, tzinfo=EASTERN)
                if in_window(start_dt, end_dt, window_start, window_end):
                    events.append(base_event(
                        venue_cfg,
                        title=rule["title"],
                        start=start_dt.isoformat(),
                        end=end_dt.isoformat() if end_dt else None,
                        url=venue_cfg["url"],
                        description=rule.get("description", ""),
                        extra={"collector": "recurring", "recurring_rule": True},
                    ))
            day += timedelta(days=1)

    return sorted(events, key=lambda e: e["start"])


# ---------------------------------------------------------------------------
# 6. DETERMINISTIC: ICS CALENDAR COLLECTOR
# ---------------------------------------------------------------------------

def collect_ics(venue_cfg, window_start, window_end):
    from calendar_collector import collect_ics_events

    raw_events = collect_ics_events(
        calendar_url=venue_cfg["calendar_url"],
        venue=venue_cfg["venue"],
        address=venue_cfg.get("address", ""),
        source_name=venue_cfg["venue"],
        event_url=venue_cfg["url"],
        days_ahead=DAYS_AHEAD,
        now=window_start,
    )
    enriched = []
    for ev in raw_events:
        enriched.append(base_event(
            venue_cfg,
            title=ev["title"],
            start=ev["start"],
            end=ev.get("end"),
            url=ev.get("url") or venue_cfg["url"],
            description=ev.get("description", ""),
            source_id=ev.get("id"),
            extra={"collector": "ics"},
        ))
    return enriched


# ---------------------------------------------------------------------------
# 7. HYBRID AI: HASH-CACHED LLM HTML STRUCTURED EXTRACTOR
# ---------------------------------------------------------------------------

LLM_EXTRACTION_SCHEMA = {
    "type": "object",
    "properties": {
        "events": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "date": {"type": "string", "description": "YYYY-MM-DD in America/New_York"},
                    "start_time": {"type": "string", "description": "HH:MM 24-hour format like 19:30, or empty string if not printed"},
                    "end_time": {"type": "string", "description": "HH:MM 24-hour format like 22:00, or empty string if not printed"},
                    "price": {"type": "string", "description": "Price like 'Free' or '$15' if printed, or empty string"},
                    "category": {"type": "string", "enum": ["Live Music", "DJ", "Social"]},
                    "summary": {"type": "string", "description": "Short detail if the page gives extra info (lineup/vibe), else empty string"},
                    "source_quote": {"type": "string", "description": "Short verbatim snippet from the page text proving this event exists"},
                },
                "required": ["title", "date", "start_time", "category", "source_quote"],
            },
        }
    },
    "required": ["events"],
}


def build_llm_prompt(venue_cfg, clean_text, window_start, window_end):
    hint = venue_cfg.get("llm_hint", "")
    return (
        f"You extract ALL upcoming nightlife/music/social events for Happenin' (Cambridge/Somerville/Boston, America/New_York).\n"
        f"Today is {window_start.strftime('%A, %Y-%m-%d')}.\n"
        f"Extract EVERY single event occurring between {window_start.date().isoformat()} and {window_end.date().isoformat()} (do not stop after one event!).\n"
        f"Venue: {venue_cfg['venue']} ({venue_cfg.get('address', '')}, {venue_cfg.get('city', '')})\n"
        f"{('Venue hint: ' + hint) if hint else ''}\n"
        "STRICT RULES:\n"
        "1. Extract EVERY matching event in the 14-day window — typically 5 to 25 events on a busy music calendar.\n"
        "2. NEVER invent events, dates, or times that are not explicitly on the page.\n"
        "3. Format start_time and end_time strictly as HH:MM 24-hour (e.g. '19:30', '20:00') or empty string '' if not printed.\n"
        "4. Deduplicate only if the exact same show is listed twice.\n"
        "5. source_quote MUST be a short verbatim substring from the page text below.\n\n"
        "--- PAGE TEXT ---\n"
        f"{clean_text[:24000]}\n"
        "--- END PAGE TEXT ---"
    )


DEFAULT_GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")


def call_gemini_rest(prompt, api_key, model=DEFAULT_GEMINI_MODEL):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.1,
            "maxOutputTokens": 8192,
            "responseMimeType": "application/json",
            "responseSchema": LLM_EXTRACTION_SCHEMA,
        },
    }
    resp = requests.post(
        url,
        headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
        json=payload,
        timeout=90,
    )
    resp.raise_for_status()
    data = resp.json()
    text = data["candidates"][0]["content"]["parts"][0]["text"]
    return json.loads(text)


def call_openai_rest(prompt, api_key, model="gpt-4o-mini"):
    url = "https://api.openai.com/v1/chat/completions"
    payload = {
        "model": model,
        "temperature": 0.0,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": "Return strict JSON matching {\"events\": [{\"title\", \"date\" (YYYY-MM-DD), \"start_time\" (HH:MM or null), \"end_time\" (HH:MM or null), \"category\" ('Live Music'|'DJ'|'Social'), \"summary\", \"source_quote\"}]}."},
            {"role": "user", "content": prompt},
        ],
    }
    resp = requests.post(
        url,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json=payload,
        timeout=45,
    )
    resp.raise_for_status()
    text = resp.json()["choices"][0]["message"]["content"]
    return json.loads(text)


def validate_llm_events(raw_items, venue_cfg, clean_text, window_start, window_end):
    normalized_page = re.sub(r"\s+", " ", clean_text).casefold()
    accepted = []
    rejected = []

    for item in raw_items:
        title = str(item.get("title") or "").strip()
        date_str = str(item.get("date") or "").strip()
        quote = str(item.get("source_quote") or "").strip()

        if not title or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date_str):
            rejected.append((title or "(missing)", "missing title or invalid YYYY-MM-DD date"))
            continue

        quote_norm = re.sub(r"\s+", " ", quote).casefold()
        if not quote_norm or quote_norm not in normalized_page:
            rejected.append((title, f"source_quote not found verbatim on page: {quote!r}"))
            continue

        raw_start = str(item.get("start_time") or "").strip()
        m_start = re.search(r"\b(\d{1,2}):(\d{2})\b", raw_start)
        start_time_inferred = False
        if m_start:
            sh, sm = int(m_start.group(1)), int(m_start.group(2))
        else:
            fallback = venue_cfg.get("default_start_time")
            if not fallback:
                rejected.append((title, "no start_time printed and no default_start_time configured"))
                continue
            sh, sm = (int(x) for x in fallback.split(":"))
            start_time_inferred = True

        if not (0 <= sh <= 23 and 0 <= sm <= 59):
            rejected.append((title, f"invalid start_time {raw_start!r}"))
            continue

        y, mo, d = (int(x) for x in date_str.split("-"))
        start_dt = datetime(y, mo, d, sh, sm, tzinfo=EASTERN)

        end_dt = None
        raw_end = str(item.get("end_time") or "").strip()
        m_end = re.search(r"\b(\d{1,2}):(\d{2})\b", raw_end)
        if m_end:
            eh, em = int(m_end.group(1)), int(m_end.group(2))
            if 0 <= eh <= 23 and 0 <= em <= 59:
                end_day = start_dt.date() + timedelta(days=1) if (eh, em) <= (sh, sm) else start_dt.date()
                end_dt = datetime(end_day.year, end_day.month, end_day.day, eh, em, tzinfo=EASTERN)

        if not in_window(start_dt, end_dt, window_start, window_end):
            rejected.append((title, f"outside 14-day window ({date_str})"))
            continue

        item_price = str(item.get("price") or "").strip() or None
        accepted.append(base_event(
            venue_cfg,
            title=title,
            start=start_dt.isoformat(),
            end=end_dt.isoformat() if end_dt else None,
            url=venue_cfg["url"],
            description=str(item.get("summary") or "").strip(),
            price=item_price,
            extra={
                "collector": "llm_html",
                "ai_category": item.get("category") or venue_cfg.get("default_category"),
                "start_time_inferred": start_time_inferred,
                "source_quote": quote,
            },
        ))

    return sorted(accepted, key=lambda e: e["start"]), rejected


def collect_llm_html(venue_cfg, window_start, window_end, *, dry_run=False, use_cache=True):
    resp = requests.get(venue_cfg["url"], headers=HEADERS, timeout=20)
    resp.raise_for_status()
    raw_bytes = len(resp.text)
    clean_text = html_to_clean_text(resp.text)
    content_hash = hashlib.sha256(clean_text.encode("utf-8")).hexdigest()[:16]

    print(f"  [llm_html] fetched {raw_bytes:,} bytes -> {len(clean_text):,} chars clean text (hash={content_hash})")

    cache = load_cache()
    cache_key = venue_cfg["id"]
    cached = cache.get(cache_key)
    if use_cache and cached and cached.get("content_hash") == content_hash:
        print("  [llm_html] CACHE HIT (page unchanged -> $0 LLM call)")
        events, rejected = validate_llm_events(cached["raw_events"], venue_cfg, clean_text, window_start, window_end)
        for title, reason in rejected:
            print(f"  [llm_html] skipped {title!r}: {reason}")
        return events

    gemini_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    openai_key = os.getenv("OPENAI_API_KEY")

    if dry_run or (not gemini_key and not openai_key):
        reason = "--dry-run enabled" if dry_run else "no GEMINI_API_KEY or OPENAI_API_KEY set"
        print(f"  [llm_html] Skipping live LLM call ({reason}).")
        return []

    prompt = build_llm_prompt(venue_cfg, clean_text, window_start, window_end)
    if gemini_key:
        print(f"  [llm_html] Calling {DEFAULT_GEMINI_MODEL} (structured JSON)...")
        parsed = call_gemini_rest(prompt, gemini_key)
        provider = DEFAULT_GEMINI_MODEL
    else:
        print("  [llm_html] Calling OpenAI gpt-4o-mini (structured JSON)...")
        parsed = call_openai_rest(prompt, openai_key)
        provider = "gpt-4o-mini"

    raw_items = parsed.get("events", []) if isinstance(parsed, dict) else []
    cache[cache_key] = {
        "content_hash": content_hash,
        "provider": provider,
        "extracted_at": datetime.now(EASTERN).isoformat(timespec="seconds"),
        "raw_events": raw_items,
    }
    save_cache(cache)

    events, rejected = validate_llm_events(raw_items, venue_cfg, clean_text, window_start, window_end)
    for title, reason in rejected:
        print(f"  [llm_html] rejected {title!r}: {reason}")
    return events


# ---------------------------------------------------------------------------
# 6b. DETERMINISTIC: TOCKIFY PUBLIC CALENDAR JSON API
# ---------------------------------------------------------------------------

def collect_tockify(venue_cfg, window_start, window_end):
    calname = venue_cfg["tockify_calendar"]
    start_ms = int((window_start - timedelta(hours=6)).timestamp() * 1000)
    end_ms = int(window_end.timestamp() * 1000)
    resp = requests.get(
        "https://tockify.com/api/ngevent",
        params={"calname": calname, "startms": start_ms, "endms": end_ms, "max": 100},
        headers=HEADERS,
        timeout=20,
    )
    resp.raise_for_status()
    payload = resp.json()
    raw_events = payload.get("events") or []

    events = []
    for item in raw_events:
        when = item.get("when") or {}
        if when.get("allDay"):
            continue
        start_ms_val = (when.get("start") or {}).get("millis")
        if not start_ms_val:
            continue
        start_dt = datetime.fromtimestamp(start_ms_val / 1000.0, tz=timezone.utc).astimezone(EASTERN)
        end_ms_val = (when.get("end") or {}).get("millis")
        end_dt = None
        if end_ms_val and end_ms_val > start_ms_val:
            end_dt = datetime.fromtimestamp(end_ms_val / 1000.0, tz=timezone.utc).astimezone(EASTERN)

        if not in_window(start_dt, end_dt, window_start, window_end):
            continue

        content = item.get("content") or {}
        title = html_lib.unescape(str((content.get("summary") or {}).get("text") or "")).strip()
        if not title or CLOSURE_RE.search(title):
            continue

        desc_raw = (content.get("description") or {}).get("text") or ""
        desc = strip_html_inline(desc_raw)
        if len(desc) > 500:
            desc = desc[:497].rsplit(" ", 1)[0] + "..."

        cost = html_lib.unescape(str(content.get("cost") or "")).strip() or None
        event_url = content.get("customButtonLink") or venue_cfg["url"]
        eid = (item.get("eid") or {}).get("uid") or f"{title}|{start_dt.isoformat()}"

        image_url = None
        img_sets = content.get("imageSets") or []
        if isinstance(img_sets, list) and img_sets and isinstance(img_sets[0], dict):
            image_url = img_sets[0].get("url")

        events.append(base_event(
            venue_cfg,
            title=title,
            start=start_dt.isoformat(),
            end=end_dt.isoformat() if end_dt else None,
            url=event_url,
            description=desc,
            source_id=f"tockify:{venue_cfg['id']}:{eid}",
            image_url=image_url,
            price=cost,
            extra={"collector": "tockify"},
        ))

    return sorted(events, key=lambda e: e["start"])


# ---------------------------------------------------------------------------
# 6c. DETERMINISTIC: WIX EVENTS /event-details JSON-LD COLLECTOR
# ---------------------------------------------------------------------------

def collect_wix_events_jsonld(venue_cfg, window_start, window_end):
    from urllib.parse import urljoin

    resp = requests.get(venue_cfg["url"], headers=HEADERS, timeout=20)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    detail_urls = []
    seen = set()
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "/event-details/" not in href:
            continue
        full = urljoin(resp.url, href).split("?")[0].rstrip("/")
        if full not in seen:
            seen.add(full)
            detail_urls.append(full)
        if len(detail_urls) >= int(venue_cfg.get("max_detail_pages", 15)):
            break

    events = []
    for durl in detail_urls:
        try:
            dr = requests.get(durl, headers=HEADERS, timeout=15)
            if dr.status_code != 200:
                continue
        except requests.RequestException:
            continue

        dsoup = BeautifulSoup(dr.text, "html.parser")
        for script in dsoup.find_all("script", type="application/ld+json"):
            try:
                blob = json.loads(script.get_text() or "")
            except json.JSONDecodeError:
                continue
            nodes = blob if isinstance(blob, list) else (blob.get("@graph") if isinstance(blob, dict) and "@graph" in blob else [blob])
            for node in nodes:
                if not isinstance(node, dict):
                    continue
                ntype = str(node.get("@type") or "")
                if "Event" not in ntype:
                    continue
                title = html_lib.unescape(str(node.get("name") or "")).strip()
                if not title or CLOSURE_RE.search(title):
                    continue
                start_dt = parse_iso_eastern(node.get("startDate"))
                if start_dt is None:
                    continue
                end_dt = parse_iso_eastern(node.get("endDate"))
                if end_dt is not None and end_dt <= start_dt:
                    end_dt = None
                if not in_window(start_dt, end_dt, window_start, window_end):
                    continue

                desc = strip_html_inline(node.get("description") or "")
                if len(desc) > 500:
                    desc = desc[:497].rsplit(" ", 1)[0] + "..."

                img = node.get("image")
                if isinstance(img, list) and img:
                    img = img[0]
                if isinstance(img, dict):
                    img = img.get("url")
                image_url = img if isinstance(img, str) else None

                price = None
                offers = node.get("offers")
                if isinstance(offers, list) and offers:
                    offers = offers[0]
                if isinstance(offers, dict):
                    p = offers.get("price") or offers.get("lowPrice")
                    if p not in (None, ""):
                        try:
                            val = float(p)
                            price = "Free" if val == 0 else f"${int(round(val))}"
                        except (TypeError, ValueError):
                            price = str(p)

                events.append(base_event(
                    venue_cfg,
                    title=title,
                    start=start_dt.isoformat(),
                    end=end_dt.isoformat() if end_dt else None,
                    url=durl,
                    description=desc,
                    source_id=f"wix:{venue_cfg['id']}:{durl.rsplit('/', 1)[-1]}",
                    image_url=image_url,
                    price=price,
                    extra={"collector": "wix_events_jsonld"},
                ))
                break

    return sorted(events, key=lambda e: e["start"])


# ---------------------------------------------------------------------------
# RUNNER
# ---------------------------------------------------------------------------

def run(venue_filter=None, dry_run=False, use_cache=True):
    registry = json.loads(VENUES_PATH.read_text(encoding="utf-8"))
    window_start = datetime.now(EASTERN)
    window_end = window_start + timedelta(days=DAYS_AHEAD)

    print("HAPPENIN' — HYBRID COLLECTOR")
    print(f"Window: {window_start.isoformat(timespec='seconds')} -> {window_end.isoformat(timespec='seconds')}\n")

    all_events = []
    failures = []

    for venue_cfg in registry.get("venues", []):
        if venue_filter and venue_cfg["id"] != venue_filter:
            continue
        if not venue_filter and not venue_cfg.get("enabled", False):
            continue

        ctype = venue_cfg["collector_type"]
        print(f"[{venue_cfg['id']}] {venue_cfg['venue']} ({ctype})")
        try:
            if ctype == "tunehatch":
                found = collect_tunehatch(venue_cfg, window_start, window_end)
            elif ctype == "tribe_api":
                found = collect_tribe_api(venue_cfg, window_start, window_end)
            elif ctype == "squarespace_json":
                found = collect_squarespace_json(venue_cfg, window_start, window_end)
            elif ctype == "bentobox_jsonld":
                found = collect_bentobox_jsonld(venue_cfg, window_start, window_end)
            elif ctype == "recurring":
                found = collect_recurring(venue_cfg, window_start, window_end)
            elif ctype == "ics":
                found = collect_ics(venue_cfg, window_start, window_end)
            elif ctype == "tockify":
                found = collect_tockify(venue_cfg, window_start, window_end)
            elif ctype == "wix_events_jsonld":
                found = collect_wix_events_jsonld(venue_cfg, window_start, window_end)
            elif ctype == "llm_html":
                found = collect_llm_html(venue_cfg, window_start, window_end, dry_run=dry_run, use_cache=use_cache)
            else:
                print(f"  [skip] unsupported collector_type: {ctype}")
                continue
            print(f"  -> collected {len(found)} event(s)\n")
            all_events.extend(found)
        except Exception as exc:
            print(f"  [ERROR] {type(exc).__name__}: {exc}\n")
            failures.append((venue_cfg["id"], f"{type(exc).__name__}: {exc}"))

    all_events.sort(key=lambda e: e["start"])
    OUTPUT_PATH.write_text(json.dumps(all_events, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print("=" * 55)
    print(f"Total hybrid events: {len(all_events)}")
    print(f"Failed venues:       {len(failures)}")
    print(f"Saved:               {OUTPUT_PATH}")
    print("=" * 55)
    for ev in all_events[:20]:
        print(f"  {ev['start'][:16]} | {ev['venue']:<26} | {ev['title']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Happenin' hybrid config-driven collector")
    parser.add_argument("--venue", help="Run a single venue id from venues.json")
    parser.add_argument("--dry-run", action="store_true", help="Skip live LLM API calls")
    parser.add_argument("--no-cache", action="store_true", help="Ignore cached LLM extractions")
    args = parser.parse_args()
    run(venue_filter=args.venue, dry_run=args.dry_run, use_cache=not args.no_cache)
