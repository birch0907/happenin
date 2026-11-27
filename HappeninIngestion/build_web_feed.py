"""Build a live, coordinate-verified events.json feed for HappeninWeb.

Combines:
  1. prototype_events.json (from hybrid_collector.py: Mad Monkfish, ManRay, Havana Club, McCarthy's, etc.)
  2. Existing fast Cambridge/Boston collectors (Lilypad, Lou's, Plough & Stars, Lamplighter, Ticketmaster)
     with fault isolation and verified coordinates stamped from venues.json.

Non-destructive: writes ONLY to HappeninWeb/public/events.json.
"""
import argparse
import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from happenin_deduplication import deduplicate, normalize
from ingest import event_is_in_time_window

POSH_SPAM_RE = re.compile(
    r"(⛔|🆓|free\s*entry|guest\s*list|text\s+for|promo\s*code|fr🥶st|fr❄️st|free\s+before\s+\d)",
    re.I,
)
EMOJI_RE = re.compile(r"[\U0001F300-\U0001FAFF\u2600-\u27BF]")


def is_promoter_spam(event):
    """Filter noisy third-party promoter guestlist spam while keeping genuine POSH events."""
    if event.get("source_name") != "POSH":
        return False
    title = str(event.get("title") or "")
    if POSH_SPAM_RE.search(title):
        return True
    # Heavy emoji spam titles (4+ emojis) are almost always duplicate promoter blasts.
    if len(EMOJI_RE.findall(title)) >= 4:
        return True
    return False

ROOT = Path(__file__).resolve().parent
VENUES_PATH = ROOT / "venues.json"
PROTOTYPE_PATH = ROOT / "prototype_events.json"
WEB_OUTPUT_PATH = ROOT.parent / "HappeninWeb" / "public" / "events.json"

EASTERN = ZoneInfo("America/New_York")
DAYS_AHEAD = 14


def build_venue_coord_lookup():
    registry = json.loads(VENUES_PATH.read_text(encoding="utf-8"))
    lookup = {}
    for v in registry.get("venues", []):
        if v.get("latitude") is None or v.get("longitude") is None:
            continue
        info = {
            "venue": v["venue"],
            "address": v.get("address"),
            "city": v.get("city"),
            "state": v.get("state"),
            "postal_code": v.get("postal_code"),
            "latitude": v["latitude"],
            "longitude": v["longitude"],
            "location_precision": "street",
            "default_admission": v.get("default_admission"),
            "default_price": v.get("default_price"),
        }
        lookup[normalize(v["venue"])] = info
        lookup[normalize(v["id"])] = info
    # Common short aliases used by older collectors
    aliases = {
        "sinclair": "the sinclair",
        "the sinclair music hall": "the sinclair",
        "lilypad": "the lilypad",
        "plough and stars": "the plough and stars",
        "lamplighter": "lamplighter brewing co",
        "lamplighter brewing co": "lamplighter brewing co",
        "lamplighter brewing co broadway": "lamplighter brewing co",
        "lous": "lou s",
        "99 franklin st": "exit galleries",
        "exit galleries allston": "exit galleries",
    }
    for alias, target in aliases.items():
        if target in lookup:
            lookup[alias] = lookup[target]
    return lookup


def enrich_coordinates(events, coord_lookup):
    enriched_count = 0
    for ev in events:
        for candidate in (ev.get("venue"), ev.get("source_name")):
            key = normalize(candidate)
            if key in coord_lookup:
                info = coord_lookup[key]
                if ev.get("latitude") is None or ev.get("longitude") is None:
                    ev["latitude"] = info["latitude"]
                    ev["longitude"] = info["longitude"]
                    ev["location_precision"] = "street"
                    enriched_count += 1
                if not ev.get("address") and info.get("address"):
                    ev["address"] = info["address"]
                if not ev.get("city") and info.get("city"):
                    ev["city"] = info["city"]
                if not ev.get("state") and info.get("state"):
                    ev["state"] = info["state"]
                if not ev.get("admission_type") and info.get("default_admission"):
                    ev["admission_type"] = info["default_admission"]
                if not ev.get("price") and info.get("default_price"):
                    ev["price"] = info["default_price"]
                break
    return enriched_count


