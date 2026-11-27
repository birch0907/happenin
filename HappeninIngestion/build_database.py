"""Happenin' Master Venue & Event Database Builder.

Combines:
  1. All 6 Greater Boston area venue research spreadsheets (Cambridge, Somerville,
     Boston proper, Allston/Brighton, JP/Dorchester/East Boston/Roxbury, Brookline)
  2. HappeninIngestion/venues.json (configured first-party collectors & recurring rules)
  3. HappeninWeb/public/events.json (live enriched 14-day events feed)

Outputs:
  - HappeninIngestion/venue_directory.json  (canonical master venue registry)
  - HappeninWeb/public/database.json        (unified payload for Happenin' Database UI)
"""
import json
import re
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import openpyxl

ROOT = Path(__file__).resolve().parent
DOWNLOADS = Path(r"C:\Users\birch\Downloads")
VENUES_JSON_PATH = ROOT / "venues.json"
EVENTS_JSON_PATH = ROOT.parent / "HappeninWeb" / "public" / "events.json"
DIRECTORY_OUT_PATH = ROOT / "venue_directory.json"
WEB_DB_OUT_PATH = ROOT.parent / "HappeninWeb" / "public" / "database.json"
EASTERN = ZoneInfo("America/New_York")


def norm(text: str) -> str:
    s = unicodedata.normalize("NFKD", str(text or ""))
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = s.casefold().replace("&", " and ")
    # Strip trailing sponsor text like "presented by citizens"
    s = re.sub(r"\bpresented by\b.*$", "", s)
    return " ".join(re.findall(r"[a-z0-9]+", s))


def norm_loose(text: str) -> str:
    s = norm(text)
    s = re.sub(r"^(the)\s+", "", s)
    s = re.sub(r"\s+(boston|cambridge|somerville|brookline|allston|brighton|dorchester|roxbury|ma)$", "", s)
    return s.strip()


