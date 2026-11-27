"""Happenin' cached AI event enricher (summaries, categories, vibe tags, prices).

Processes events in batches (25 events/request) and caches permanently by event
identity in cache/ai_enrichment_cache.json so you NEVER pay twice for the same event.

Supports:
  - GEMINI_API_KEY (or GOOGLE_API_KEY) -> Gemini 2.5 Flash (thinkingBudget=0, ~$0.08/350 events)
  - OPENAI_API_KEY                     -> gpt-4o-mini (~$0.03/350 events)

Usage:
  python ai_enricher.py                # Enrich HappeninWeb/public/events.json in place
  python ai_enricher.py --dry-run      # Show how many uncached events would be sent & est. cost
  python ai_enricher.py --limit 25     # Enrich at most 25 uncached events (great for a quick test)
"""
import argparse
import hashlib
import json
import os
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

ROOT = Path(__file__).resolve().parent
CACHE_PATH = ROOT / "cache" / "ai_enrichment_cache.json"
CONTENT_FILTERS_PATH = ROOT / "content_filters.json"
DEFAULT_FEED_PATH = ROOT.parent / "HappeninWeb" / "public" / "events.json"
EASTERN = ZoneInfo("America/New_York")
BATCH_SIZE = 25
RATING_BATCH_SIZE = 50
RATING_ORDER = {"PG": 0, "R": 1, "Explicit": 2}


def load_local_env():
    """Load simple KEY=VALUE pairs from HappeninIngestion/.env if present."""
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


load_local_env()

ENRICH_SCHEMA = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "key": {"type": "string"},
                    "category": {"type": "string", "enum": ["Live Music", "DJ", "Social", "Exclude"]},
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "1 to 3 short vibe/genre/age tags like 'Jazz', 'Indie Rock', 'House', 'Trivia', '21+'",
                    },
                    "price": {
                        "type": "string",
                        "nullable": True,
                        "description": "Short cover/ticket price like 'Free', '$10', '$15–$25' ONLY if stated; otherwise null",
                    },
                    "summary": {
                        "type": "string",
                        "description": "1-2 crisp, helpful sentences for someone deciding where to go tonight. Never invent facts not in the input.",
                    },
                    "content_rating": {
                        "type": "string",
                        "enum": ["PG", "R", "Explicit"],
                        "description": "Hospitality safety rating for hotel concierges: PG (mainstream/hotel-safe), R (edgy adult nightlife/cheeky comedy/burlesque/punk/rave), Explicit (fetish/kink/BDSM/sexually explicit/explicit profanity in title).",
                    },
                    "safety_reason": {
                        "type": "string",
                        "description": "Empty string for PG; short 2-6 word reason for R or Explicit (e.g. 'Kink/fetish night', 'Adult burlesque comedy').",
                    },
                },
                "required": ["key", "category", "tags", "summary", "content_rating", "safety_reason"],
            },
        }
    },
    "required": ["items"],
}

RATE_ONLY_SCHEMA = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "key": {"type": "string"},
                    "content_rating": {"type": "string", "enum": ["PG", "R", "Explicit"]},
                    "safety_reason": {"type": "string"},
                },
                "required": ["key", "content_rating", "safety_reason"],
            },
        }
    },
    "required": ["items"],
}


def load_content_filters():
    if CONTENT_FILTERS_PATH.exists():
        try:
            cfg = json.loads(CONTENT_FILTERS_PATH.read_text(encoding="utf-8"))
            return {
                "exclude_venues": {str(v).strip().lower() for v in cfg.get("exclude_from_hotels_venues", []) if v},
                "explicit_res": [re.compile(p, re.I) for p in cfg.get("explicit_patterns", [])],
                "r_res": [re.compile(p, re.I) for p in cfg.get("r_rated_patterns", [])],
                "allow_titles": [str(t).strip().lower() for t in cfg.get("allow_title_overrides", []) if t],
            }
        except (OSError, json.JSONDecodeError, re.error) as exc:
            print(f"  [warn] Could not parse content_filters.json: {exc}")
    return {"exclude_venues": set(), "explicit_res": [], "r_res": [], "allow_titles": []}


