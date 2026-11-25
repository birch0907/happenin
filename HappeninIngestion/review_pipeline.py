"""Happenin' combined review report (read-only).

Run: python review_pipeline.py
Requires events.json, quality_rules.json, quality_rules.py, event_quality.py.
Never modifies event data or saved rules.
"""
import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from quality_rules import load_rules, apply_rules
from event_quality import build_report

ROOT = Path(__file__).resolve().parent
EASTERN = ZoneInfo('America/New_York')


def main():
    events_path = ROOT / 'events.json'
    if not events_path.exists():
        print('Missing events.json. Place this script in your HappeninIngestion folder.')
        return
    try:
        events = json.loads(events_path.read_text(encoding='utf-8'))
        if not isinstance(events, list) or not all(isinstance(e, dict) for e in events):
            raise ValueError('events.json must be a list of event objects')
        rules = load_rules()
        results = apply_rules(events, rules)
        quality_report, _ = build_report(events)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f'Cannot generate report: {exc}')
        return

    # event_quality.build_report currently exposes its findings as a TXT report.
    # Read its numbered sections; this adapter does not alter the quality checker.
    sections = re.split(r'(?=^\[\d+\] (?:LIKELY DUPLICATE|POSSIBLE DUPLICATE|PROMOTION / ADD-ON)$)',
                        quality_report, flags=re.MULTILINE)
    findings = []
    for section in sections:
        header = re.match(r'^\[\d+\] ([^\r\n]+)', section)
        if not header:
            continue
        indexes = [int(n) - 1 for n in re.findall(r'^  Record #(\d+):', section, flags=re.MULTILINE)]
        if indexes and all(0 <= i < len(events) for i in indexes):
            findings.append((header.group(1), indexes, section.strip()))

    expected_match = re.search(r'^Findings: (\d+)$', quality_report, flags=re.MULTILINE)
    if expected_match and int(expected_match.group(1)) != len(findings):
        print(f'ERROR: Quality checker reported {expected_match.group(1)} findings, '
              f'but review pipeline parsed {len(findings)}. No report was generated.')
        return

    status_by_index = {index - 1: status for index, _, status, _ in results}
    pending = []
    resolved = Counter()
    for category, indexes, section in findings:
        statuses = [status_by_index[i] for i in indexes]
        # Hiding a listing resolves its promotion flag and removes its duplicate pairing.
        if 'HIDE' in statuses:
            resolved['HIDE rule'] += 1
            continue
        # A KEEP rule resolves only an individual promotion warning, not a duplicate
        # involving another listing; a duplicate still needs a merge/keep-both decision.
        if len(indexes) == 1 and statuses == ['KEEP']:
            resolved['KEEP rule'] += 1
            continue
        pending.append((category, section))

    conflicts = [(index, event, matched) for index, event, status, matched in results
                 if status == 'CONFLICT — REVIEW']
    counts = Counter(status for _, _, status, _ in results)
    categories = Counter(category for category, _ in pending)
    stamp = datetime.now(EASTERN).strftime('%Y-%m-%d_%H%M%S_%f')
    report_dir = ROOT / 'reports'
    report_dir.mkdir(exist_ok=True)
    path = report_dir / f'pending_review_{stamp}.txt'
    lines = [
        "HAPPENIN' — PENDING EVENT REVIEW",
        f'Generated: {datetime.now(EASTERN).isoformat(timespec="seconds")}',
        f'Events checked: {len(events)}',
        f'Permanent rules: {len(rules)} ({sum(r.get("enabled", True) for r in rules)} enabled)',
        f'Rule matches — HIDE: {counts["HIDE"]}, KEEP: {counts["KEEP"]}, conflicts: {len(conflicts)}',
        f'No rule matched: {counts["NO RULE"]} (NOT all pending review)',
        f'Quality findings before rules: {len(findings)}',
        f'Quality findings resolved by rules: {sum(resolved.values())}',
        f'Unresolved quality findings: {len(pending)}',
        f'  Likely duplicate pairs: {categories["LIKELY DUPLICATE"]}',
        f'  Possible duplicate pairs: {categories["POSSIBLE DUPLICATE"]}',
        f'  Promotion / add-on flags: {categories["PROMOTION / ADD-ON"]}',
        '',
        'REVIEW ONLY — No events, rules, or published feeds have been changed.',
        'Duplicate pairs can overlap; findings are not counts of unique events.',
        '',
    ]
    if conflicts:
        lines.append('PERMANENT RULE CONFLICTS — REVIEW REQUIRED')
        for index, event, matched in conflicts:
            lines.append(f'  Record #{index}: {event.get("title", "(untitled)")}')
            lines.append('    Conflicting rules: ' + ', '.join(r['id'] for r in matched))
        lines.append('')
    lines.append('UNRESOLVED QUALITY FINDINGS')
    if not pending:
        lines.append('  None')
    else:
        for number, (_, section) in enumerate(pending, 1):
            section = re.sub(r'^\[\d+\]', f'[{number}]', section, count=1)
            lines.extend([section, ''])
    path.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(f'Reviewed {len(events)} events.')
    print(f'Quality findings: {len(findings)}; resolved by permanent rules: {sum(resolved.values())}.')
    print(f'Unresolved quality findings: {len(pending)}; rule conflicts: {len(conflicts)}.')
    print(f'Saved: {path}')
    print('No input files changed.')


if __name__ == '__main__':
    main()