def infer_region(event):
    if event.get("region") in {"boston", "seacoast"}:
        return event["region"]
    state = str(event.get("state") or "").strip().upper()
    if state == "NH":
        return "seacoast"
    lat = event.get("latitude")
    if isinstance(lat, (int, float)) and lat >= 42.82:
        return "seacoast"
    return "boston"


def main(with_posh=False, with_sinclair=False, skip_ai=False):
    window_start = datetime.now(EASTERN)
    window_end = window_start + timedelta(days=DAYS_AHEAD)
    coord_lookup = build_venue_coord_lookup()

    print("HAPPENIN' — BUILDING LIVE WEB FEED")
    print(f"Window: {window_start.isoformat(timespec='seconds')} -> {window_end.isoformat(timespec='seconds')}\n")

    all_events = []

    if PROTOTYPE_PATH.exists():
        proto = json.loads(PROTOTYPE_PATH.read_text(encoding="utf-8"))
        print(f"Loaded prototype_events.json: {len(proto)} events")
        all_events.extend(proto)

    from lamplighter import collect_lamplighter_events
    from lilypad import collect_lilypad_events
    from lous import collect_lous_events
    from plough import collect_plough_events
    from ticketmaster import collect_ticketmaster_events

    collectors = [
        ("Lilypad", collect_lilypad_events),
        ("Lou's", collect_lous_events),
        ("Plough and Stars", collect_plough_events),
        ("Lamplighter", collect_lamplighter_events),
        ("Ticketmaster (Boston)", lambda: collect_ticketmaster_events(region="boston")),
        (
            "Ticketmaster (Seacoast NH)",
            lambda: collect_ticketmaster_events(
                center_lat=43.02, center_lng=-70.80, radius_miles=18, region="seacoast"
            ),
        ),
    ]
    if with_sinclair:
        from sinclair import collect_sinclair_events
        collectors.append(("Sinclair", collect_sinclair_events))
    if with_posh:
        from posh import collect_posh_events
        collectors.append(("POSH", collect_posh_events))

    for name, fn in collectors:
        try:
            print(f"Collecting {name}...")
            found = fn()
            print(f"  -> {len(found)} events")
            all_events.extend(found)
        except Exception as exc:
            print(f"  [warn] {name} failed: {type(exc).__name__}: {exc}")

    enriched = enrich_coordinates(all_events, coord_lookup)
    print(f"\nStamped verified venue coordinates onto {enriched} first-party events.")

    for ev in all_events:
        ev["region"] = infer_region(ev)

    spam_filtered = [e for e in all_events if not is_promoter_spam(e)]
    removed_spam = len(all_events) - len(spam_filtered)
    if removed_spam:
        print(f"Filtered {removed_spam} noisy POSH promoter/guestlist spam listings.")

    windowed = [e for e in spam_filtered if event_is_in_time_window(e, window_start, window_end)]
    unique_events, groups = deduplicate(windowed)
    unique_events.sort(key=lambda e: e["start"])

    if not skip_ai:
        from ai_enricher import enrich_events
        unique_events = enrich_events(unique_events)

    WEB_OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    WEB_OUTPUT_PATH.write_text(
        json.dumps(unique_events, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    with_coords = sum(1 for e in unique_events if e.get("latitude") is not None and e.get("longitude") is not None)
    print("=" * 55)
    print(f"Total unique live events: {len(unique_events)} ({with_coords} with map coordinates)")
    print(f"Duplicate groups merged:  {len(groups)}")
    print(f"Written to: {WEB_OUTPUT_PATH}")
    print("=" * 55)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--with-posh", action="store_true", help="Include POSH collector (slower)")
    parser.add_argument("--with-sinclair", action="store_true", help="Include Sinclair detail scraper")
    parser.add_argument("--skip-ai", action="store_true", help="Skip AI summary/tag enrichment")
    args = parser.parse_args()
    main(with_posh=args.with_posh, with_sinclair=args.with_sinclair, skip_ai=args.skip_ai)
