import json
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from lamplighter import collect_lamplighter_events
from lilypad import collect_lilypad_events
from sinclair import collect_sinclair_events
from ticketmaster import collect_ticketmaster_events
from lous import collect_lous_events
from manray import collect_manray_events
from plough import collect_plough_events
from posh import collect_posh_events
from happenin_deduplication import deduplicate, merge_group

# Collect -> combine -> 14-day overlap filter -> archive -> deduplicate -> sort -> save.
EASTERN = ZoneInfo('America/New_York')
DAYS_AHEAD = 14
FOLDER = Path(__file__).resolve().parent


def event_is_in_time_window(event, window_start, window_end):
    start_text = event.get('start')
    if not start_text:
        return False
    try:
        event_start = datetime.fromisoformat(start_text)
    except (ValueError, TypeError):
        print('Skipping event with invalid start:', event.get('title'))
        return False
    if event_start.tzinfo is None:
        print('Skipping event with no timezone:', event.get('title'))
        return False
    event_start = event_start.astimezone(EASTERN)
    end_text = event.get('end')
    event_end = None
    if end_text:
        try:
            event_end = datetime.fromisoformat(end_text)
            if event_end.tzinfo is None:
                event_end = None
            else:
                event_end = event_end.astimezone(EASTERN)
        except (TypeError, ValueError):
            pass
    if event_end is None:
        event_end = event_start + timedelta(hours=4)
    return event_start < window_end and event_end > window_start


def write_json(path, data):
    with path.open('w', encoding='utf-8') as file:
        json.dump(data, file, indent=4, ensure_ascii=False)


def main():
    print("Starting Happenin' ingestion...\n")
    window_start = datetime.now(EASTERN)
    window_end = window_start + timedelta(days=DAYS_AHEAD)
    print('Happenin\' window:')
    print(' ', window_start.isoformat(timespec='seconds'))
    print('  to')
    print(' ', window_end.isoformat(timespec='seconds'), '\n')

    collectors = [
        ('Lamplighter', collect_lamplighter_events),
        ('Lilypad', collect_lilypad_events),
        ('Sinclair', collect_sinclair_events),
        ('Ticketmaster', collect_ticketmaster_events),
        ("Lou's", collect_lous_events),
        ('ManRay', collect_manray_events),
        ('Plough and Stars', collect_plough_events),
        ('POSH', collect_posh_events),
    ]
    all_events = []
    for name, collector in collectors:
        print(f'Collecting {name} events...')
        collected = collector()
        print(f'{name} collected: {len(collected)}\n')
        all_events.extend(collected)

    events = [e for e in all_events if event_is_in_time_window(e, window_start, window_end)]
    print('Total collected before filtering:', len(all_events))
    print('Events inside 14-day window:', len(events))
    print('Events removed by time filter:', len(all_events) - len(events), '\n')

    source_counts = {}
    for event in events:
        source = event.get('source_name', 'unknown')
        source_counts[source] = source_counts.get(source, 0) + 1
    print('Events by source (before deduplication):')
    for source, count in sorted(source_counts.items()):
        print(f'  {source}: {count}')
    print()

    # Preserve the complete filtered records before any merging.
    stamp = datetime.now(EASTERN).strftime('%Y-%m-%d_%H%M%S_%f')
    archive_dir = FOLDER / 'archive'
    log_dir = FOLDER / 'logs'
    archive_dir.mkdir(exist_ok=True)
    log_dir.mkdir(exist_ok=True)
    archive_path = archive_dir / f'events_raw_{stamp}.json'
    log_path = log_dir / f'deduplication_{stamp}.json'
    write_json(archive_path, events)

    unique_events, groups = deduplicate(events)
    merge_records = []
    for number, indexes in enumerate(groups, 1):
        originals = [events[index] for index in indexes]
        merged = merge_group(originals)
        merge_records.append({
            'group': number,
            'title': merged.get('title'),
            'start': merged.get('start'),
            'preferred_source': merged.get('source_name'),
            'sources': merged.get('sources', []),
            'ticket_links': merged.get('ticket_links', []),
            'original_records': originals,
            'merged_record': merged,
        })
    write_json(log_path, {
        'run_at': datetime.now(EASTERN).isoformat(timespec='seconds'),
        'original_archive': str(archive_path),
        'events_before_deduplication': len(events),
        'duplicate_groups': len(groups),
        'records_consolidated': len(events) - len(unique_events),
        'events_after_deduplication': len(unique_events),
        'merges': merge_records,
    })

    unique_events.sort(key=lambda e: e['start'])
    write_json(FOLDER / 'events.json', unique_events)
    print('\n------------------------------')
    print("HAPPENIN' — INGESTION COMPLETE")
    print('Events collected:', len(all_events))
    print('Events after time filter:', len(events))
    print('Duplicate groups:', len(groups))
    print('Records consolidated:', len(events) - len(unique_events))
    print('Final unique events:', len(unique_events))
    print('Created events.json')
    print('Original events archived:', archive_path)
    print('Deduplication log saved:', log_path)
    print('------------------------------')


if __name__ == '__main__':
    main()
