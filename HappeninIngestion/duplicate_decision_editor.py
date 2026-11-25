"""Edit saved Happenin' duplicate decisions without changing events.json.
Run: python duplicate_decision_editor.py
"""
import json
import shutil
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from duplicate_reviewer import EVENTS, DECISIONS, event_identity, pair_key, load_decisions

EASTERN = ZoneInfo('America/New_York')


def describe(event):
    return (f"{event.get('title') or '(untitled)'} | "
            f"{event.get('source_name') or '?'} | "
            f"{event.get('start') or '?'} | "
            f"{event.get('venue') or '(venue missing)'}")


def save_with_backup(data):
    # Never silently replace the only copy of user review decisions.
    backup_dir = DECISIONS.parent / 'backups'
    backup_dir.mkdir(exist_ok=True)
    stamp = datetime.now(EASTERN).strftime('%Y%m%d_%H%M%S_%f')
    backup = backup_dir / f'duplicate_decisions_before_edit_{stamp}.json'
    shutil.copy2(DECISIONS, backup)
    temp = DECISIONS.with_name(DECISIONS.name + '.tmp')
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temp.replace(DECISIONS)
    return backup


def main():
    try:
        events = json.loads(EVENTS.read_text(encoding='utf-8'))
        if not isinstance(events, list) or not all(isinstance(e, dict) for e in events):
            raise ValueError('events.json must contain a list of event objects')
        data = load_decisions()
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f'Could not open decisions: {exc}')
        return

    by_identity = {}
    for event in events:
        identity = json.dumps(event_identity(event), ensure_ascii=False)
        by_identity.setdefault(identity, []).append(event)

    entries = sorted(data['decisions'].items(), key=lambda item: item[1].get('reviewed_at', ''))
    if not entries:
        print('No saved duplicate decisions yet.')
        return

    print("\nHAPPENIN' — EDIT DUPLICATE DECISIONS")
    print('Changes affect duplicate_decisions.json ONLY; no events are merged or hidden.')
    for number, (_, record) in enumerate(entries, 1):
        titles = record.get('titles', ['(unknown)', '(unknown)'])
        a = str(titles[0]) if len(titles) > 0 else '(unknown)'
        b = str(titles[1]) if len(titles) > 1 else '(unknown)'
        print(f"{number:2}. [{record.get('decision', 'unknown')}] {a}  /  {b}")

    selection = input('\nDecision number to edit (0 to cancel): ').strip()
    if selection == '0':
        print('Cancelled.')
        return
    if not selection.isdigit() or not 1 <= int(selection) <= len(entries):
        print('Invalid number; nothing changed.')
        return

    key, record = entries[int(selection) - 1]
    pair = []
    for identity in (record.get('event_a'), record.get('event_b')):
        found = by_identity.get(json.dumps(identity, ensure_ascii=False), [])
        if len(found) != 1:
            print('Could not uniquely match both saved events to events.json.')
            print('No changes made; event records may have changed since the review.')
            return
        pair.append(found[0])
    a, b = pair
    if pair_key(a, b) != key:
        print('Saved decision key does not match current events. No changes made.')
        return

    print('\nCurrent decision:', record.get('decision', 'unknown'))
    print(' A:', describe(a))
    print(' B:', describe(b))
    print('\n[m] Merge  [k] Keep separate  [h] Hide add-on  [r] Remove decision  [c] Cancel')
    choice = input('New decision: ').strip().lower()
    if choice not in ('m', 'k', 'h', 'r', 'c'):
        print('Invalid choice; nothing changed.')
        return
    if choice == 'c':
        print('Cancelled.')
        return

    new_record = dict(record)
    if choice == 'h':
        print('\nWhich listing is the add-on to hide?')
        print(' A:', describe(a))
        print(' B:', describe(b))
        target = input('Hide [a] or [b] (anything else cancels): ').strip().lower()
        if target not in ('a', 'b'):
            print('Cancelled.')
            return
        hidden = a if target == 'a' else b
        kept = b if target == 'a' else a
        print('\nHIDE:', describe(hidden))
        print('KEEP:', describe(kept))
        new_record['decision'] = 'hide_addon'
        new_record['hide_event'] = event_identity(hidden)
        new_record['keep_event'] = event_identity(kept)
        print('This is a saved review decision only; it does NOT add a permanent Hide rule.')
    elif choice == 'r':
        print('\nREMOVE the saved decision, returning this pair to pending review.')
    else:
        new_record['decision'] = 'merge' if choice == 'm' else 'keep_separate'
        new_record.pop('hide_event', None)
        new_record.pop('keep_event', None)
        print('\nNew decision:', new_record['decision'])

    if input('Confirm change? [y/N]: ').strip().lower() != 'y':
        print('Cancelled; nothing changed.')
        return
    if choice == 'r':
        del data['decisions'][key]
    else:
        new_record['reviewed_at'] = datetime.now(EASTERN).isoformat(timespec='seconds')
        data['decisions'][key] = new_record
    try:
        backup = save_with_backup(data)
    except OSError as exc:
        print(f'Could not save change: {exc}')
        return
    print(f'Saved: {DECISIONS}')
    print(f'Backup: {backup}')
    print('events.json and ingest.py were not changed.')


if __name__ == '__main__':
    main()
