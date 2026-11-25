"""Happenin' single-command operator workflow. Run: python happenin.py

Collect into an isolated staging folder, review findings, and publish only after
explicit confirmation. Existing ingest.py and preview_processor_v2.py are reused.
"""
import json
import shutil
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
EASTERN = ZoneInfo('America/New_York')


def write_json_atomic(path, value):
    temp = path.with_name(path.name + '.tmp')
    temp.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    temp.replace(path)


def ask(prompt, options):
    while True:
        choice = input(prompt).strip().lower()
        if choice in options:
            return choice
        print('Choose: ' + ', '.join(options))


def label(event):
    return f"{event.get('title', '(untitled)')} | {event.get('source_name', '?')} | {event.get('start', '?')} | {event.get('venue', '?')}"


def main():
    required = ['ingest.py', 'preview_processor_v2.py', 'quality_rules.json',
                'quality_rules.py', 'event_quality.py', 'duplicate_reviewer.py',
                'happenin_deduplication.py']
    missing = [name for name in required if not (ROOT / name).is_file()]
    if missing:
        raise FileNotFoundError('Missing: ' + ', '.join(missing))

    import ingest
    import preview_processor_v2 as preview
    import quality_rules
    import event_quality
    import duplicate_reviewer as reviewer
    from happenin_deduplication import merge_group

    stamp = datetime.now(EASTERN).strftime('%Y-%m-%d_%H%M%S_%f')
    stage = ROOT / 'runs' / stamp
    stage.mkdir(parents=True, exist_ok=False)
    decisions_path = ROOT / 'duplicate_decisions.json'
    if not decisions_path.exists():
        write_json_atomic(decisions_path, {'version': 1, 'decisions': {}})
    # Copy decision/rule snapshots into staging; don't alter originals during collection.
    shutil.copy2(decisions_path, stage / 'duplicate_decisions.json')
    shutil.copy2(ROOT / 'quality_rules.json', stage / 'quality_rules.json')

    original_folder = ingest.FOLDER
    original_preview_root = preview.ROOT
    original_rules_path = quality_rules.RULES_PATH
    try:
        ingest.FOLDER = stage
        print("\nHAPPENIN' — COLLECT (STAGING ONLY)")
        ingest.main()
    finally:
        ingest.FOLDER = original_folder

    fresh_path = stage / 'events.json'
    events = json.loads(fresh_path.read_text(encoding='utf-8'))
    if not isinstance(events, list):
        raise ValueError('Ingestion did not produce an event list.')

    # Existing reviewer understands duplicate pairs and saved event identities.
    decisions = json.loads(decisions_path.read_text(encoding='utf-8'))
    if not isinstance(decisions, dict) or not isinstance(decisions.get('decisions'), dict):
        raise ValueError('Invalid duplicate_decisions.json')
    findings = reviewer.duplicate_findings(events)
    pending = [(cat, reason, i, j, reviewer.pair_key(events[i], events[j]))
               for cat, reason, i, j in findings
               if reviewer.pair_key(events[i], events[j]) not in decisions['decisions']]
    print(f'\nREVIEW — {len(pending)} undecided duplicate pairs')
    for number, (cat, reason, i, j, key) in enumerate(pending, 1):
        a, b = events[i], events[j]
        print(f'\n[{number}/{len(pending)}] {cat}: {reason}')
        print(' A:', label(a))
        print(' B:', label(b))
        print(' [m] Merge  [k] Keep separate  [s] Skip  [q] Stop review')
        choice = ask(' Choice: ', {'m', 'k', 's', 'q'})
        if choice == 'q':
            break
        if choice == 's':
            continue
        if choice == 'm':
            merged = merge_group([a, b])
            print(' Merge primary:', label(merged))
        if ask(' Save decision? [y/N]: ', {'y', 'n', ''}) != 'y':
            continue
        decisions['decisions'][key] = {
            'decision': 'merge' if choice == 'm' else 'keep_separate',
            'event_a': reviewer.event_identity(a),
            'event_b': reviewer.event_identity(b),
            'titles': [str(a.get('title') or ''), str(b.get('title') or '')],
            'reviewed_at': datetime.now(EASTERN).isoformat(timespec='seconds'),
        }
        write_json_atomic(decisions_path, decisions)
    # Update staged snapshot after review. Preview uses staging only.
    shutil.copy2(decisions_path, stage / 'duplicate_decisions.json')

    try:
        preview.ROOT = stage
        quality_rules.RULES_PATH = stage / 'quality_rules.json'
        preview.run()
    finally:
        preview.ROOT = original_preview_root
        quality_rules.RULES_PATH = original_rules_path

    cleaned = json.loads((stage / 'events_preview.json').read_text(encoding='utf-8'))
    report, counts = event_quality.build_report(cleaned)
    (stage / 'quality_report.txt').write_text(report, encoding='utf-8')
    print('\nQUALITY CHECK:', dict(counts))
    print('Quality report:', stage / 'quality_report.txt')

    # Promotion review is explicit, per-listing, and never transfers ticket links.
    # This is an operator decision for the current run, not a broad permanent rule.
    import re
    flagged = []
    for section in re.split(r'(?m)^\[\d+\] ', report)[1:]:
        if not section.startswith('PROMOTION / ADD-ON'):
            continue
        match = re.search(r'(?m)^  Record #(\d+):', section)
        if match:
            idx = int(match.group(1)) - 1
            if 0 <= idx < len(cleaned) and idx not in flagged:
                flagged.append(idx)
    hidden = set()
    for idx in flagged:
        print('\nPROMOTION / ADD-ON:', label(cleaned[idx]))
        print(' [h] Hide this listing  [k] Keep it  [s] Skip for now')
        choice = ask(' Choice: ', {'h', 'k', 's'})
        if choice == 'h' and ask(' Confirm hide? [y/N]: ', {'y', 'n', ''}) == 'y':
            hidden.add(idx)
    final_events = [event for idx, event in enumerate(cleaned) if idx not in hidden]
    final_events.sort(key=lambda event: str(event.get('start') or ''))
    final_path = stage / 'events_approved_preview.json'
    write_json_atomic(final_path, final_events)
    final_report, final_counts = event_quality.build_report(final_events)
    (stage / 'final_quality_report.txt').write_text(final_report, encoding='utf-8')

    print('\nHAPPENIN\' — READY FOR PUBLISH REVIEW')
    print('Collected after automatic deduplication:', len(events))
    print('After saved decisions and permanent rules:', len(cleaned))
    print('After manual promotion hides:', len(final_events))
    print('Remaining quality warnings:', dict(final_counts))
    print('Staged feed:', final_path)
    print('No published file has been changed.')
    if ask('\nPublish this feed to events.json? [y/N]: ', {'y', 'n', ''}) != 'y':
        print('Not published. All staging reports and data remain in:', stage)
        return

    published = ROOT / 'events.json'
    backups = ROOT / 'backups'
    backups.mkdir(exist_ok=True)
    if published.exists():
        backup = backups / f'events_before_publish_{stamp}.json'
        shutil.copy2(published, backup)
        print('Previous published feed backed up:', backup)
    # The source of the published feed is the explicitly reviewed staged preview.
    write_json_atomic(published, final_events)
    print('PUBLISHED:', published)
    print('Run details:', stage)


if __name__ == '__main__':
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        print('\nStopped. Published feed was not changed by an incomplete run.')
    except Exception as exc:
        print(f'\nWORKFLOW STOPPED: {type(exc).__name__}: {exc}')
        raise SystemExit(1)
