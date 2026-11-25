"""Happenin' read-only-source preview of permanent rules and reviewed duplicate decisions.
Run beside events.json, quality_rules.json, duplicate_decisions.json and helper scripts:
    python preview_processor.py
Writes only events_preview.json and reports/preview_application_*.txt.
"""
import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import quality_rules
import happenin_deduplication as dedup
from duplicate_reviewer import event_identity, pair_key

ROOT = Path(__file__).resolve().parent
EASTERN = ZoneInfo('America/New_York')


def identity_token(event):
    return json.dumps(event_identity(event), ensure_ascii=False, separators=(',', ':'))


def label(event):
    return f"{event.get('title') or '(untitled)'} | {event.get('source_name') or '?'} | {event.get('start') or '?'}"


def run():
    events = json.loads((ROOT / 'events.json').read_text(encoding='utf-8'))
    if not isinstance(events, list) or not all(isinstance(e, dict) for e in events):
        raise ValueError('events.json must contain a list of event objects.')
    rules = quality_rules.load_rules()
    rule_results = quality_rules.apply_rules(events, rules)
    statuses = [item[2] for item in rule_results]
    if any(s == 'CONFLICT — REVIEW' for s in statuses):
        raise ValueError('Conflicting permanent rules exist. Resolve them before previewing.')

    decision_data = json.loads((ROOT / 'duplicate_decisions.json').read_text(encoding='utf-8'))
    if not isinstance(decision_data, dict) or not isinstance(decision_data.get('decisions'), dict):
        raise ValueError('duplicate_decisions.json must contain a decisions object.')

    identity_indexes = defaultdict(list)
    for i, event in enumerate(events):
        identity_indexes[identity_token(event)].append(i)

    def resolve(identity):
        token = json.dumps(identity, ensure_ascii=False, separators=(',', ':'))
        matches = identity_indexes.get(token, [])
        if len(matches) != 1:
            raise ValueError(f'Saved decision identity matches {len(matches)} current records: {identity!r}. No output written.')
        return matches[0]

    parent = list(range(len(events)))

    def root(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(a, b):
        ra, rb = root(a), root(b)
        if ra != rb:
            parent[rb] = ra

    hidden_addons = set()
    keep_separate = []
    merge_pairs = []
    decisions = decision_data['decisions']
    for key, record in decisions.items():
        if not isinstance(record, dict):
            raise ValueError(f'Invalid decision: {key}')
        a, b = resolve(record['event_a']), resolve(record['event_b'])
        if a == b or pair_key(events[a], events[b]) != key:
            raise ValueError(f'Stale or invalid decision key: {key}. No output written.')
        action = record.get('decision')
        if action == 'merge':
            merge_pairs.append((a, b))
            union(a, b)
        elif action == 'keep_separate':
            keep_separate.append((a, b))
        elif action == 'hide_addon':
            hidden = resolve(record['hide_event'])
            kept = resolve(record['keep_event'])
            if {hidden, kept} != {a, b}:
                raise ValueError(f'Invalid hide_addon target: {key}')
            hidden_addons.add(hidden)
        else:
            raise ValueError(f'Unknown decision type {action!r}: {key}')

    groups = defaultdict(list)
    for i in range(len(events)):
        groups[root(i)].append(i)
    merge_groups = [g for g in groups.values() if len(g) > 1]

    # Reject contradictory instructions rather than silently choosing one.
    for a, b in keep_separate:
        if root(a) == root(b):
            raise ValueError(f'Keep-separate pair belongs to an approved merge group: {label(events[a])} / {label(events[b])}')
    for group in merge_groups:
        if any(i in hidden_addons for i in group):
            raise ValueError('An event marked Hide Add-on is also in an approved merge group. Review decisions first.')
        if any(statuses[i] == 'HIDE' for i in group):
            raise ValueError('A permanent Hide rule matches a member of an approved merge group. Review rules first.')

    output = []
    emitted_groups = set()
    hidden_rules = []
    hidden_addon_labels = []
    merge_descriptions = []
    for i, event in enumerate(events):
        if statuses[i] == 'HIDE':
            hidden_rules.append(label(event))
            continue
        if i in hidden_addons:
            hidden_addon_labels.append(label(event))
            continue
        group = groups[root(i)]
        if len(group) == 1:
            output.append(dict(event))
            continue
        group_root = root(i)
        if group_root in emitted_groups:
            continue
        emitted_groups.add(group_root)
        merged = dedup.merge_group([events[j] for j in group])
        # merge_group chooses venue source as primary. Explicitly preserve its
        # start time, even if the ticketing source reports an earlier doors time.
        venue_members = [events[j] for j in group if dedup.source_priority(events[j]) == 0]
        if venue_members:
            authoritative = sorted(venue_members, key=lambda e: -sum(not dedup.is_missing(v) for v in e.values()))[0]
            merged['start'] = authoritative.get('start')
        output.append(merged)
        merge_descriptions.append((label(merged), [label(events[j]) for j in group]))

    now = datetime.now(EASTERN)
    stamp = now.strftime('%Y-%m-%d_%H%M%S_%f')
    report_lines = [
        "HAPPENIN' — CLEANED EVENTS PREVIEW",
        f'Generated: {now.isoformat(timespec="seconds")}',
        f'Input events: {len(events)}',
        f'Permanent-rule hides: {len(hidden_rules)}',
        f'Individual add-ons hidden: {len(hidden_addon_labels)}',
        f'Approved merge pairs: {len(merge_pairs)}',
        f'Connected merge groups: {len(merge_groups)}',
        f'Records consolidated by merging: {sum(len(g) - 1 for g in merge_groups)}',
        f'Keep-separate decisions: {len(keep_separate)}',
        f'Preview output events: {len(output)}',
        '', 'SOURCE FILES UNCHANGED: events.json, ingest.py, rules and decisions.',
        'The preview file is not the published feed.', '',
        'PERMANENT-RULE HIDES',
        *([f'  - {x}' for x in hidden_rules] or ['  None']), '',
        'HIDDEN ADD-ONS',
        *([f'  - {x}' for x in hidden_addon_labels] or ['  None']), '',
        'APPROVED MERGE GROUPS',
    ]
    if not merge_descriptions:
        report_lines.append('  None')
    for number, (merged_label, members) in enumerate(merge_descriptions, 1):
        report_lines.append(f'  {number}. OUTPUT: {merged_label}')
        report_lines.extend(f'     FROM: {member}' for member in members)
    report_lines.extend(['', 'KEEP-SEPARATE DECISIONS'])
    report_lines.extend([f'  - {label(events[a])} / {label(events[b])}' for a, b in keep_separate] or ['  None'])

    # Write only after all validation and transformations succeed.
    report_dir = ROOT / 'reports'
    report_dir.mkdir(exist_ok=True)
    preview_path = ROOT / 'events_preview.json'
    report_path = report_dir / f'preview_application_{stamp}.txt'
    preview_path.write_text(json.dumps(output, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    report_path.write_text('\n'.join(report_lines) + '\n', encoding='utf-8')
    print("HAPPENIN' — CLEANED PREVIEW")
    print(f'Input: {len(events)} | Rule hides: {len(hidden_rules)} | Add-ons hidden: {len(hidden_addon_labels)}')
    print(f'Merge pairs: {len(merge_pairs)} | Merge groups: {len(merge_groups)}')
    print(f'Preview events: {len(output)}')
    print(f'Preview: {preview_path}')
    print(f'Report: {report_path}')
    print('Original files unchanged.')


if __name__ == '__main__':
    try:
        run()
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(f'Preview NOT generated: {exc}')
        raise SystemExit(1)