# Explicit cross-source matching aliases (spreadsheet name / TM name / POSH name -> canonical key)
CANONICAL_ALIASES = {
    "the cantab lounge": "cantab lounge",
    "cantab underground": "cantab lounge",
    "cantab lounge / underground": "cantab lounge",
    "the sinclair music hall": "the sinclair",
    "sinclair music hall": "the sinclair",
    "sinclair": "the sinclair",
    "lilypad": "the lilypad",
    "plough and stars": "the plough and stars",
    "plough & stars": "the plough and stars",
    "lamplighter brewing co": "lamplighter brewing",
    "lamplighter brewing co broadway": "lamplighter brewing",
    "lamplighter": "lamplighter brewing",
    "lou s": "lous",
    "lous": "lous",
    "the mad monkfish": "mad monkfish",
    "the phoenix landing": "phoenix landing",
    "the burren": "burren",
    "underbones redbones": "underbones",
    "redbones / underbones": "underbones",
    "remnant brewing satellite": "remnant satellite",
    "remnant brewing bow market": "remnant brewing",
    "castle island brewing south boston": "castle island brewing",
    "bills bar and lounge": "bills bar",
    "bill s bar and lounge": "bills bar",
    "bill s bar": "bills bar",
    "lorettas last call": "lorettas last call",
    "loretta s last call": "lorettas last call",
    "the lansdowne pub": "lansdowne pub",
    "the beehive": "beehive",
    "the bebop": "bebop",
    "club cafe": "club cafe",
    "nicks comedy stop": "nicks comedy stop",
    "nick s comedy stop": "nicks comedy stop",
    "luckys lounge": "luckys lounge",
    "lucky s lounge": "luckys lounge",
    "institute of contemporary art": "ica",
    "ica boston": "ica",
    "paradise rock club": "paradise rock club",
    "brighton music hall": "brighton music hall",
    "roadrunner": "roadrunner",
    "roadrunner boston": "roadrunner",
    "scullers jazz club": "scullers jazz club",
    "obriens pub": "obriens pub",
    "o brien s pub": "obriens pub",
    "viva karaoke allston stage karaoke": "viva karaoke allston",
    "viva karaoke allston main stage": "viva karaoke allston",
    "notch brewing brighton": "notch brewing brighton",
    "charles river speedway courtyard": "charles river speedway",
    "charles river speedway": "charles river speedway",
    "widowmaker taproom and kitchen brighton": "widowmaker brighton",
    "widowmaker brewing brighton": "widowmaker brighton",
    "broken records": "broken records beer hall",
    "broken records beer hall": "broken records beer hall",
    "blondies": "blondies",
    "blondie s": "blondies",
    "porter belleys pub": "porter bellys pub",
    "porter belly s pub": "porter bellys pub",
    "99 franklin st": "exit galleries",
    "exit galleries": "exit galleries",
    "allstonway park": "allstonway",
    "allstonway": "allstonway",
    "midway cafe": "midway cafe",
    "brendan behan pub": "brendan behan pub",
    "jeanie johnston pub and grill": "jeanie johnston pub",
    "the haven": "the haven jp",
    "dorchester brewing company": "dorchester brewing",
    "dorchester brewing co": "dorchester brewing",
    "mcgonagle s pub": "mcgonagles pub",
    "mcgonagles pub": "mcgonagles pub",
    "jazzurbane cafe": "jazzurbane cafe",
    "jazz urbane cafe": "jazzurbane cafe",
    "slade s bar and grill": "slades bar and grill",
    "slades bar and grill": "slades bar and grill",
    "grainne o malley s tavern": "grainne omalleys",
    "grainne omalleys tavern": "grainne omalleys",
    "hamilton restaurant and bar": "hamilton brookline",
    "mccarthy s": "mccarthys",
    "mccarthys": "mccarthys",
    "dante alighieri society": "dante alighieri society",
    "dante s salsa and bachata": "dante alighieri society",
    "dantes salsa and bachata": "dante alighieri society",
    "havana club": "havana club",
    "288 green st": "havana club",
    "manray": "manray",
    "man ray": "manray",
    "middlesex lounge": "middlesex lounge",
    "middlesex": "middlesex lounge",
    "arts at the armory": "arts at the armory",
    "arts at the armory performance hall": "arts at the armory",
    "crystal ballroom": "crystal ballroom",
    "crystal ballroom at somerville theatre": "crystal ballroom",
    "charles playhouse": "charles playhouse",
    "charles playhouse theater 2": "charles playhouse",
    "symphony hall": "symphony hall",
    "boston symphony hall": "symphony hall",
    "hava": "hava nightclub",
    "hava nightclub": "hava nightclub",
    "hava night club": "hava nightclub",
    "venu": "venu nightclub",
    "venu nightclub": "venu nightclub",
    "the liberty hotel": "liberty hotel",
    "house of blues boston": "house of blues",
    "house of blues": "house of blues",
    "mgm music hall at fenway": "mgm music hall at fenway",
    "citizens house of blues boston": "house of blues",
    "td garden": "td garden",
    "orpheum theatre": "orpheum theatre",
    "boch center wang theatre": "wang theatre",
    "boch center shubert theatre": "shubert theatre",
    "wilbur theatre": "the wilbur",
    "the wilbur": "the wilbur",
    "chevalier theatre": "chevalier theatre",
    "royale": "royale",
    "royale boston": "royale",
    "big night live": "big night live",
    "memoire": "memoire",
    "the grand": "the grand",
    "the grand boston": "the grand",
    "bijou": "bijou",
    "bijou nightclub": "bijou",
    "bijou nightclub and lounge": "bijou",
    "bijou nightclub lounge": "bijou",
    "scorpion bar": "scorpion boston",
    "scorpion bar boston": "scorpion boston",
    "scorpion boston": "scorpion boston",
    "empire": "empire",
    "grace by nia": "grace by nia",
    "howl at the moon": "howl at the moon",
    "green dragon tavern": "green dragon tavern",
    "city winery boston": "city winery",
    "city winery": "city winery",
    "laugh boston": "laugh boston",
    "improv asylum": "improv asylum",
    "comedy studio": "the comedy studio",
    "the comedy studio": "the comedy studio",
    "sonia": "middle east sonia zuzu",
    "middle east downstairs": "middle east sonia zuzu",
    "middle east upstairs": "middle east sonia zuzu",
    "middle east corner bakery": "middle east sonia zuzu",
    "middle east zuzu": "middle east sonia zuzu",
    "middle east": "middle east sonia zuzu",
    "middle east sonia zuzu": "middle east sonia zuzu",
    "jimmy s jazz and blues club": "jimmys jazz and blues club",
    "jimmys jazz and blues club": "jimmys jazz and blues club",
    "jimmys jazz blues club": "jimmys jazz and blues club",
    "wally s": "wallys",
    "wallys": "wallys",
    "bernie s beach bar": "bernies beach bar",
    "bogie s at depot square": "bogies at depot square",
    "the press room": "press room",
    "press room": "press room",
    "portsmouth gas light co": "portsmouth gas light co",
    "3s artspace": "3s artspace",
    "the music hall": "music hall",
    "the music hall lounge": "music hall lounge",
}


