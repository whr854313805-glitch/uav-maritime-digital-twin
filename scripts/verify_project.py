"""Verify the F23 offline AIS project with its installed/bundled Python.

Default: inspect saved files and hashes only; no solver, UI or network access.
Optional --recompute creates NEW run files through the original run_task with
publish=False. It never replaces latest.json or a saved catalog result.

There are 16 saved entries: 10 permit recalculation; 6 are view-only (three
not-tested detour requests and three historical grid comparisons). These are
not 16 independent experiments. Historical results are not new SST evidence.
This script does not verify the AnyLogic UI or establish global optimality.
"""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import sys
import time

EXPECTED_RECALCULABLE = {
    'M1', 'M2', 'M3', 'M4', 'current', 'detour_M1',
    'encounter_M1_start_conflict', 'encounter_M1_opposing',
    'encounter_M1_same_direction', 'encounter_M1_singleton',
}
EXPECTED_VIEW_ONLY = {'detour_M2', 'detour_M3', 'detour_M4', 'grid_100', 'grid_200', 'grid_400'}
EXPECTED_DEMOS = {
    'M2': 'straight', 'M4': 'building',
    'encounter_M1_same_direction': 'same_direction',
    'encounter_M1_opposing': 'opposing',
    'encounter_M1_start_conflict': 'rejection',
    'encounter_M1_singleton': 'singleton',
}


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def within(root, relative):
    path = (root / relative).resolve()
    require(path.is_relative_to(root), 'Referenced path is outside this project: ' + str(relative))
    return path


def locate(explicit):
    if explicit is not None:
        return explicit.resolve()
    for path in Path(__file__).resolve().parents:
        if (path / 'src/anylogic_workspace.py').is_file() and (path / 'config.yaml').is_file():
            return path
    raise ValueError('Project root not found. Pass --project PATH.')


