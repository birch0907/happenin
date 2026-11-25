"""Happenin' permanent event quality rules (review-only preview).

Run: python quality_rules.py
Reads events.json and quality_rules.json; writes a TXT preview to reports/.
Does NOT modify events.json, ingest.py, or the existing deduplication pipeline.
"""
import json
import re
import unicodedata
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
EVENTS_PATH = ROOT / 'events.json'
RULES_PATH = ROOT / 'quality_rules.json'
REPORTS_DIR = ROOT / 'reports'
EASTERN = ZoneInfo('America/New_York')
ALLOWED_ACTIONS = {'hide', 'keep'}
ALLOWED_FIELDS = {'title', 'source_name', 'venue', 'source_url'}
ALLOWED_MATCHES = {'equals', 'contains'}


def normalize(value):
    text = unicodedata.normalize('NFKD', str(value or ''))
    text = ''.join(c for c in text if not unicodedata.combining(c))
    return ' '.join(re.findall(r'[a-z0-9]+', text.casefold()))


def load_rules():
    if not RULES_PATH.exists():
        raise FileNotFoundError(f'Missing {RULES_PATH.name}; place it alongside this script.')
    with RULES_PATH.open(encoding='utf-8') as f:
        data = json.load(f)
    if not isinstance(data, dict) or not isinstance(data.get('rules'), list):
        raise ValueError('quality_rules.json must contain a "rules" list.')
    seen = set()
    for i, rule in enumerate(data['rules'], 1):
        if not isinstance(rule, dict):
            raise ValueError(f'Rule {i} must be an object.')
        rule_id = rule.get('id')
        if not isinstance(rule_id, str) or not rule_id.strip() or rule_id in seen:
            raise ValueError(f'Rule {i} needs a unique, nonempty id.')
        seen.add(rule_id)
        if rule.get('action') not in ALLOWED_ACTIONS:
            raise ValueError(f'{rule_id}: action must be hide or keep.')
        conditions = rule.get('conditions')
        if not isinstance(conditions, list) or not conditions:
            raise ValueError(f'{rule_id}: conditions must be a nonempty list.')
        for condition in conditions:
            if not isinstance(condition, dict) or condition.get('field') not in ALLOWED_FIELDS or condition.get('match') not in ALLOWED_MATCHES or not isinstance(condition.get('value'), str) or not condition['value'].strip():
                raise ValueError(f'{rule_id}: invalid condition (field, match, value required).')
    return data['rules']


def condition_matches(event, condition):
    actual = normalize(event.get(condition['field']))
    expected = normalize(condition['value'])
    if not actual or not expected:
        return False
    if condition['match'] == 'equals':
        return actual == expected
    # Word-boundary match avoids accidental substrings (e.g. 'vip' inside another word).
    return f' {expected} ' in f' {actual} '


def apply_rules(events, rules):
    results = []
    for index, event in enumerate(events, 1):
        matched = [rule for rule in rules if rule.get('enabled', True) and all(condition_matches(event, c) for c in rule['conditions'])]
        actions = {rule['action'] for rule in matched}
        if len(actions) > 1:
            status = 'CONFLICT — REVIEW'
        elif matched:
            status = next(iter(actions)).upper()
        else:
            status = 'NO RULE'
        results.append((index, event, status, matched))
    return results


def main():
    if not EVENTS_PATH.exists():
        print(f'Missing {EVENTS_PATH.name}. Run this beside your events.json file.')
        return
    with EVENTS_PATH.open(encoding='utf-8') as f:
        events = json.load(f)
    if not isinstance(events, list):
        raise ValueError('events.json must contain a list of events.')
    rules = load_rules()
    results = apply_rules(events, rules)
    counts = {name: sum(status == name for _, _, status, _ in results) for name in ('HIDE', 'KEEP', 'NO RULE', 'CONFLICT — REVIEW')}
    now = datetime.now(EASTERN)
    lines = [
        "HAPPENIN' — PERMANENT RULES PREVIEW",
        f'Generated: {now.isoformat(timespec="seconds")}',
        f'Events reviewed: {len(events)}',
        f'Enabled rules: {sum(rule.get("enabled", True) for rule in rules)}',
        f'Matched HIDE: {counts["HIDE"]}',
        f'Matched KEEP: {counts["KEEP"]}',
        f'Conflicting rules (review): {counts["CONFLICT — REVIEW"]}',
        f'No rule matched: {counts["NO RULE"]}',
        '',
        'PREVIEW ONLY: No events have been modified, hidden, or deleted.',
        'No-rule events are NOT automatically suspicious; use the quality checker for those.',
        '',
    ]
    for index, event, status, matched in results:
        if status == 'NO RULE':
            continue
        lines.extend([
            f'[{index}] {status} — {event.get("title", "(untitled)")}',
            f'  Source: {event.get("source_name", "(missing)")}',
            f'  Start: {event.get("start", "(missing)")}',
            f'  Venue: {event.get("venue") or "(missing)"}',
            f'  Rules: {", ".join(rule["id"] for rule in matched)}',
            f'  URL: {event.get("source_url") or event.get("url") or "(missing)"}',
            '',
        ])
    REPORTS_DIR.mkdir(exist_ok=True)
    path = REPORTS_DIR / f'quality_rules_preview_{now.strftime("%Y-%m-%d_%H%M%S")}.txt'
    path.write_text('\n'.join(lines), encoding='utf-8')
    print('\n'.join(lines[:11]))
    print(f'Report saved: {path}')


if __name__ == '__main__':
    main()