def canonical_key(name: str) -> str:
    n = norm(name)
    if n in CANONICAL_ALIASES:
        return CANONICAL_ALIASES[n]
    nl = norm_loose(name)
    if nl in CANONICAL_ALIASES:
        return CANONICAL_ALIASES[nl]
    return nl or n


def clean_priority(raw) -> str:
    s = str(raw or "").strip().upper()
    if s in {"A", "HIGH", "A — CORE", "A – CORE", "CORE"} or s.startswith("A "):
        return "A"
    if s in {"B", "MEDIUM", "MED", "B — SUPPLEMENTARY"} or s.startswith("B "):
        return "B"
    if s in {"C", "LOW", "C — INVESTIGATE"} or s.startswith("C "):
        return "C"
    return "Unranked"


def clean_str(val) -> str:
    if val is None:
        return ""
    return " ".join(str(val).strip().split())


def slugify(text: str) -> str:
    s = unicodedata.normalize("NFKD", str(text or ""))
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")
    return s or "venue"


def infer_area_from_city_or_hood(city: str, neighborhood: str) -> str:
    blob = f"{city} {neighborhood}".lower()
    if "cambridge" in blob:
        return "Cambridge"
    if "somerville" in blob:
        return "Somerville"
    if "brookline" in blob or "coolidge corner" in blob:
        return "Brookline"
    if "allston" in blob or "brighton" in blob or "boston landing" in blob or "cleveland circle" in blob:
        return "Allston / Brighton"
    if "jamaica plain" in blob:
        return "Jamaica Plain"
    if "dorchester" in blob:
        return "Dorchester"
    if "east boston" in blob:
        return "East Boston"
    if "roxbury" in blob or "nubian" in blob:
        return "Roxbury"
    if "medford" in blob:
        return "Medford / North"
    if any(k in blob for k in ("portsmouth", "hampton", "seabrook", "rye", "durham", "salisbury", "new castle", "seacoast")):
        if "hampton" in blob:
            return "Hampton / Beach NH"
        if "portsmouth" in blob:
            return "Portsmouth NH"
        return "Seacoast NH"
    if "boston" in blob or any(
        k in blob for k in ("fenway", "seaport", "back bay", "south end", "beacon hill", "north end", "downtown", "theater", "chinatown", "south boston", "charlestown", "fort point")
    ):
        return "Boston Proper"
    return city or "Greater Boston"