def evaluate_deterministic_safety(event, filters):
    """Layer 1 deterministic hospitality safety check (always runs, $0 cost)."""
    venue_norm = re.sub(r"[^a-z0-9]+", "", str(event.get("venue") or "").lower())
    title = str(event.get("title") or "")
    title_lower = title.lower()
    blob = f"{title} {event.get('description') or ''} {event.get('ai_summary') or ''}"

    venue_blocked = any(re.sub(r"[^a-z0-9]+", "", v) == venue_norm for v in filters["exclude_venues"])
    if any(tok in title_lower for tok in filters["allow_titles"]):
        return "PG", ("Venue excluded for hotels" if venue_blocked else ""), venue_blocked

    for rx in filters["explicit_res"]:
        m = rx.search(blob)
        if m:
            return "Explicit", f"Keyword guardrail ({m.group(0)})", True

    for rx in filters["r_res"]:
        m = rx.search(blob)
        if m:
            return "R", f"Edgy nightlife ({m.group(0)})", venue_blocked

    if venue_blocked:
        return "PG", f"Venue excluded for hotels ({event.get('venue')})", True

    return "PG", "", False


def event_cache_key(event):
    """Stable identity key so repeated daily ingests hit the cache at $0 cost."""
    raw = "|".join([
        str(event.get("source_name") or "").strip().lower(),
        str(event.get("venue") or "").strip().lower(),
        str(event.get("title") or "").strip().lower(),
        str(event.get("start") or "")[:16],
    ])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


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


def compact_event_input(key, event):
    desc = re.sub(r"<[^>]*>", " ", str(event.get("description") or ""))
    desc = re.sub(r"\s+", " ", desc).strip()[:320]
    return {
        "key": key,
        "title": event.get("title"),
        "venue": event.get("venue"),
        "city": event.get("city"),
        "start": event.get("start"),
        "genre": event.get("genre"),
        "subgenre": event.get("subgenre"),
        "price": event.get("price"),
        "ages": event.get("ages"),
        "default_category": event.get("default_category"),
        "description": desc or None,
    }


def build_prompt(batch_inputs):
    return (
        "You enrich nightlife and social event cards for Happenin' (Cambridge/Somerville/Boston).\n"
        "For each event in the JSON array below, return an enriched object with the EXACT same `key`:\n"
        "- `category`: Choose one of 'Live Music', 'DJ', 'Social', or 'Exclude'.\n"
        "  * Use 'DJ' for DJ sets, dance nights, house/techno/EDM, salsa/bachata dance parties, goth/industrial club nights.\n"
        "  * Use 'Live Music' for concerts, bands, jazz, acoustic, open jams, Irish sessions.\n"
        "  * Use 'Social' for comedy, trivia, karaoke, drag, poetry slam, open mic, craft nights, mixers, markets, theater.\n"
        "  * Use 'Exclude' ONLY for non-events: parking passes, VIP upgrades, ticket add-ons, venue closure notices, or sports games.\n"
        "- `tags`: 1 to 3 crisp, helpful tags (e.g. ['Jazz', 'Late Night'], ['Indie Rock', '21+'], ['Comedy']). No generic filler.\n"
        "- `price`: Short string like 'Free' or '$15' ONLY if explicitly present in the input; otherwise null.\n"
        "- `summary`: 1-2 crisp sentences ONLY if the description has real extra details (lineup, vibe, special guests, theme, lesson time).\n"
        "  * If the input has NO description or no real info beyond title/venue/time, return an EMPTY STRING \"\" rather than restating the title.\n"
        "  * Never invent times, lineups, drink specials, or details not in the input.\n"
        "  * Strip promotional boilerplate ('Make reservations here!', 'Click link in bio').\n"
        "- `content_rating`: Hospitality content rating for hotel concierge safety:\n"
        "  * 'PG' — Mainstream & upscale hotel-safe: concerts, jazz, indie rock, trivia, karaoke, salsa, regular DJ/dance nights, mainstream stand-up comedy (e.g. touring theater comics), open mics, markets, cultural events.\n"
        "  * 'R' — Edgy adult nightlife (suitable for rock/nightlife hotels like The Verb, NOT conservative luxury hotels like The Charles): profanity/raunchy comedy titles (e.g. 'Sh!t-Faced Shakespeare'), burlesque shows, cheeky adult drag/club nights, raves, extreme metal/gore-themed bills.\n"
        "  * 'Explicit' — Hidden from ALL hotels (Happenin' only): fetish/kink/BDSM/leather/dungeon nights, sexually explicit events/storytelling ('Smut Slam', 'MASOCHISSIMO', 'Horny for...', 'Slutcracker'), or explicit slurs/profanity in titles.\n"
        "  * Use real context: 'Albert Lam Sextet' is PG jazz; 'Brett Goldstein: Sex, Death & Small Talk' at Wang Theatre is PG mainstream theater comedy.\n"
        "- `safety_reason`: Return \"\" for PG; for R or Explicit return a crisp 2-6 word reason.\n\n"
        "INPUT EVENTS:\n"
        + json.dumps(batch_inputs, ensure_ascii=False)
    )


