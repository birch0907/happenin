"""Happenin' non-destructive event quality review. Run: python event_quality.py"""
import json
import re
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
INPUT = ROOT / 'events.json'
REPORTS = ROOT / 'reports'
EASTERN = ZoneInfo('America/New_York')

VENUE_ALIASES = {
    'the sinclair music hall': 'the sinclair', 'sinclair music hall': 'the sinclair',
    'bijou nightclub lounge': 'bijou', 'bijou nightclub and lounge': 'bijou',
    'scorpion bar boston': 'scorpion', 'scorpion boston': 'scorpion',
    'the grand boston': 'the grand',
}
ADDON = re.compile(r'\b(?:vip\s*(?:m\s*&\s*g|meet\s*(?:and|&)\s*greet)|meet\s*(?:and|&)\s*greet|add[ -]?on|upgrade|parking\s*pass|early\s*entry\s*upgrade)\b', re.I)
GENERIC_PROMO = re.compile(r'\b(?:early\s*access\s*(?:and|&)\s*alerts?|guestlists?|giveaways?|discounted\s*tickets|weekly\s*lineup|festival\s*passes|must\s*read\s*below)\b', re.I)
RSVP_PROMO = re.compile(r'\b(?:free\s*rsvp|link\s*to\s*free\s*rsvp|free\s*before\s*\d{1,2}\s*(?:am|pm)?)\b', re.I)
TITLE_NOISE = re.compile(r'\b(?:free|entry|rsvp|tickets?|guestlist|link|to|the|at|dj|saturday|saturdays|friday|fridays)\b', re.I)


def norm(value):
    text = unicodedata.normalize('NFKD', str(value or ''))
    text = ''.join(c for c in text if not unicodedata.combining(c))
    return ' '.join(re.findall(r'[a-z0-9]+', text.casefold().replace('&', ' and ')))


def time_of(event):
    try:
        dt = datetime.fromisoformat(event.get('start') or '')
        return dt.astimezone(EASTERN) if dt.tzinfo else None
    except (ValueError, TypeError, OverflowError):
        return None


def venue_of(event):
    value = norm(event.get('venue'))
    return VENUE_ALIASES.get(value, value)


def similarity(x, y):
    return SequenceMatcher(None, norm(x), norm(y)).ratio() if norm(x) and norm(y) else 0


def significant_words(title):
    words = norm(title).split()
    return {w for w in words if len(w) >= 4 and not TITLE_NOISE.fullmatch(w)}


def describe(event, index):
    return [
        f'  Record #{index + 1}: {event.get("title") or "(untitled)"}',
        f'    Start: {event.get("start") or "unknown"}',
        f'    Venue: {event.get("venue") or "(not supplied)"}',
        f'    Source: {event.get("source_name") or "unknown"}',
        f'    ID: {event.get("source_id") or event.get("id") or "(not supplied)"}',
        f'    URL: {event.get("source_url") or event.get("url") or "(not supplied)"}',
    ]