def parse_spreadsheets():
    """Read all 6 Greater Boston research spreadsheets into a list of raw venue dicts."""
    records = []

    # 1. Cambridge Source Map v0.6
    p = DOWNLOADS / "Happenin_Cambridge_Source_Map_v0.6.xlsx"
    if p.exists():
        wb = openpyxl.load_workbook(p, read_only=True, data_only=True)
        # Pull URLs from A-Priority Sat Audit if available
        sat_urls = {}
        if "A-Priority Sat Audit" in wb.sheetnames:
            ws_sat = wb["A-Priority Sat Audit"]
            for row in list(ws_sat.iter_rows(values_only=True))[1:]:
                if row and row[0]:
                    url = clean_str(row[7] if len(row) > 7 else "")
                    if url.startswith("http"):
                        sat_urls[canonical_key(row[0])] = url
        ws = wb["Source Map"]
        for row in list(ws.iter_rows(values_only=True))[1:]:
            if not row or not row[0]:
                continue
            name = clean_str(row[0])
            source_class = clean_str(row[2] if len(row) > 2 else "")
            # Skip pure ticketing/aggregator/calendar meta-rows (not physical venues)
            if any(k in source_class.lower() for k in ("ticketing platform", "aggregator", "discovery", "social", "calendar")):
                continue
            if name.lower() in {"ticketmaster / ticketweb", "posh", "eventbrite", "dice", "resident advisor", "google calendar / ics"}:
                continue
            hood = clean_str(row[1] if len(row) > 1 else "")
            prio = clean_priority(row[3] if len(row) > 3 else "")
            vibe = clean_str(row[4] if len(row) > 4 else "")
            pattern = clean_str(row[5] if len(row) > 5 else "")
            notes = clean_str(row[7] if len(row) > 7 else "")
            records.append({
                "venue": name,
                "area": "Cambridge",
                "neighborhood": hood or "Cambridge",
                "priority": prio,
                "vibe": vibe,
                "notes": " · ".join(x for x in (pattern, notes) if x),
                "url": sat_urls.get(canonical_key(name), ""),
                "source_sheet": p.name,
            })

    # 2. Somerville Venue Directory
    p = DOWNLOADS / "Happenin_Somerville_Venue_Directory.xlsx"
    if p.exists():
        wb = openpyxl.load_workbook(p, read_only=True, data_only=True)
        ws = wb["Somerville Venues"]
        for row in list(ws.iter_rows(values_only=True))[1:]:
            if not row or not row[0]:
                continue
            records.append({
                "venue": clean_str(row[0]),
                "area": "Somerville",
                "neighborhood": "Somerville",
                "priority": clean_priority(row[2] if len(row) > 2 else ""),
                "vibe": clean_str(row[1] if len(row) > 1 else ""),
                "notes": "",
                "url": "",
                "source_sheet": p.name,
            })

    # 3. Boston Proper Venue Directory
    p = DOWNLOADS / "Happenin_Boston_Venue_Directory.xlsx"
    if p.exists():
        wb = openpyxl.load_workbook(p, read_only=True, data_only=True)
        hood_map = {}
        if "Research Sources" in wb.sheetnames:
            for row in list(wb["Research Sources"].iter_rows(values_only=True))[1:]:
                if row and row[0]:
                    hood_map[canonical_key(row[0])] = clean_str(row[1] if len(row) > 1 else "")
        ws = wb["Boston Venues"]
        for row in list(ws.iter_rows(values_only=True))[1:]:
            if not row or not row[0]:
                continue
            name = clean_str(row[0])
            records.append({
                "venue": name,
                "area": "Boston Proper",
                "neighborhood": hood_map.get(canonical_key(name), "Boston"),
                "priority": clean_priority(row[2] if len(row) > 2 else ""),
                "vibe": clean_str(row[1] if len(row) > 1 else ""),
                "notes": "",
                "url": "",
                "source_sheet": p.name,
            })

    # 4. Allston / Brighton Venue Directory
    p = DOWNLOADS / "Happenin_Allston_Brighton_Venue_Directory.xlsx"
    if p.exists():
        wb = openpyxl.load_workbook(p, read_only=True, data_only=True)
        meta_map = {}
        if "Research Sources" in wb.sheetnames:
            for row in list(wb["Research Sources"].iter_rows(values_only=True))[1:]:
                if row and row[0]:
                    meta_map[canonical_key(row[0])] = (
                        clean_str(row[1] if len(row) > 1 else ""),
                        clean_str(row[2] if len(row) > 2 else ""),
                    )
        ws = wb["Allston Brighton Venues"]
        for row in list(ws.iter_rows(values_only=True))[1:]:
            if not row or not row[0]:
                continue
            name = clean_str(row[0])
            hood, src_url = meta_map.get(canonical_key(name), ("Allston / Brighton", ""))
            records.append({
                "venue": name,
                "area": "Allston / Brighton",
                "neighborhood": hood or "Allston / Brighton",
                "priority": clean_priority(row[2] if len(row) > 2 else ""),
                "vibe": clean_str(row[1] if len(row) > 1 else ""),
                "notes": "",
                "url": src_url if src_url.startswith("http") else "",
                "source_sheet": p.name,
            })

    # 5. Boston Neighborhoods (JP, Dorchester, East Boston, Roxbury)
    p = DOWNLOADS / "Happenin_Boston_Neighborhoods_Venue_Directory.xlsx"
    if p.exists():
        wb = openpyxl.load_workbook(p, read_only=True, data_only=True)
        src_map = {}
        if "Research Sources" in wb.sheetnames:
            for row in list(wb["Research Sources"].iter_rows(values_only=True))[1:]:
                if row and len(row) >= 2 and row[1]:
                    src_map[canonical_key(row[1])] = (
                        clean_str(row[0]),
                        clean_str(row[2] if len(row) > 2 else ""),
                    )
        ws = wb["Neighborhood Venues"]
        for row in list(ws.iter_rows(values_only=True))[1:]:
            if not row or not row[0]:
                continue
            raw_name = clean_str(row[0])
            area = "Boston Proper"
            name = raw_name
            if "—" in raw_name:
                parts = [x.strip() for x in raw_name.split("—", 1)]
                area, name = parts[0], parts[1]
            elif " - " in raw_name:
                parts = [x.strip() for x in raw_name.split(" - ", 1)]
                area, name = parts[0], parts[1]
            hood_src, url_src = src_map.get(canonical_key(name), (area, ""))
            records.append({
                "venue": name,
                "area": area,
                "neighborhood": hood_src or area,
                "priority": clean_priority(row[2] if len(row) > 2 else ""),
                "vibe": clean_str(row[1] if len(row) > 1 else ""),
                "notes": "",
                "url": url_src if url_src.startswith("http") else "",
                "source_sheet": p.name,
            })

    # 6. Brookline Nightlife Venue Directory
    p = DOWNLOADS / "Brookline_Nightlife_Venue_Directory.xlsx"
    if p.exists():
        wb = openpyxl.load_workbook(p, read_only=True, data_only=True)
        ws = wb["Venues"]
        for row in list(ws.iter_rows(values_only=True))[1:]:
            if not row or not row[0]:
                continue
            name = clean_str(row[0])
            hood = clean_str(row[1] if len(row) > 1 else "")
            addr = clean_str(row[2] if len(row) > 2 else "")
            vtype = clean_str(row[3] if len(row) > 3 else "")
            prog = clean_str(row[5] if len(row) > 5 else "")
            prio = clean_priority(row[6] if len(row) > 6 else "")
            status_note = clean_str(row[7] if len(row) > 7 else "")
            lead_url = clean_str(row[8] if len(row) > 8 else "")
            is_closed = "golden temple" in name.lower()
            records.append({
                "venue": name,
                "area": "Brookline",
                "neighborhood": hood or "Brookline",
                "address": f"{addr}, Brookline, MA" if addr else "",
                "priority": prio,
                "vibe": " · ".join(x for x in (vtype, prog) if x),
                "notes": "Permanently closed after 66 years." if is_closed else status_note,
                "url": lead_url if lead_url.startswith("http") else "",
                "permanently_closed": is_closed,
                "region": "boston",
                "source_sheet": p.name,
            })

    # 7. NH Seacoast Nightlife Venue Directory (Portsmouth, Hampton, North Hampton, Seabrook, Rye)
    p = DOWNLOADS / "NH_Seacoast_Nightlife_Venue_Directory.xlsx"
    if p.exists():
        wb = openpyxl.load_workbook(p, read_only=True, data_only=True)
        ws = wb["Venues"]
        for row in list(ws.iter_rows(values_only=True))[1:]:
            if not row or not row[0]:
                continue
            name = clean_str(row[0])
            hood = clean_str(row[1] if len(row) > 1 else "")
            addr = clean_str(row[2] if len(row) > 2 else "")
            vtype = clean_str(row[3] if len(row) > 3 else "")
            prog = clean_str(row[5] if len(row) > 5 else "")
            prio = clean_priority(row[6] if len(row) > 6 else "")
            status_note = clean_str(row[7] if len(row) > 7 else "")
            lead_url = clean_str(row[8] if len(row) > 8 else "")
            muni = clean_str(row[10] if len(row) > 10 else "")
            seasonality = clean_str(row[11] if len(row) > 11 else "")
            area = "Portsmouth NH" if muni == "Portsmouth" else ("Hampton / Beach NH" if "Hampton" in muni else "Seacoast NH")
            notes_parts = [x for x in (seasonality, status_note) if x]
            records.append({
                "venue": name,
                "area": area,
                "neighborhood": f"{muni} · {hood}" if (muni and hood and muni != hood) else (hood or muni or "Seacoast NH"),
                "address": f"{addr}, {muni or 'Portsmouth'}, NH" if addr else "",
                "priority": prio,
                "vibe": " · ".join(x for x in (vtype, prog) if x),
                "notes": " · ".join(notes_parts),
                "url": lead_url if lead_url.startswith("http") else "",
                "region": "seacoast",
                "source_sheet": p.name,
            })

    return records


