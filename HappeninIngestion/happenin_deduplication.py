"""Happenin' deduplication safe-coordinate preview. Reads events.json; writes events_deduplicated.json."""
import json
import re
import unicodedata
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

EASTERN = ZoneInfo('America/New_York')
FOLDER = Path(__file__).resolve().parent
INPUT_FILE = FOLDER / 'events.json'
OUTPUT_FILE = FOLDER / 'events_deduplicated.json'

VENUE_ALIASES = {
    'the sinclair music hall': 'the sinclair',
    'sinclair music hall': 'the sinclair',
    'bijou nightclub lounge': 'bijou',
    'bijou nightclub and lounge': 'bijou',
    'the grand boston': 'the grand',
    'scorpion bar seaport boston': 'scorpion boston',
    'scorpion bar boston': 'scorpion boston',
}
VENUE_SOURCES = {'Lamplighter', 'Lilypad', 'Sinclair', "Lou's", 'ManRay', 'The Plough and Stars'}


def normalize(value):
    text = unicodedata.normalize('NFKD', str(value or ''))
    text = ''.join(char for char in text if not unicodedata.combining(char))
    text = text.casefold().replace('&', ' and ')
    return ' '.join(re.findall(r'[a-z0-9]+', text))


def start_key(value):
    try:
        start = datetime.fromisoformat(value)
        if start.tzinfo is None:
            return None
        return start.astimezone(EASTERN).replace(second=0, microsecond=0)
    except (ValueError, TypeError):
        return None


def duplicate_key(event):
    title = normalize(event.get('title'))
    venue = normalize(event.get('venue'))
    venue = VENUE_ALIASES.get(venue, venue)
    start = start_key(event.get('start'))
    return (start, venue, title) if start and venue and title else None


def source_priority(event):
    source = event.get('source_name')
    kind = event.get('source_type')
    if kind == 'venue_website' or source in VENUE_SOURCES:
        return 0
    if source == 'Ticketmaster':
        return 1
    if kind == 'ticketing_platform':
        return 2
    if source == 'POSH':
        return 3
    return 4


def is_missing(value):
    return value is None or value == '' or value == [] or value == {}


def link_for(event):
    return event.get('source_url') or event.get('url')


def merge_group(group):
    # Stable choice: source priority, then count of populated fields.
    ranked = sorted(group, key=lambda e: (source_priority(e), -sum(not is_missing(v) for v in e.values())))
    merged = dict(ranked[0])
    sources = []
    links = []
    for event in ranked:
        source = event.get('source_name')
        if source and source not in sources:
            sources.append(source)
        for link in ([link_for(event)] + event.get('ticket_links', [])):
            if isinstance(link, str) and link.strip() and link not in links:
                links.append(link)
        for field, value in event.items():
            if field in {'source_name', 'source_type', 'source_id', 'source_url', 'url', 'id', 'ticket_links', 'sources'}:
                continue
            # Coordinates must come from the primary listing, not a secondary source.
            # A wrong map pin is worse than a missing map pin.
            if field in {'latitude', 'longitude', 'location_precision'}:
                continue
            if is_missing(merged.get(field)) and not is_missing(value):
                merged[field] = value
    # Treat (0, 0) as missing coordinates, never a real event location.
    if merged.get('latitude') == 0 and merged.get('longitude') == 0:
        merged['latitude'] = None
        merged['longitude'] = None
    merged['sources'] = sources
    merged['ticket_links'] = links
    return merged


def deduplicate(events):
    groups = defaultdict(list)
    for index, event in enumerate(events):
        key = duplicate_key(event)
        if key is not None:
            groups[key].append(index)
    duplicate_groups = [indexes for indexes in groups.values() if len(indexes) > 1]
    merged_by_first = {}
    suppressed = set()
    for indexes in duplicate_groups:
        merged_by_first[indexes[0]] = merge_group([events[i] for i in indexes])
        suppressed.update(indexes[1:])
    output = []
    for index, event in enumerate(events):
        if index in suppressed:
            continue
        output.append(merged_by_first.get(index, event))
    return output, duplicate_groups


def main():
    if not INPUT_FILE.exists():
        print(f'Cannot find {INPUT_FILE}. Put this script beside events.json.')
        return
    with INPUT_FILE.open(encoding='utf-8') as handle:
        events = json.load(handle)
    if not isinstance(events, list):
        print('events.json must contain a JSON list.')
        return
    output, groups = deduplicate(events)
    with OUTPUT_FILE.open('w', encoding='utf-8') as handle:
        json.dump(output, handle, indent=4, ensure_ascii=False)
    print("HAPPENIN' — DEDUPLICATION PREVIEW")
    print(f'Original events: {len(events)}')
    print(f'Duplicate groups: {len(groups)}')
    print(f'Records consolidated: {len(events) - len(output)}')
    print(f'Output events: {len(output)}')
    print()
    for number, indexes in enumerate(groups, 1):
        merged = merge_group([events[i] for i in indexes])
        print(f"GROUP {number}: {merged.get('title')} | {merged.get('start')}")
        print(f"  Primary: {merged.get('source_name')} | {merged.get('venue')}")
        print(f"  Sources: {', '.join(merged['sources'])}")
        print(f"  Links preserved: {len(merged['ticket_links'])}")
    print()
    print(f'Created {OUTPUT_FILE.name}. Original events.json was not changed.')


if __name__ == '__main__':
    main()
