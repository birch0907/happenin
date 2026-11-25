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