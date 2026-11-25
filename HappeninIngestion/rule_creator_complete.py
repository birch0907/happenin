"""Interactive, conservative permanent-rule creator for Happenin'.

Run: python rule_creator.py
Only edits quality_rules.json after explicit confirmation. Never edits events.json.
"""
import json
import re
import shutil
from collections import Counter
from datetime import datetime
from pathlib import Path

from quality_rules import ROOT, RULES_PATH, load_rules, apply_rules, normalize
from event_quality import build_report

EVENTS_PATH = ROOT / 'events.json'


def flagged_promotions(report, events):
    """Extract only single-event promotion warnings from the existing checker."""
    sections = re.split(r'(?=^\[\d+\] (?:LIKELY DUPLICATE|POSSIBLE DUPLICATE|PROMOTION / ADD-ON)$)',
                        report, flags=re.MULTILINE)
    flagged = []
    for section in sections:
        if not re.match(r'^\[\d+\] PROMOTION / ADD-ON(?:\r?\n|$)', section):
            continue
        matches = re.findall(r'^  Record #(\d+):', section, flags=re.MULTILINE)
        if len(matches) == 1:
            idx = int(matches[0]) - 1
            if 0 <= idx < len(events):
                flagged.append(idx)
    return sorted(set(flagged))


def prompt_choice(message, allowed):
    while True:
        response = input(message).strip().lower()
        if response in allowed:
            return response
        print('Please enter ' + ', '.join(sorted(allowed)) + '.')


def main():
    try:
        events = json.loads(EVENTS_PATH.read_text(encoding='utf-8'))
        if not isinstance(events, list) or not all(isinstance(e, dict) for e in events):
            raise ValueError('events.json must be a list of event objects')
        rules = load_rules()
        report, _ = build_report(events)
        expected = re.search(r'^Findings: (\d+)$', report, re.MULTILINE)
        sections = re.findall(r'^\[\d+\] (?:LIKELY DUPLICATE|POSSIBLE DUPLICATE|PROMOTION / ADD-ON)$', report, re.MULTILINE)
        if expected is None or int(expected.group(1)) != len(sections):
            raise ValueError('Quality report format changed; refusing to create rules.')
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f'Cannot load review data: {exc}')
        return

    statuses = {i - 1: status for i, _, status, _ in apply_rules(events, rules)}
    candidates = [i for i in flagged_promotions(report, events) if statuses[i] == 'NO RULE']
    # Group identical source + normalized title, so one rule can cover multiple dates.
    groups = {}
    for i in candidates:
        event = events[i]
        source, title = str(event.get('source_name') or '').strip(), str(event.get('title') or '').strip()
        if source and title:
            groups.setdefault((normalize(source), normalize(title)), []).append(i)
    choices = sorted(groups.values(), key=lambda ids: (-len(ids), events[ids[0]].get('title', '').casefold()))
    if not choices:
        print('No unresolved promotional listings with usable titles and sources.')
        return

    print('\nHAPPENIN\' — RULE CREATOR (promotion flags only)')
    print('Duplicate pairs remain in manual review; this tool does not merge events.')
    for number, indices in enumerate(choices, 1):
        event = events[indices[0]]
        print(f'{number:2}. [{len(indices)} flagged] {event["title"]}  ({event["source_name"]})')
    print(' 0. Cancel')
    while True:
        answer = input('\nChoose listing number: ').strip()
        if answer == '0':
            print('Cancelled; nothing changed.')
            return
        if answer.isdigit() and 1 <= int(answer) <= len(choices):
            break
        print('Enter one of the displayed numbers.')

    indices = choices[int(answer) - 1]
    chosen = events[indices[0]]
    source = str(chosen['source_name']).strip()
    title = str(chosen['title']).strip()
    print(f'\nTitle: {title}\nSource: {source}')
    print(f'Flagged occurrences in current dataset: {len(indices)}')
    print('Create a permanent rule matching this exact title AND source (case/punctuation normalized).')
    action_input = prompt_choice('Choose [h]ide, [k]eep, or [c]ancel: ', {'h', 'k', 'c'})
    if action_input == 'c':
        print('Cancelled; nothing changed.')
        return
    action = {'h': 'hide', 'k': 'keep'}[action_input]
    base = 'rule-' + re.sub(r'[^a-z0-9]+', '-', normalize(source + ' ' + title)).strip('-')[:65]
    used = {r['id'] for r in rules}
    rule_id = base
    suffix = 2
    while rule_id in used:
        rule_id = f'{base}-{suffix}'
        suffix += 1
    rule = {'id': rule_id, 'enabled': True, 'action': action,
            'conditions': [
                {'field': 'source_name', 'match': 'equals', 'value': source},
                {'field': 'title', 'match': 'equals', 'value': title},
            ]}
    before = apply_rules(events, rules)
    after = apply_rules(events, rules + [rule])
    transitions = Counter((old[2], new[2]) for old, new in zip(before, after) if old[2] != new[2])
    print('\nPREVIEW of this rule across all current events:')
    for (old, new), count in transitions.items():
        print(f'  {count} events: {old} -> {new}')
    if not transitions:
        print('  No status changes. Rule not saved.')
        return
    if any(new == 'CONFLICT — REVIEW' for (_, new) in transitions):
        print('Rule would introduce a conflict. Nothing saved.')
        return
    if prompt_choice('Save this permanent rule? [y/n]: ', {'y', 'n'}) != 'y':
        print('Cancelled; nothing changed.')
        return
    # Re-read before writing, to avoid accidentally overwriting unexpected changes.
    original = RULES_PATH.read_bytes()
    data = json.loads(original.decode('utf-8'))
    if data.get('rules') != rules:
        print('Rules changed since loading; nothing saved. Run again.')
        return
    backup = RULES_PATH.with_name('quality_rules_backup_' + datetime.now().strftime('%Y%m%d_%H%M%S_%f') + '.json')
    shutil.copy2(RULES_PATH, backup)
    data['rules'].append(rule)
    temp = RULES_PATH.with_name('quality_rules.tmp')
    try:
        temp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
        temp.replace(RULES_PATH)
    finally:
        if temp.exists():
            temp.unlink()
    print(f'\nSaved {action.upper()} rule: {rule_id}')
    print(f'Backup: {backup.name}')
    print('events.json and ingest.py were not modified.')
    print('Run: python review_pipeline.py  to see the updated review queue.')


if __name__ == '__main__':
    main()
