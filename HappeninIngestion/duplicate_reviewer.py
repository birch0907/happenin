"""Happenin' interactive duplicate decisions. Does not modify events.json.
Place beside events.json, event_quality.py, and happenin_deduplication.py.
Run: python duplicate_reviewer.py
"""
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import event_quality
import happenin_deduplication as dedup

ROOT = Path(__file__).resolve().parent
EVENTS = ROOT / 'events.json'
DECISIONS = ROOT / 'duplicate_decisions.json'
EASTERN = ZoneInfo('America/New_York')


def event_identity(event):
    """Prefer source-specific identifiers; include start so recurring shows stay distinct."""
    source = str(event.get('source_name') or '').strip().casefold()
    source_id = str(event.get('source_id') or event.get('id') or '').strip()
    url = str(event.get('source_url') or event.get('url') or '').strip()
    title = dedup.normalize(event.get('title'))
    start = dedup.start_key(event.get('start'))
    start_text = start.isoformat() if start else str(event.get('start') or '')
    venue = event_quality.venue_of(event)
    # ID or URL should be stable across title corrections. Fallback is content-based.
    anchor = ('id', source_id) if source_id else (('url', url) if url else ('title_venue', title, venue))
    return [source, *anchor, start_text]


def pair_key(a, b):
    identities = sorted([event_identity(a), event_identity(b)], key=lambda v: json.dumps(v, ensure_ascii=False))
    raw = json.dumps(identities, ensure_ascii=False, separators=(',', ':'))
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()[:24]


def duplicate_findings(events):
    """Read findings from the existing quality checker's report; no new detection logic."""
    report, _ = event_quality.build_report(events)
    output = []
    for section in re.split(r'(?m)^\[\d+\] ', report)[1:]:
        header = section.splitlines()[0].strip()
        if header not in ('LIKELY DUPLICATE', 'POSSIBLE DUPLICATE'):
            continue
        record_nums = [int(n) - 1 for n in re.findall(r'(?m)^  Record #(\d+):', section)]
        if len(record_nums) != 2 or any(i < 0 or i >= len(events) for i in record_nums):
            raise ValueError('Could not read a duplicate pair from event_quality.py output. No decisions saved.')
        reason_match = re.search(r'(?m)^  Reason: (.+)$', section)
        i, j = record_nums
        output.append((header, reason_match.group(1) if reason_match else '', i, j))
    return output


def load_decisions():
    if not DECISIONS.exists():
        return {'version': 1, 'decisions': {}}
    data = json.loads(DECISIONS.read_text(encoding='utf-8'))
    if not isinstance(data, dict) or not isinstance(data.get('decisions'), dict):
        raise ValueError('duplicate_decisions.json has an unexpected structure; refusing to overwrite it.')
    return data


def save_decisions(data):
    # Atomic replace to avoid a half-written decisions file.
    temp = DECISIONS.with_name(DECISIONS.name + '.tmp')
    temp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    temp.replace(DECISIONS)


def show_event(label, event):
    print(f'  {label}: {event.get("title") or "(untitled)"}')
    for field, key in [('Venue', 'venue'), ('Start', 'start'), ('Source', 'source_name')]:
        print(f'    {field}: {event.get(key) or "(missing)"}')
    print(f'    Link: {event.get("source_url") or event.get("url") or "(missing)"}')


def main():
    try:
        events = json.loads(EVENTS.read_text(encoding='utf-8'))
        if not isinstance(events, list) or not all(isinstance(e, dict) for e in events):
            raise ValueError('events.json must be a list of event objects.')
        decisions = load_decisions()
        findings = duplicate_findings(events)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f'Cannot start duplicate reviewer: {exc}')
        return

    pending = []
    already = 0
    for category, reason, i, j in findings:
        key = pair_key(events[i], events[j])
        if key in decisions['decisions']:
            already += 1
        else:
            pending.append((category, reason, i, j, key))

    print("\nHAPPENIN' — DUPLICATE REVIEWER")
    print(f'Events: {len(events)} | Duplicate pair findings: {len(findings)}')
    print(f'Previously decided: {already} | Pending: {len(pending)}')
    print('Decisions only: events.json and ingest.py will NOT change.\n')
    for n, (category, reason, i, j, key) in enumerate(pending, 1):
        a, b = events[i], events[j]
        print(f'--- Pair {n} of {len(pending)} — {category} ---')
        print(f'  Why flagged: {reason}')
        show_event('A', a)
        show_event('B', b)
        print('  [m] Same event / approve merge   [k] Keep separate   [s] Skip   [q] Quit')
        while True:
            choice = input('  Choice: ').strip().lower()
            if choice in ('m', 'k', 's', 'q'):
                break
            print('  Enter m, k, s, or q.')
        if choice == 'q':
            print('Stopped. Previously saved decisions remain saved.')
            break
        if choice == 's':
            print('Skipped; no decision saved.\n')
            continue
        if choice == 'm':
            # Preview the exact existing merge behavior; do not write merged events.
            merged = dedup.merge_group([a, b])
            print(f'  Merge preview — primary: {merged.get("source_name")} | {merged.get("title")}')
            print(f'  Ticket links retained: {len(merged.get("ticket_links", []))}')
            print('  This records an approval only. No merge is applied yet.')
        confirmation = input(f'  Save {"MERGE" if choice == "m" else "KEEP SEPARATE"} decision? [y/N]: ').strip().lower()
        if confirmation != 'y':
            print('Not saved.\n')
            continue
        decisions['decisions'][key] = {
            'decision': 'merge' if choice == 'm' else 'keep_separate',
            'event_a': event_identity(a),
            'event_b': event_identity(b),
            'titles': [str(a.get('title') or ''), str(b.get('title') or '')],
            'reviewed_at': datetime.now(EASTERN).isoformat(timespec='seconds'),
        }
        try:
            save_decisions(decisions)
        except OSError as exc:
            print(f'Could not save decision: {exc}')
            break
        print(f'  Saved to {DECISIONS.name}.\n')
    print('Finished. Run again to continue reviewing undecided pairs.')


if __name__ == '__main__':
    main()