def build_report(events):
    findings = []
    seen = set()
    for i, event in enumerate(events):
        title = str(event.get('title') or '')
        if ADDON.search(title):
            findings.append(('PROMOTION / ADD-ON', 'Ticket add-on or upgrade; verify this is not a standalone event', [i]))
        elif GENERIC_PROMO.search(title):
            findings.append(('PROMOTION / ADD-ON', 'Generic guestlist, alert, discount or lineup listing; check whether it describes a real event', [i]))
        elif RSVP_PROMO.search(title):
            findings.append(('PROMOTION / ADD-ON', 'RSVP or free-before-time offer; could be a legitimate event, review before hiding', [i]))

    # Same venue and same local date. Time is crucial: multiple shows must remain distinct.
    by_venue_day = defaultdict(list)
    by_day = defaultdict(list)
    for i, event in enumerate(events):
        dt = time_of(event)
        if not dt:
            continue
        by_day[dt.date()].append(i)
        venue = venue_of(event)
        if venue:
            by_venue_day[(venue, dt.date())].append(i)

    for (venue, date), indexes in sorted(by_venue_day.items(), key=lambda x: (x[0][1], x[0][0])):
        for pos, i in enumerate(indexes):
            for j in indexes[pos + 1:]:
                a, b = events[i], events[j]
                minutes = abs((time_of(a) - time_of(b)).total_seconds()) / 60
                if minutes > 90:
                    continue
                score = similarity(a.get('title'), b.get('title'))
                wa, wb = significant_words(a.get('title')), significant_words(b.get('title'))
                shared = wa & wb
                # Never use mere shared generic words as proof of identity.
                similar = score >= .78 or (bool(shared) and len(shared) >= 1 and
                    (wa <= wb or wb <= wa) and min(len(wa), len(wb)) >= 1)
                if not similar:
                    continue
                strong = minutes <= 30 and score >= .85
                category = 'LIKELY DUPLICATE' if strong else 'POSSIBLE DUPLICATE'
                reason = (f'Same venue ({venue}) and date ({date}); '
                          f'titles {score:.0%} similar; starts {minutes:.0f} minutes apart')
                findings.append((category, reason, [i, j]))
                seen.add((min(i, j), max(i, j)))

    # Venue missing or inconsistently named: require a distinctive title and tight time.
    for date, indexes in sorted(by_day.items()):
        for pos, i in enumerate(indexes):
            for j in indexes[pos + 1:]:
                pair = (min(i, j), max(i, j))
                if pair in seen:
                    continue
                a, b = events[i], events[j]
                va, vb = venue_of(a), venue_of(b)
                if va and vb and va != vb:
                    continue  # Conflicting named venues: not enough evidence.
                if va and vb:
                    continue  # Already assessed in same-venue pass.
                minutes = abs((time_of(a) - time_of(b)).total_seconds()) / 60
                if minutes > 60:
                    continue
                wa, wb = significant_words(a.get('title')), significant_words(b.get('title'))
                shared = wa & wb
                if not shared or not (wa <= wb or wb <= wa):
                    continue
                # A single word must be distinctive (e.g. COSTA, BONES), not generic.
                if len(shared) == 1 and len(next(iter(shared))) < 5:
                    continue
                findings.append(('POSSIBLE DUPLICATE',
                    f'One or both venues missing; shared distinctive title terms ({", ".join(sorted(shared))}); starts {minutes:.0f} minutes apart; verify venue before merging',
                    [i, j]))
                seen.add(pair)

    order = {'LIKELY DUPLICATE': 0, 'POSSIBLE DUPLICATE': 1, 'PROMOTION / ADD-ON': 2}
    findings.sort(key=lambda x: (order[x[0]], x[2][0], x[2][-1]))
    counts = Counter(category for category, _, _ in findings)
    lines = ["HAPPENIN' — EVENT QUALITY REVIEW", 
        f'Generated: {datetime.now(EASTERN).isoformat(timespec="seconds")}',
        f'Input: {INPUT.name}', f'Events reviewed: {len(events)}',
        f'Findings: {len(findings)}',
        f'Likely duplicate pairs: {counts["LIKELY DUPLICATE"]}',
        f'Possible duplicate pairs: {counts["POSSIBLE DUPLICATE"]}',
        f'Promotion / add-on flags: {counts["PROMOTION / ADD-ON"]}', '',
        'REVIEW ONLY: No events have been changed or removed.',
        'Do not automatically merge separate performances or hide free-entry events.', '']
    if not findings:
        lines.append('No suspicious listings found under current rules.')
    for n, (category, reason, indexes) in enumerate(findings, 1):
        lines.extend([f'[{n}] {category}', f'  Reason: {reason}'])
        for index in indexes:
            lines.extend(describe(events[index], index))
        lines.append('')
    return '\n'.join(lines), counts


def main():
    if not INPUT.exists():
        print(f'Cannot find {INPUT}. Place event_quality.py beside events.json.')
        return
    try:
        with INPUT.open(encoding='utf-8') as f:
            events = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        print(f'Could not read events.json: {exc}')
        return
    if not isinstance(events, list) or not all(isinstance(e, dict) for e in events):
        print('events.json must be a JSON list of event objects.')
        return
    report, counts = build_report(events)
    REPORTS.mkdir(exist_ok=True)
    stamp = datetime.now(EASTERN).strftime('%Y-%m-%d_%H%M%S_%f')
    path = REPORTS / f'event_quality_{stamp}.txt'
    path.write_text(report, encoding='utf-8')
    print(f'Reviewed {len(events)} events; flagged {sum(counts.values())} findings.')
    for label in ('LIKELY DUPLICATE', 'POSSIBLE DUPLICATE', 'PROMOTION / ADD-ON'):
        print(f'  {label}: {counts[label]}')
    print(f'Report saved: {path}')
    print('events.json was not changed.')


if __name__ == '__main__':
    main()
