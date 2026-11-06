"""Run one offline task; exit 2 means data/planning rejected, 1 means error."""
import argparse
import json
from pathlib import Path
from src.ais_single_task import PROJECT, run_task


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture', type=Path)
    parser.add_argument('--request', type=Path, default=PROJECT / 'config/ais-single-task.json')
    args = parser.parse_args()
    try:
        source = args.capture
        if source is None:
            bundle = json.loads((PROJECT / 'output/ais_replay/bundle.json').read_text(encoding='utf-8'))
            source = PROJECT / 'data/ais/captures' / bundle['capture_id']
        request = json.loads(args.request.read_text(encoding='utf-8-sig'))
        result = run_task(source, request)
    except (OSError, ValueError, KeyError) as error:
        result = {'status': 'error', 'failure_reason': str(error), 'trajectory': None, 'planner_invoked': False}
        print(json.dumps(result, ensure_ascii=True))
        print('Request was not submitted; no default result was published.')
        return 1
    print(json.dumps({key: result.get(key) for key in ['run_id', 'status', 'failure_reason', 'planner_invoked']}, ensure_ascii=False))
    check = result.get('data_check')
    if check:
        print(f"Observed vessels: {check['observed_vessels']}; qualified in window: {len(check['selected_vessels'])}; "
              f"longest contiguous: {check['longest_contiguous_seconds']:.3f}s; "
              f"minimum required: {check['required_seconds']:.3f}s; rule: {check['rule_version']}")
    if str(result.get('failure_reason') or '').startswith('result_publish_failed:'):
        print('Default publication did not complete; this command reports failure.')
        print('Publication diagnostic: ' + str(PROJECT / 'output/ais_single_task/runs' / result['run_id'] / 'publication_error.json'))
    else:
        print('Result: ' + str(PROJECT / 'output/ais_single_task/latest.json'))
    return 0 if result['status'] == 'planned' else 1 if result['status'] == 'error' else 2


if __name__ == '__main__':
    raise SystemExit(main())