def verify(project, recompute):
    started = time.monotonic()
    report = {
        'schema_version': 1, 'created_at_utc': datetime.now(timezone.utc).isoformat(),
        'project': str(project), 'python': str(Path(sys.executable).resolve()),
        'mode': 'saved_files_and_optional_original_solver' if recompute else 'saved_files_only_no_recompute',
        'checks': [], 'recomputations': [],
        'scope': 'Offline historical AIS, original observed-segment rules and fixed research points.',
        'limits': [
            'No AnyLogic UI verification is performed by this script.',
            'No real-flight safety, future-ship prediction or global-optimality claim.',
            '16 catalog entries are not 16 independent experiments.',
            'Historical grid results and not-tested entries are not new SST verification.',
        ],
    }
    state = {}

    def check(name, callback):
        tick = time.monotonic()
        try:
            detail = callback()
            report['checks'].append({'name': name, 'passed': True, 'detail': detail,
                                     'seconds': round(time.monotonic() - tick, 3)})
            print('PASS ' + name)
            return True
        except Exception as error:
            report['checks'].append({'name': name, 'passed': False,
                                     'error': type(error).__name__ + ': ' + str(error),
                                     'seconds': round(time.monotonic() - tick, 3)})
            print('FAIL ' + name + ': ' + str(error))
            return False

    def published_identity():
        sys.path.insert(0,str(project))
        from src.release_checks import verify_release
        return verify_release(project)

    def necessary_files():
        required = [
            'config.yaml', 'config/ais-single-task.json', 'config/parameter-sources.json',
            'ais_anylogic_bridge.py', 'start_full_demo.py', 'presentation_controls.py',
            'src/anylogic_workspace.py', 'src/ais_single_task.py', 'src/ais_data.py',
            'src/ais_replay.py', 'src/ais_segments.py', 'src/temporal_planning.py',
            'src/ompl_sst.py', 'src/safe_planning.py', 'src/metric_projection.py',
            'src/project_config.py', 'src/flight_simulation.py',
            'select_research_points.py', 'verify_ais_encounters.py',
            'anylogic/AIS_Visual_Demo.alp', 'anylogic/native-visual-demo.jar',
            'anylogic/ctrl_wheel.js', 'anylogic/harbour_background.png',
            'anylogic/workbench/workspace.json', 'anylogic/workbench/provenance.json',
            'anylogic/visual_demo/support.json', 'anylogic/visual_demo/scenery.json',
            'output/ais_single_task/latest.json', 'output/ais_single_task/ompl_sst/catalog.json',
            'output/research_points/study/study.json',
            'output/ais_replay/buildings_display.geojson', 'output/ais_replay/buildings_display_source.json',
            'runtime/ompl/manifest.json', 'runtime/ompl/settings.json', 'runtime/ompl/OMPL-LICENSE',
            'runtime/ompl/sst_probe.cpp',
        ]
        missing = [rel for rel in required if not within(project, rel).is_file()]
        require(not missing, 'Missing necessary files: ' + ', '.join(missing))
        return {'file_count': len(required)}

    def dependencies():
        sys.path.insert(0, str(project))
        # Reuse original project adapters; importing these does not run planning.
        from src.anylogic_workspace import catalog
        from src.ais_replay import build_capture
        from src.ais_single_task import apply_reference_profile, load_environment, run_task
        from src.project_config import load_config
        from playwright.sync_api import sync_playwright
        from PIL import Image
        state.update(catalog_function=catalog, build_capture=build_capture,
                     apply_reference_profile=apply_reference_profile, load_environment=load_environment,
                     run_task=run_task, load_config=load_config)
        return {'original_project_modules_imported': True, 'Pillow_imported': True,
                'Playwright_imported': True, 'solver_invoked': False}

    def saved_catalog():
        items = state['catalog_function']()
        require({r['key'] for r in items} == EXPECTED_RECALCULABLE | EXPECTED_VIEW_ONLY,
                'Expected all 16 saved catalog entries.')
        require({r['key'] for r in items if r['can_run']} == EXPECTED_RECALCULABLE,
                'The 10 recalculable / 6 view-only entry split changed.')
        workspace = read(project / 'anylogic/workbench/workspace.json')
        indexed = {r['key']: r for r in workspace['catalog']}
        require(set(indexed) == {r['key'] for r in items}, 'Workspace catalog keys differ from the current catalog.')
        results = {}
        protected = {project / 'output/ais_single_task/latest.json'}
        for item in items:
            path = within(project, 'output/' + item['file'])
            result = read(path)
            require(sha(path) == item['sha256'], 'Saved result hash mismatch: ' + item['key'])
            old = indexed[item['key']]
            require(all(old.get(k) == item.get(k) for k in ['file', 'sha256', 'can_run']),
                    'Workspace is stale for ' + item['key'])
            require(result['request'] == item['request'], 'Saved request mismatch: ' + item['key'])
            results[item['key']] = result
            protected.add(path)
            if item.get('baseline_file'):
                protected.add(within(project, 'output/' + item['baseline_file']))
        state.update(items=items, results=results, workspace=workspace, protected=protected)
        return {'saved_entries': 16, 'recalculable': sorted(EXPECTED_RECALCULABLE),
                'view_only': sorted(EXPECTED_VIEW_ONLY),
                'original_catalog_baseline_and_override_checks_passed': True}

    def demo_results():
        support = read(project / 'anylogic/visual_demo/support.json')
        demos = support['demo_results']
        require(len(demos) == 6, 'Expected six demonstration bindings.')
        require({entry['key']: entry['kind'] for entry in demos.values()} == EXPECTED_DEMOS,
                'Six demonstration keys/kinds differ.')
        items = {r['key']: r for r in state['items']}
        for run_id, entry in demos.items():
            saved = state['results'][entry['key']]
            require(saved['run_id'] == run_id, 'Demonstration run identity mismatch: ' + entry['key'])
            require(entry['result_sha256'] == items[entry['key']]['sha256'],
                    'Demonstration result hash mismatch: ' + entry['key'])
        state['support'] = support
        return {'saved_demonstrations': 6, 'bindings_match_current_saved_results': True}

    def raw_capture():
        workspace = state['workspace']
        capture_id = workspace['source']['capture_id']
        source = within(project, 'data/ais/captures/' + capture_id)
        manifest = read(source / 'capture.json')
        require(manifest['status'] == 'captured', 'Current capture has not completed.')
        require(not manifest.get('test_fixture_not_real_data'), 'A protocol fixture is not a real AIS capture.')
        bundle = state['build_capture'](source)
        require(bundle['capture_id'] == capture_id, 'Raw capture identity mismatch.')
        expected = sha(source / 'messages.jsonl')
        require(expected == workspace['source']['raw_sha256'] == bundle['raw_sha256'], 'Workspace raw AIS hash mismatch.')
        require(expected == state['support']['raw_sha256'], 'Demonstration support raw AIS hash mismatch.')
        manifest_hash = sha(source / 'capture.json')
        for key, result in state['results'].items():
            require(result['capture_id'] == capture_id and result['raw_sha256'] == expected,
                    'Saved result has a different AIS source: ' + key)
            if result.get('capture_manifest_sha256'):
                require(result['capture_manifest_sha256'] == manifest_hash, 'Capture manifest hash mismatch: ' + key)
        study = read(project / 'output/research_points/study/study.json')
        require(study['capture_id'] == capture_id and study['raw_ais_sha256'] == expected,
                'Frozen study uses a different AIS source.')
        from src.release_checks import verify_workspace
        verify_workspace(project, workspace)
        state.update(source=source, bundle=bundle, raw_sha256=expected)
        return {'capture_id': capture_id, 'raw_sha256': expected,
                'valid_positions': bundle['valid_position_count'], 'vessels': bundle['vessel_count'],
                'original_capture_parser_and_hash_checks_passed': True}

    def selections():
        seen = set()
        for key, result in state['results'].items():
            request = result['request']
            ref = request.get('research_points')
            if not ref:
                continue
            path = within(project, ref['selection_file'])
            require(sha(path) == ref['selection_sha256'], 'Frozen selection hash mismatch: ' + key)
            selection = read(path)
            require(selection['status'] == 'selected' and selection['gates'] == ref['gates'],
                    'Frozen research-point gates changed: ' + key)
            require([g['point'] for g in selection['gates']] == [request['start'], request['end']],
                    'Task endpoints differ from frozen selection: ' + key)
            state['protected'].add(path)
            seen.add(ref['selection_file'])
        require(seen, 'No frozen research-point selection was verified.')
        return {'selection_files': sorted(seen), 'endpoints_unchanged': True}

    def official_buildings():
        request = read(project / 'config/ais-single-task.json')
        config = state['apply_reference_profile'](state['load_config'](project / 'config.yaml'), request)
        # Original method checks the exact derived buildings file and every original
        # buildings_*.geojson page in the preserved official manifest.
        inputs, provenance = state['load_environment'](project, config)
        display = project / 'output/ais_replay/buildings_display.geojson'
        require(sha(display) == state['workspace']['source']['background_source_sha256'],
                'Official display footprint hash mismatch.')
        require(sha(display) == state['support']['building_source_sha256'],
                'Demonstration support building source mismatch.')
        scenery = read(project / 'anylogic/visual_demo/scenery.json')
        require(scenery.get('display_only') is True, 'Scenery is not marked display-only.')
        require(scenery['provenance']['buildings_sha256'] == provenance['buildings_sha256'],
                'Scenery references different official buildings.')
        require(config['planning']['building_buffer_m'] == 30, 'Reference building clearance changed.')
        state.update(config=config, inputs=inputs)
        return {'building_count': provenance['building_count'],
                'buildings_sha256': provenance['buildings_sha256'],
                'original_load_environment_hash_checks_passed': True,
                'display_only_scenery': True}

    def official_sst():
        runtime = project / 'runtime/ompl'
        manifest = read(runtime / 'manifest.json')
        require(manifest['library'] == 'OMPL' and manifest['version'] == '2.0.2', 'OMPL version differs.')
        require(manifest['commit'] == '1ae6ac0bf7e9cb67d8994a8b8742833f813fdd39', 'OMPL pinned commit differs.')
        require(manifest.get('upstream_search_unmodified') is True, 'OMPL manifest no longer declares unmodified upstream search.')
        required = {'sst_worker.exe', 'libgcc_s_seh-1.dll', 'libstdc++-6.dll', 'libwinpthread-1.dll'}
        require(set(manifest['runtime_sha256']) == required, 'OMPL runtime manifest has unexpected members.')
        for name, expected in manifest['runtime_sha256'].items():
            require(sha(within(runtime, name)) == expected, 'OMPL runtime hash mismatch: ' + name)
        require(sha(runtime / 'sst_probe.cpp') == manifest['adapter_source_sha256'], 'OMPL adapter source hash mismatch.')
        settings = read(runtime / 'settings.json')
        require(settings.get('default') and isinstance(settings.get('fixed_requests'), list), 'OMPL settings are incomplete.')
        return {'version': manifest['version'], 'declared_upstream_commit': manifest['commit'],
                'runtime_files_verified': sorted(required), 'adapter_source_hash_verified': True,
                'solver_invoked': False}

    def independent_recomputed_result(key):
        from select_research_points import StaticSiteChecker
        from src.safe_planning import validate_path
        from verify_ais_encounters import raw_oracle
        item = next(q for q in state['items'] if q['key'] == key)
        require(item['can_run'], 'This entry is view-only: ' + key)
        request = deepcopy(item['request'])
        before = {str(p.relative_to(project)): sha(p) for p in state['protected']}
        result = state['run_task'](state['source'], request, project, publish=False)
        after = {str(p.relative_to(project)): sha(p) for p in state['protected']}
        require(before == after, 'A saved result/latest/selection changed during optional recomputation.')
        summary = {'key': key, 'run_id': result.get('run_id'), 'status': result['status'],
                   'failure_reason': result.get('failure_reason'), 'publish': False,
                   'saved_results_unchanged': True,
                   'new_run_directory': 'output/ais_single_task/runs/' + result['run_id']}
        report['recomputations'].append(summary)
        require(result['status'] == 'planned', 'Original solver did not produce a valid route: ' + str(result.get('failure_reason')))
        require(result['request'] == request and result['raw_sha256'] == state['raw_sha256'], 'Recomputed request/source mismatch.')
        require(result['ship_check']['valid'] and result['coverage_check']['valid']
                and result['planning']['geometry_valid'], 'Original hard-constraint checks did not pass.')
        search = result['planning']['search']
        require(search['algorithm'] == 'OMPL 2.0.2 control::SST'
                and search['custom_search_or_shortening_used'] is False, 'Unexpected planner/fallback identity.')
        tr = result['trajectory']
        config = state['apply_reference_profile'](state['load_config'](project / 'config.yaml'), request)
        checker = StaticSiteChecker(config, state['inputs'])
        geom = validate_path(tr['path'], request['start'], request['end'], [], request['buffer_m'],
                             config, state['inputs']['buildings']['buildings'], checker)
        require(geom['geometry_valid'], 'Independent original GEOS building/bounds/endpoints check failed.')
        rows = []
        origin = result['window_start_unix_s']
        for vessel in state['bundle']['vessels']:
            for segment in vessel['segments']:
                pairs = zip(segment, segment[1:]) if len(segment) > 1 else [(segment[0], segment[0])]
                for a, b in pairs:
                    rows.append((vessel['mmsi'], a['timestamp_unix_s'] - origin, b['timestamp_unix_s'] - origin,
                                 checker.project([a['latitude'], a['longitude']]),
                                 checker.project([b['latitude'], b['longitude']])))
        ships = raw_oracle(tr, rows)
        distance = ships['minimum_distance_m']
        require(distance is None or distance >= request['buffer_m'] - config['planning']['clearance_tolerance_m'],
                'Independent original raw-AIS continuous-distance check failed.')
        require(len(tr['xy']) == len(tr['times_s']) and len(tr['xy']) >= 2, 'Invalid trajectory cardinality.')
        intervals = list(zip(tr['xy'], tr['xy'][1:], tr['times_s'], tr['times_s'][1:]))
        require(all(tb > ta for _, _, ta, tb in intervals), 'Non-increasing trajectory timestamps.')
        speed_error = max(abs(math.dist(a, b) / (tb - ta) - request['speed_mps']) for a, b, ta, tb in intervals)
        require(speed_error <= 1e-6, 'Recomputed physical speed differs from the fixed request.')
        summary.update(geometry_check=geom, raw_AIS_continuous_check=ships,
                       maximum_speed_error_mps=speed_error, search_method=search['method'],
                       algorithm=search['algorithm'], distance_m=tr['distance_m'])
        return summary

    check('published_files_identity', published_identity)
    check('necessary_files', necessary_files)
    if check('installed_dependencies', dependencies):
        if check('all_16_saved_catalog_entries', saved_catalog):
            check('six_saved_demonstration_bindings', demo_results)
            check('capture_and_raw_AIS_identity', raw_capture)
            check('frozen_research_point_selections', selections)
            check('official_buildings_and_original_raw_files', official_buildings)
        check('pinned_OMPL_runtime', official_sst)
    baseline_passed = all(row['passed'] for row in report['checks'])
    if recompute and baseline_passed:
        for key in recompute:
            check('optional_original_solver_recompute_' + key, lambda key=key: independent_recomputed_result(key))
    elif recompute:
        report['recompute_skipped'] = 'Saved-file verification failed; no solver was started.'
    report['passed'] = all(row['passed'] for row in report['checks'])
    report['elapsed_seconds'] = round(time.monotonic() - started, 3)
    return report


def main():
    # A successful check must not become a failure when an English Windows
    # redirected console cannot encode the Unicode project path.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8', errors='backslashreplace')
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--project', type=Path, help='Project root; otherwise locate relative to this script.')
    parser.add_argument('--recompute', action='append', nargs='+', choices=['M2', 'encounter_M1_opposing'],
                        help='Optional original-solver computation; may repeat this option. Default does not replan.')
    args = parser.parse_args()
    try:
        project = locate(args.project)
        recompute = list(dict.fromkeys(key for group in (args.recompute or []) for key in group))
        report = verify(project, recompute)
        output = project / '.local/verification.json'
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
        print(('VERIFIED' if report['passed'] else 'VERIFICATION FAILED') + ': ' + str(output))
        return 0 if report['passed'] else 1
    except Exception as error:
        print('VERIFICATION ERROR: ' + type(error).__name__ + ': ' + str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