def build_rating_only_prompt(batch_inputs):
    return (
        "Classify the hospitality content rating for each Greater Boston event below.\n"
        "For each item, return the EXACT same `key`, `content_rating` ('PG' | 'R' | 'Explicit'), and `safety_reason`:\n"
        "- 'PG': Mainstream & upscale hotel-safe (concerts, jazz, indie/rock bands, trivia, karaoke, salsa, regular DJ/dance nights, mainstream touring theater comedy, open mics, markets, run clubs, cultural showcases).\n"
        "- 'R': Edgy adult nightlife (suitable for rock/nightlife boutique hotels like The Verb, NOT conservative luxury hotels like The Charles): cheeky/profane comedy ('Sh!t-Faced Shakespeare'), burlesque shows, risqué adult drag/club parties, underground raves, extreme gore/metal themes.\n"
        "- 'Explicit': Hidden from ALL hotel concierges (Happenin' only): fetish/kink/BDSM/leather/dungeon nights, sexually explicit shows ('Smut Slam', 'MASOCHISSIMO', 'Horny for...', 'Slutcracker'), or explicit slurs/profanity in titles.\n"
        "- Use real context: 'Albert Lam Sextet' is PG jazz; 'GottaBal! Dance' is PG swing dance; mainstream theater comedy like Brett Goldstein is PG.\n"
        "- `safety_reason`: \"\" for PG; short 2-6 word reason for R or Explicit.\n\n"
        "INPUT EVENTS:\n"
        + json.dumps(batch_inputs, ensure_ascii=False)
    )


DEFAULT_GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")


def call_gemini(prompt, api_key, model=DEFAULT_GEMINI_MODEL, schema=None):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.2,
            "responseMimeType": "application/json",
            "responseSchema": schema or ENRICH_SCHEMA,
        },
    }
    resp = requests.post(
        url,
        headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
        json=payload,
        timeout=60,
    )
    resp.raise_for_status()
    text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
    return json.loads(text).get("items", [])


def call_openai(prompt, api_key, model="gpt-4o-mini"):
    url = "https://api.openai.com/v1/chat/completions"
    payload = {
        "model": model,
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
        "messages": [
            {
                "role": "system",
                "content": (
                    "Return strict JSON: {\"items\": [{\"key\", \"category\" ('Live Music'|'DJ'|'Social'|'Exclude'), "
                    "\"tags\" (array of 1-3 strings), \"price\" (string or null), \"summary\" (1-2 sentences)}]}."
                ),
            },
            {"role": "user", "content": prompt},
        ],
    }
    resp = requests.post(
        url,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json=payload,
        timeout=60,
    )
    resp.raise_for_status()
    text = resp.json()["choices"][0]["message"]["content"]
    return json.loads(text).get("items", [])