def main():
    print("HAPPENIN' — BUILDING MASTER VENUE & EVENT DATABASE")

    sheet_venues = parse_spreadsheets()
    print(f"Loaded {len(sheet_venues)} spreadsheet venue rows across 6 area files.")

    registry = json.loads(VENUES_JSON_PATH.read_text(encoding="utf-8"))
    configured_list = registry.get("venues", [])
    print(f"Loaded {len(configured_list)} collector configs from venues.json.")

    events = json.loads(EVENTS_JSON_PATH.read_text(encoding="utf-8"))
    print(f"Loaded {len(events)} live upcoming events from HappeninWeb/public/events.json.")

    # Index configured collectors by canonical key (a venue may have 2 collectors, e.g. live + weekly)
    configs_by_key = defaultdict(list)
    for cfg in configured_list:
        configs_by_key[canonical_key(cfg["venue"])].append(cfg)

    # Index live events by canonical venue key
    events_by_key = defaultdict(list)
    for ev in events:
        ck = canonical_key(ev.get("venue") or "")
        if ck:
            events_by_key[ck].append(ev)

    # Merge spreadsheet venues (deduplicating overlaps across sheets, preferring higher priority & richer notes)
    prio_rank = {"A": 0, "B": 1, "C": 2, "Unranked": 3}
    merged_venues = {}

    for rec in sheet_venues:
        ck = canonical_key(rec["venue"])
        if ck not in merged_venues:
            merged_venues[ck] = dict(rec)
            merged_venues[ck]["source_sheets"] = [rec["source_sheet"]]
        else:
            existing = merged_venues[ck]
            if rec["source_sheet"] not in existing["source_sheets"]:
                existing["source_sheets"].append(rec["source_sheet"])
            if prio_rank[rec["priority"]] < prio_rank[existing["priority"]]:
                existing["priority"] = rec["priority"]
            if len(rec.get("vibe", "")) > len(existing.get("vibe", "")):
                existing["vibe"] = rec["vibe"]
            if rec.get("url") and not existing.get("url"):
                existing["url"] = rec["url"]
            if rec.get("address") and not existing.get("address"):
                existing["address"] = rec["address"]
            if rec.get("notes") and not existing.get("notes"):
                existing["notes"] = rec["notes"]
            if rec.get("permanently_closed"):
                existing["permanently_closed"] = True

    # Ensure every configured venue in venues.json is present
    for ck, cfgs in configs_by_key.items():
        primary = cfgs[0]
        if ck not in merged_venues:
            merged_venues[ck] = {
                "venue": primary["venue"],
                "area": infer_area_from_city_or_hood(primary.get("city", ""), primary.get("address", "")),
                "neighborhood": primary.get("city", ""),
                "priority": "A",
                "vibe": primary.get("default_category") or "",
                "notes": primary.get("notes") or "",
                "url": primary.get("url") or "",
                "source_sheets": ["venues.json"],
            }

    # Ensure every live venue appearing in events.json (Ticketmaster / POSH / legacy) is present
    for ck, ev_list in events_by_key.items():
        if ck not in merged_venues:
            sample = ev_list[0]
            city = sample.get("city") or ""
            addr = sample.get("address") or ""
            area = infer_area_from_city_or_hood(city, addr)
            sources = sorted({e.get("source_name") or "Unknown" for e in ev_list})
            merged_venues[ck] = {
                "venue": sample.get("venue") or ck.title(),
                "area": area,
                "neighborhood": city or area,
                "priority": "Unranked",
                "vibe": ", ".join(sorted({e.get("ai_category") or e.get("default_category") or "" for e in ev_list if (e.get("ai_category") or e.get("default_category"))})),
                "notes": f"Discovered automatically via {', '.join(sources)}",
                "url": sample.get("source_url") or "",
                "source_sheets": ["live_feed"],
            }

    # Known seasonal / blocker hints for clean human-review guidance
    SEASONAL_RE = re.compile(r"\b(seasonal|outdoor|park|pond|stadium|watershed|tall ship|suffolk downs|herter|arboretum|owl's nest)\b", re.I)

    # Build final unified venue records
    venue_records = []
    for ck, rec in merged_venues.items():
        cfgs = configs_by_key.get(ck, [])
        ev_list = sorted(events_by_key.get(ck, []), key=lambda e: e.get("start") or "")

        enabled_cfgs = [c for c in cfgs if c.get("enabled")]
        legacy_cfgs = [c for c in cfgs if c.get("collector_type") == "legacy_custom"]
        disabled_cfgs = [c for c in cfgs if not c.get("enabled") and c.get("collector_type") != "legacy_custom"]

        # Determine provenance of live events
        live_sources = sorted({e.get("source_name") or "" for e in ev_list if e.get("source_name")})
        has_first_party_events = any(
            e.get("source_type") == "venue_website" or e.get("source_name") not in {"Ticketmaster", "POSH"}
            for e in ev_list
        )
        has_tm = any(e.get("source_name") == "Ticketmaster" for e in ev_list)
        has_posh = any(e.get("source_name") == "POSH" for e in ev_list)

        # Collector method list
        collector_methods = []
        for c in enabled_cfgs:
            ct = c.get("collector_type")
            if ct and ct not in collector_methods:
                collector_methods.append(ct)
        for c in legacy_cfgs:
            if "legacy_custom" not in collector_methods:
                collector_methods.append("legacy_custom")
        if has_tm and "ticketmaster" not in collector_methods:
            collector_methods.append("ticketmaster")
        if has_posh and "posh" not in collector_methods:
            collector_methods.append("posh")
        if not collector_methods:
            collector_methods = ["none"]

        primary_method = collector_methods[0]

        # Status classification (Plan 01 5-state system)
        is_closed = bool(rec.get("permanently_closed"))
        is_seasonal = bool(SEASONAL_RE.search(f"{rec.get('venue','')} {rec.get('vibe','')}"))
        if is_closed:
            status = "Paused / Closed"
        elif has_first_party_events:
            status = "Live (First-Party)"
        elif enabled_cfgs and not ev_list:
            status = "Ready (0 Events)"
        elif ev_list and not has_first_party_events:
            status = "Aggregator Only"
        elif disabled_cfgs or is_seasonal:
            status = "Paused / Closed"
        else:
            status = "Not Pulling"

        # Prefer verified coordinates and address from venues.json, then live events, then spreadsheet
        cfg_primary = (enabled_cfgs or legacy_cfgs or disabled_cfgs or [None])[0]
        sample_ev = ev_list[0] if ev_list else None

        lat = (cfg_primary or {}).get("latitude")
        lng = (cfg_primary or {}).get("longitude")
        if lat is None and sample_ev:
            lat = sample_ev.get("latitude")
            lng = sample_ev.get("longitude")

        address = ""
        if cfg_primary and cfg_primary.get("address"):
            parts = [cfg_primary.get("address"), cfg_primary.get("city"), cfg_primary.get("state"), cfg_primary.get("postal_code")]
            address = ", ".join(str(x) for x in parts if x)
        elif sample_ev and sample_ev.get("address"):
            parts = [sample_ev.get("address"), sample_ev.get("city"), sample_ev.get("state")]
            address = ", ".join(str(x) for x in parts if x)
        elif rec.get("address"):
            address = rec["address"]

        url = (cfg_primary or {}).get("url") or rec.get("url") or (sample_ev.get("source_url") if sample_ev else "") or ""

        # Gather recurring rules & config notes
        recurring_rules = []
        cfg_notes = []
        for c in cfgs:
            if c.get("notes"):
                cfg_notes.append(c["notes"])
            for r in c.get("rules") or []:
                recurring_rules.append({
                    "title": r.get("title"),
                    "weekdays": r.get("weekdays", []),
                    "start_time": r.get("start_time"),
                    "end_time": r.get("end_time"),
                    "description": r.get("description", ""),
                })

        notes_combined = " · ".join(x for x in [rec.get("notes", ""), *cfg_notes] if x)
        if status == "Paused / Closed" and is_seasonal and not is_closed and not notes_combined:
            notes_combined = "Seasonal / outdoor venue."

        categories_present = sorted({
            e.get("ai_category") or e.get("default_category")
            for e in ev_list
            if (e.get("ai_category") or e.get("default_category"))
        })
        if not categories_present and cfg_primary and cfg_primary.get("default_category"):
            categories_present = [cfg_primary["default_category"]]

        venue_region = (
            rec.get("region")
            or (cfg_primary or {}).get("region")
            or (sample_ev.get("region") if sample_ev else None)
            or ("seacoast" if (lat is not None and lat >= 42.82) or "NH" in rec["area"] else "boston")
        )
        venue_id = (cfg_primary or {}).get("id") or slugify(f"{rec['area']}-{rec['venue']}")
        # Ensure unique IDs
        venue_records.append({
            "id": venue_id,
            "canonicalKey": ck,
            "venue": rec["venue"],
            "region": venue_region,
            "area": rec["area"],
            "neighborhood": rec.get("neighborhood") or rec["area"],
            "address": address,
            "latitude": lat,
            "longitude": lng,
            "priority": rec["priority"],
            "status": status,
            "collectorMethods": collector_methods,
            "primaryMethod": primary_method,
            "eventCount": len(ev_list),
            "eventIds": [e.get("id") for e in ev_list if e.get("id")],
            "categories": categories_present,
            "vibe": rec.get("vibe") or "",
            "url": url,
            "notes": notes_combined,
            "sourceSheets": rec.get("source_sheets", []),
            "liveSources": live_sources,
            "recurringRules": recurring_rules,
            "configIds": [c.get("id") for c in cfgs],
        })

    # Deduplicate any accidental venue_id collision
    seen_ids = Counter()
    for v in venue_records:
        vid = v["id"]
        seen_ids[vid] += 1
        if seen_ids[vid] > 1:
            v["id"] = f"{vid}-{seen_ids[vid]}"

    # Sort venues cleanly: Priority A->B->C->Unranked, then live events desc, then name
    venue_records.sort(key=lambda v: (prio_rank.get(v["priority"], 9), -v["eventCount"], v["venue"].lower()))

    # Build slim event records linked to venueId & area for fast UI filtering
    venue_by_ck = {v["canonicalKey"]: v for v in venue_records}
    db_events = []
    for ev in events:
        ck = canonical_key(ev.get("venue") or "")
        vrec = venue_by_ck.get(ck)
        src_name = ev.get("source_name") or "Unknown"
        provenance = (
            "Ticketmaster"
            if src_name == "Ticketmaster"
            else ("POSH" if src_name == "POSH" else "First-Party")
        )
        db_events.append({
            "id": ev.get("id") or slugify(f"{ev.get('venue')}-{ev.get('title')}-{ev.get('start')}"),
            "venueId": vrec["id"] if vrec else None,
            "venue": ev.get("venue") or "Unknown Venue",
            "region": ev.get("region") or (vrec["region"] if vrec else "boston"),
            "area": vrec["area"] if vrec else infer_area_from_city_or_hood(ev.get("city", ""), ev.get("address", "")),
            "neighborhood": vrec["neighborhood"] if vrec else (ev.get("city") or ""),
            "title": ev.get("title") or "Untitled Event",
            "start": ev.get("start"),
            "end": ev.get("end"),
            "category": ev.get("ai_category") or ev.get("default_category") or "Social",
            "admissionType": ev.get("admission_type") or "",
            "price": ev.get("ai_price") or ev.get("price") or "",
            "summary": ev.get("ai_summary") or "",
            "description": ev.get("description") or "",
            "tags": ev.get("ai_tags") or [],
            "sourceName": src_name,
            "provenance": provenance,
            "sourceUrl": ev.get("source_url") or "",
            "latitude": ev.get("latitude"),
            "longitude": ev.get("longitude"),
            "address": ev.get("address") or (vrec["address"] if vrec else ""),
            "contentRating": ev.get("content_rating") or "PG",
            "safetyReason": ev.get("safety_reason") or "",
            "hotelBlocked": bool(ev.get("hotel_blocked")),
        })

    # Summary stats
    status_counts = Counter(v["status"] for v in venue_records)
    area_counts = Counter(v["area"] for v in venue_records)
    prio_counts = Counter(v["priority"] for v in venue_records)
    region_counts = Counter(v["region"] for v in venue_records)

    payload = {
        "generatedAt": datetime.now(EASTERN).isoformat(timespec="seconds"),
        "stats": {
            "totalVenues": len(venue_records),
            "totalEvents": len(db_events),
            "statusCounts": dict(status_counts),
            "areaCounts": dict(area_counts),
            "priorityCounts": dict(prio_counts),
            "regionCounts": dict(region_counts),
            "attentionCount": sum(
                1
                for v in venue_records
                if v["status"] == "Ready (0 Events)"
                or (v["priority"] == "A" and v["status"] in {"Not Pulling", "Aggregator Only"})
            ),
        },
        "venues": venue_records,
        "events": db_events,
    }

    DIRECTORY_OUT_PATH.write_text(
        json.dumps(
            {"generatedAt": payload["generatedAt"], "stats": payload["stats"], "venues": venue_records},
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    WEB_DB_OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    WEB_DB_OUT_PATH.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print("=" * 60)
    print(f"Master venues built: {len(venue_records)}")
    print(f"Live events linked:  {len(db_events)}")
    print("By status:")
    for st, cnt in status_counts.most_common():
        print(f"  {st:22s}: {cnt}")
    print("By area:")
    for ar, cnt in area_counts.most_common():
        print(f"  {ar:22s}: {cnt}")
    print(f"Saved: {DIRECTORY_OUT_PATH}")
    print(f"Saved: {WEB_DB_OUT_PATH}")
    print("=" * 60)


if __name__ == "__main__":
    main()
