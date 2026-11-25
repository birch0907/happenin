"""Happenin' fresh ingestion dry run.

Run from the HappeninIngestion folder:
    python fresh_ingestion_test.py

Uses existing ingest.py and preview_processor_v2.py unchanged, redirecting their
output directories to a temporary folder. Never replaces the published events.json.
"""
import json
import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
EASTERN = ZoneInfo('America/New_York')


def main():
    # Validate inputs before invoking any collector.
    required = ('ingest.py', 'preview_processor_v2.py', 'quality_rules.json',
                'duplicate_decisions.json', 'event_quality.py')
    missing = [name for name in required if not (ROOT / name).is_file()]
    if missing:
        raise FileNotFoundError('Missing required files: ' + ', '.join(missing))

    import ingest
    import preview_processor_v2 as preview
    import quality_rules
    import event_quality

    # The two imported modules refer to ROOT/FOLDER for their outputs. Temporarily
    # redirect them; restore them even if collection or review fails.
    original_folder = ingest.FOLDER
    original_root = preview.ROOT
    original_rules_path = quality_rules.RULES_PATH
    stamp = datetime.now(EASTERN).strftime('%Y-%m-%d_%H%M%S_%f')
    with tempfile.TemporaryDirectory(prefix='happenin_fresh_test_') as temp:
        staging = Path(temp)
        shutil.copy2(ROOT / 'quality_rules.json', staging / 'quality_rules.json')
        shutil.copy2(ROOT / 'duplicate_decisions.json', staging / 'duplicate_decisions.json')
        try:
            ingest.FOLDER = staging
            preview.ROOT = staging
            quality_rules.RULES_PATH = staging / 'quality_rules.json'
            print("\nHAPPENIN' — FRESH INGESTION DRY RUN")
            print('Published events.json will NOT be replaced.\n')
            ingest.main()
            preview.run()
        finally:
            ingest.FOLDER = original_folder
            preview.ROOT = original_root
            quality_rules.RULES_PATH = original_rules_path

        fresh = json.loads((staging / 'events.json').read_text(encoding='utf-8'))
        cleaned = json.loads((staging / 'events_preview.json').read_text(encoding='utf-8'))
        quality_text, counts = event_quality.build_report(cleaned)
        reports = ROOT / 'reports'
        reports.mkdir(exist_ok=True)
        raw_output = ROOT / 'events_fresh_test.json'
        cleaned_output = ROOT / 'events_fresh_cleaned_test.json'
        quality_output = reports / f'fresh_quality_{stamp}.txt'
        application_output = reports / f'fresh_application_{stamp}.txt'
        shutil.copy2(staging / 'events.json', raw_output)
        shutil.copy2(staging / 'events_preview.json', cleaned_output)
        quality_output.write_text(quality_text, encoding='utf-8')
        application_reports = list((staging / 'reports').glob('preview_application_*.txt'))
        if len(application_reports) != 1:
            raise RuntimeError('Expected one preview application report in staging.')
        shutil.copy2(application_reports[0], application_output)

    print('\n-----------------------------------')
    print("HAPPENIN' — FRESH TEST COMPLETE")
    print('Fresh events after existing deduplication:', len(fresh))
    print('Cleaned events:', len(cleaned))
    print('Records removed by rules and decisions:', len(fresh) - len(cleaned))
    print('Quality checker counts:', counts)
    print('Fresh feed:', raw_output)
    print('Cleaned test feed:', cleaned_output)
    print('Application report:', application_output)
    print('Quality report:', quality_output)
    print('Published events.json unchanged by this test runner.')
    print('-----------------------------------')


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(f'\nFRESH TEST FAILED: {type(exc).__name__}: {exc}')
        raise SystemExit(1)