def enrich_events(events, *, dry_run=False, limit=None):
    cache = load_cache()
    missing = []
    seen_keys = set()

    for ev in events:
        k = event_cache_key(ev)
        if k not in cache and k not in seen_keys:
            seen_keys.add(k)
            missing.append((k, ev))

    cached_count = len(events) - len(missing)
    to_process = missing[:limit] if limit is not None else missing

    print(f"AI Enricher: {len(events)} events total | {cached_count} cached ($0) | {len(to_process)} to enrich")

    gemini_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    openai_key = os.getenv("OPENAI_API_KEY")

    if to_process and (dry_run or (not gemini_key and not openai_key)):
        est_batches = (len(to_process) + BATCH_SIZE - 1) // BATCH_SIZE
        est_cost = len(to_process) * 0.00025
        reason = "--dry-run enabled" if dry_run else "no GEMINI_API_KEY or OPENAI_API_KEY set"
        print(f"  Skipping live AI enrichment ({reason}).")
        print(f"  Would run {est_batches} batch call(s) (~${est_cost:.3f} est. total, cached permanently afterward).")
    elif to_process:
        provider = DEFAULT_GEMINI_MODEL if gemini_key else "gpt-4o-mini"
        print(f"  Using {provider} in batches of {BATCH_SIZE}...")
        for start_idx in range(0, len(to_process), BATCH_SIZE):
            chunk = to_process[start_idx : start_idx + BATCH_SIZE]
            batch_inputs = [compact_event_input(k, ev) for k, ev in chunk]
            prompt = build_prompt(batch_inputs)
            try:
                results = call_gemini(prompt, gemini_key) if gemini_key else call_openai(prompt, openai_key)
            except requests.HTTPError as exc:
                status = exc.response.status_code if exc.response is not None else None
                if status in {401, 402, 403}:
                    print(f"  [stop] API returned HTTP {status} (check API key / billing credits). Stopping remaining batches.")
                    break
                print(f"  [warn] batch {start_idx // BATCH_SIZE + 1} failed: HTTP {status}")
                continue
            except Exception as exc:
                print(f"  [warn] batch {start_idx // BATCH_SIZE + 1} failed: {type(exc).__name__}: {exc}")
                continue

            now_iso = datetime.now(EASTERN).isoformat(timespec="seconds")
            valid_keys = {k for k, _ in chunk}
            saved_in_batch = 0
            for item in results:
                k = item.get("key")
                if k not in valid_keys:
                    continue
                cat = item.get("category")
                if cat not in {"Live Music", "DJ", "Social", "Exclude"}:
                    continue
                tags = [str(t).strip() for t in (item.get("tags") or []) if str(t).strip()][:3]
                summary = str(item.get("summary") or "").strip()
                price = str(item["price"]).strip() if item.get("price") else None
                rating = item.get("content_rating")
                if rating not in RATING_ORDER:
                    rating = "PG"
                safety_reason = str(item.get("safety_reason") or "").strip() if rating != "PG" else ""
                cache[k] = {
                    "ai_category": cat,
                    "ai_tags": tags,
                    "ai_price": price,
                    "ai_summary": summary,
                    "ai_content_rating": rating,
                    "ai_safety_reason": safety_reason,
                    "provider": provider,
                    "enriched_at": now_iso,
                }
                saved_in_batch += 1
            save_cache(cache)
            print(f"  Batch {start_idx // BATCH_SIZE + 1}: enriched {saved_in_batch}/{len(chunk)} events")

    # Lightweight 1-time backfill for older cached events that predate content_rating
    missing_ratings = []
    seen_rate_keys = set()
    for ev in events:
        k = event_cache_key(ev)
        entry = cache.get(k)
        if entry and "ai_content_rating" not in entry and k not in seen_rate_keys:
            seen_rate_keys.add(k)
            missing_ratings.append((k, ev))

    if missing_ratings and not dry_run and (gemini_key or openai_key):
        print(f"AI Safety Backfill: {len(missing_ratings)} cached events need content_rating (batches of {RATING_BATCH_SIZE})...")
        for start_idx in range(0, len(missing_ratings), RATING_BATCH_SIZE):
            chunk = missing_ratings[start_idx : start_idx + RATING_BATCH_SIZE]
            batch_inputs = [compact_event_input(k, ev) for k, ev in chunk]
            prompt = build_rating_only_prompt(batch_inputs)
            try:
                results = (
                    call_gemini(prompt, gemini_key, schema=RATE_ONLY_SCHEMA)
                    if gemini_key
                    else call_openai(prompt, openai_key)
                )
            except requests.HTTPError as exc:
                status = exc.response.status_code if exc.response is not None else None
                if status in {401, 402, 403}:
                    print(f"  [stop] API returned HTTP {status}. Stopping rating backfill.")
                    break
                print(f"  [warn] rating batch {start_idx // RATING_BATCH_SIZE + 1} failed: HTTP {status}")
                continue
            except Exception as exc:
                print(f"  [warn] rating batch {start_idx // RATING_BATCH_SIZE + 1} failed: {type(exc).__name__}: {exc}")
                continue

            valid_keys = {k for k, _ in chunk}
            rated = 0
            for item in results:
                k = item.get("key")
                if k not in valid_keys or k not in cache:
                    continue
                rating = item.get("content_rating")
                if rating not in RATING_ORDER:
                    rating = "PG"
                cache[k]["ai_content_rating"] = rating
                cache[k]["ai_safety_reason"] = str(item.get("safety_reason") or "").strip() if rating != "PG" else ""
                rated += 1
            save_cache(cache)
            print(f"  Safety Batch {start_idx // RATING_BATCH_SIZE + 1}: rated {rated}/{len(chunk)} events")

    # Apply cached enrichments + Layer 1 deterministic safety guardrails onto every event.
    filters = load_content_filters()
    applied = 0
    rating_counts = {"PG": 0, "R": 0, "Explicit": 0}
    hotel_blocked_count = 0

    for ev in events:
        entry = cache.get(event_cache_key(ev))
        ai_rating = "PG"
        ai_reason = ""
        if entry:
            ev["ai_category"] = entry["ai_category"]
            ev["ai_tags"] = entry["ai_tags"]
            if entry.get("ai_price"):
                ev["ai_price"] = entry["ai_price"]
            if entry.get("ai_summary"):
                ev["ai_summary"] = entry["ai_summary"]
            ai_rating = entry.get("ai_content_rating") or "PG"
            ai_reason = entry.get("ai_safety_reason") or ""
            applied += 1

        # Strictest rating wins between Layer 1 (deterministic rules) and Layer 2 (AI)
        rule_rating, rule_reason, venue_or_rule_blocked = evaluate_deterministic_safety(ev, filters)
        title_lower = str(ev.get("title") or "").lower()
        if any(tok in title_lower for tok in filters["allow_titles"]):
            final_rating = "PG"
            final_reason = rule_reason
        elif RATING_ORDER.get(rule_rating, 0) >= RATING_ORDER.get(ai_rating, 0):
            final_rating = rule_rating
            final_reason = rule_reason or ai_reason
        else:
            final_rating = ai_rating
            final_reason = ai_reason or rule_reason

        hotel_blocked = bool(venue_or_rule_blocked or final_rating == "Explicit")
        ev["content_rating"] = final_rating
        ev["safety_reason"] = final_reason
        ev["hotel_blocked"] = hotel_blocked
        rating_counts[final_rating] = rating_counts.get(final_rating, 0) + 1
        if hotel_blocked:
            hotel_blocked_count += 1

    print(
        f"AI Enricher applied to {applied}/{len(events)} events | "
        f"Ratings: PG={rating_counts['PG']}, R={rating_counts['R']}, Explicit={rating_counts['Explicit']} "
        f"(hotel_blocked={hotel_blocked_count})."
    )
    return events


def main():
    parser = argparse.ArgumentParser(description="Happenin' cached AI event enricher")
    parser.add_argument("--input", default=str(DEFAULT_FEED_PATH), help="Path to events.json to enrich")
    parser.add_argument("--dry-run", action="store_true", help="Preview batch count & cost without calling LLM")
    parser.add_argument("--limit", type=int, default=None, help="Max new events to enrich this run")
    args = parser.parse_args()

    path = Path(args.input)
    if not path.exists():
        raise FileNotFoundError(f"Feed not found: {path}")

    events = json.loads(path.read_text(encoding="utf-8"))
    enriched = enrich_events(events, dry_run=args.dry_run, limit=args.limit)
    if not args.dry_run:
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(json.dumps(enriched, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        tmp.replace(path)
        print(f"Saved enriched feed: {path}")


if __name__ == "__main__":
    main()
