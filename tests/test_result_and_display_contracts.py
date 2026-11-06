"""Semantic success and frozen display regression tests; no source inputs change."""
from contextlib import redirect_stdout
from copy import deepcopy
from pathlib import Path
import importlib.util
import io
import json
import shutil
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.validation import validate_result
from src.release_checks import verify_workspace, workspace_geometry
from src.anylogic_workspace import catalog


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def load(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SuccessfulResultContracts(unittest.TestCase):
    def setUp(self):
        self.result = read(ROOT / 'output/ais_single_task/latest.json')

    def test_all_16_saved_results_remain_compatible(self):
        items = catalog()
        self.assertEqual(len(items), 16)
        for item in items:
            with self.subTest(key=item['key']):
                validate_result(read(ROOT / 'output' / item['file']))

    def test_each_success_flag_must_be_a_true_boolean(self):
        for field, key in [('planning', 'found'), ('planning', 'geometry_valid'),
                           ('ship_check', 'valid'), ('coverage_check', 'valid')]:
            for value in [False, None, 1, 'true']:
                with self.subTest(field=field, key=key, value=value):
                    result = deepcopy(self.result)
                    result[field][key] = value
                    with self.assertRaisesRegex(ValueError, field + '.' + key):
                        validate_result(result)
            result = deepcopy(self.result)
            result[field].pop(key)
            with self.assertRaises(ValueError):
                validate_result(result)

    def test_failure_reasons_and_planner_status_cannot_claim_success(self):
        for field, key in [(None, 'failure_reason'), ('planning', 'failure_reason'), ('ship_check', 'reason')]:
            result = deepcopy(self.result)
            (result[field] if field else result)[key] = 'failed'
            with self.assertRaises(ValueError):
                validate_result(result)
        result = deepcopy(self.result)
        result['planner_invoked'] = False
        with self.assertRaises(ValueError):
            validate_result(result)

    def test_invalid_distance_speed_and_timestamps_are_rejected(self):
        for field, value in [('distance_m', -1), ('distance_m', 0), ('distance_m', float('nan')),
                             ('distance_m', self.result['trajectory']['distance_m'] + 1),
                             ('speed_mps', 14), ('departure_s', -1), ('arrival_s', 0)]:
            with self.subTest(field=field, value=value):
                result = deepcopy(self.result)
                result['trajectory'][field] = value
                with self.assertRaises(ValueError):
                    validate_result(result)
        result = deepcopy(self.result)
        result['trajectory']['times_s'][-1] += 1
        with self.assertRaises(ValueError):
            validate_result(result)

    def test_projected_path_and_original_endpoints_must_match(self):
        result = deepcopy(self.result)
        result['trajectory']['xy'][0][0] += 1
        with self.assertRaises(ValueError):
            validate_result(result)
        result = deepcopy(self.result)
        result['request']['end'][0] += .001
        with self.assertRaisesRegex(ValueError, 'request.end'):
            validate_result(result)

    def test_projection_and_reference_profile_cannot_disagree(self):
        result = deepcopy(self.result)
        result['projection']['crs'] = 'EPSG:3857'
        with self.assertRaises(ValueError):
            validate_result(result)
        result = deepcopy(self.result)
        result['request']['buffer_m'] = 80
        with self.assertRaises(ValueError):
            validate_result(result)

    def test_recording_window_coverage_and_summary_must_agree(self):
        cases = [('window_start_unix_s', self.result['window_start_unix_s'] + 1),
                 ('window_end_unix_s', self.result['data_check']['window_end_unix_s'] + 1)]
        for field, value in cases:
            result = deepcopy(self.result)
            if field == 'window_start_unix_s':
                result[field] = value
            else:
                result['data_check'][field] = value
            with self.assertRaises(ValueError):
                validate_result(result)
        result = deepcopy(self.result)
        result['coverage_check']['actual_flight_seconds'] += 1
        with self.assertRaises(ValueError):
            validate_result(result)

    def test_clearance_claim_and_closest_time_must_be_consistent(self):
        for key, value in [('minimum_distance_m', 89.999), ('closest_time_s', -1)]:
            result = deepcopy(self.result)
            result['ship_check'][key] = value
            with self.assertRaises(ValueError):
                validate_result(result)

    def test_planning_duplicate_cannot_hide_a_different_result(self):
        result = deepcopy(self.result)
        result['planning']['trajectory']['distance_m'] += 1
        with self.assertRaisesRegex(ValueError, 'disagree'):
            validate_result(result)
        result = deepcopy(self.result)
        result['planning']['distance_m'] += 1
        with self.assertRaises(ValueError):
            validate_result(result)

    def test_unknown_positions_are_not_relabelled_as_a_failed_flight(self):
        result = deepcopy(self.result)
        result['ship_check'].update(minimum_distance_m=None, nearest_ship=None, closest_time_s=None)
        result['planning']['ship_check'] = deepcopy(result['ship_check'])
        validate_result(result)
        self.assertIsNone(result['ship_check']['minimum_distance_m'])

    def test_historical_unrun_entries_do_not_gain_a_fake_run_id(self):
        result = read(ROOT / 'output/ais_single_task/detour_verification/M2_result.json')
        validate_result(result)
        self.assertEqual(result['status'], 'not_tested')
        self.assertIsNone(result.get('run_id'))

    def test_malformed_saved_and_new_results_cannot_write_a_packet(self):
        import src.anylogic_workspace as work
        broken = deepcopy(self.result)
        broken['ship_check']['valid'] = False
        original_read = work.read
        latest = (ROOT / 'output/ais_single_task/latest.json').resolve()
        for run in [False, True]:
            with self.subTest(run=run), tempfile.TemporaryDirectory() as d:
                target = Path(d)
                with patch.object(work, 'read', side_effect=lambda p: broken if p.resolve() == latest else original_read(p)), \
                     patch.object(work, 'run_task', return_value=broken):
                    with self.assertRaisesRegex(ValueError, 'ship_check.valid'):
                        work.packet('current', target, run=run)
                self.assertFalse((target / 'packet.json').exists())
                self.assertFalse((target / 'result.json').exists())

    def test_inconsistent_new_planner_success_is_persisted_as_error(self):
        import src.ais_single_task as task
        request = deepcopy(self.result['request'])
        request.pop('research_points', None)
        planned = deepcopy(self.result['planning'])
        planned['geometry_valid'] = False
        fake = Mock()
        fake.timeline.horizon_s = self.result['data_check']['available_seconds']
        fake.plan_corridor.return_value = planned
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            shutil.copy2(ROOT / 'config.yaml', root / 'config.yaml')
            with patch.object(task, 'load_environment', return_value=({}, {})), \
                 patch.object(task, 'PlanarObservedPlanner', return_value=fake):
                result = task.run_task(ROOT / 'data/ais/captures' / self.result['capture_id'], request, root)
            fake.plan_corridor.assert_called_once()
            self.assertEqual(result['status'], 'error')
            self.assertIsNone(result['trajectory'])
            self.assertIn('geometry_valid', result['failure_reason'])
            self.assertEqual(read(root / 'output/ais_single_task/latest.json')['status'], 'error')

    def test_contradictory_latest_cannot_mark_bootstrap_complete(self):
        # Reuse the same real-byte archive fixture as the earlier recovery tests.
        from test_security_regressions import LatestRecovery
        fixture = LatestRecovery(); fixture.setUp()
        for field, key in [('planning', 'geometry_valid'), ('ship_check', 'valid'), ('coverage_check', 'valid')]:
            with self.subTest(field=field), tempfile.TemporaryDirectory() as d:
                root = Path(d)
                target, original = fixture.fixture(root)
                original[field][key] = False
                target.write_text(json.dumps(original), encoding='utf-8')
                with self.assertRaises(ValueError):
                    fixture.module.restore(root)
                self.assertFalse((root / '.local/data-bootstrap.json').exists())


class FrozenDisplayContracts(unittest.TestCase):
    def setUp(self):
        self.workspace = read(ROOT / 'anylogic/workbench/workspace.json')

    def test_original_geometry_is_preserved(self):
        result = verify_workspace(ROOT)
        self.assertEqual(result['frozen_sites_and_anchors_checked'], 8)
        self.assertTrue(result['fixed_region_bounds_verified'])

    def test_site_anchor_source_and_labels_cannot_drift(self):
        for field in ['xy', 'anchor_xy', 'point', 'anchor', 'offset_m', 'task', 'role']:
            with self.subTest(field=field):
                workspace = deepcopy(self.workspace)
                site = workspace['sites'][0]
                if field in ('xy', 'anchor_xy'): site[field][0] += 1000
                elif field == 'point': site[field][0] += 1e-8
                elif field == 'anchor': site[field]['lat'] += 1e-8
                elif field == 'offset_m': site[field] += 1
                else: site[field] = 'wrong'
                with self.assertRaises(ValueError):
                    verify_workspace(ROOT, workspace)

    def test_missing_duplicate_or_reordered_sites_are_rejected(self):
        for change in ['missing', 'duplicate', 'reordered']:
            workspace = deepcopy(self.workspace)
            if change == 'missing': workspace['sites'].pop()
            elif change == 'duplicate': workspace['sites'][1] = deepcopy(workspace['sites'][0])
            else: workspace['sites'].reverse()
            with self.subTest(change=change), self.assertRaises(ValueError):
                verify_workspace(ROOT, workspace)

    def test_zero_shifted_inverted_nonfinite_bounds_are_rejected(self):
        cases = [[0, 0, 0, 0], [1, 0, 1, 0], [0, 1, 0, float('nan')], [True, 1, 0, 1], [0, 1]]
        shifted = self.workspace['bounds'][:]; shifted[0] += 100
        for bounds in cases + [shifted]:
            workspace = deepcopy(self.workspace); workspace['bounds'] = bounds
            with self.subTest(bounds=bounds), self.assertRaises(ValueError):
                verify_workspace(ROOT, workspace)

    def test_changed_frozen_source_cannot_validate_a_matching_bad_display(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            names = ['runtime/data/current-data.manifest.json', 'output/research_points/study/study.json', 'config.yaml']
            names += ['output/research_points/study/M' + str(i) + '/selection.json' for i in range(1, 5)]
            for name in names:
                target = root / name; target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(ROOT / name, target)
            study = root / 'output/research_points/study/study.json'
            changed = read(study); changed['tasks'][0]['gates'][0]['point'][0] += .001
            study.write_text(json.dumps(changed), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'Frozen display input identity mismatch'):
                workspace_geometry(root, read(ROOT / 'output/ais_single_task/latest.json')['projection'])

    def test_bad_display_is_rejected_before_bridge_output(self):
        import src.anylogic_workspace as work
        original = work.read
        path = (ROOT / 'anylogic/workbench/workspace.json').resolve()
        for field in ['sites', 'bounds']:
            workspace = deepcopy(self.workspace)
            if field == 'sites': workspace['sites'][0]['xy'][0] += 1000
            else: workspace['bounds'] = [0, 0, 0, 0]
            with self.subTest(field=field), tempfile.TemporaryDirectory() as d, \
                 patch.object(work, 'read', side_effect=lambda p: workspace if p.resolve() == path else original(p)):
                with self.assertRaises(ValueError): work.packet('M2', Path(d))
                self.assertFalse((Path(d) / 'packet.json').exists())

    def test_full_project_check_detects_the_previously_missed_site_shift(self):
        verifier = load('verify_display_contract', 'scripts/verify_project.py')
        original = verifier.read
        workspace = deepcopy(self.workspace); workspace['sites'][0]['xy'][0] += 1000
        path = (ROOT / 'anylogic/workbench/workspace.json').resolve()
        with patch.object(verifier, 'read', side_effect=lambda p: workspace if p.resolve() == path else original(p)), \
             redirect_stdout(io.StringIO()):
            report = verifier.verify(ROOT, [])
        self.assertFalse(report['passed'])
        checks = {row['name']: row for row in report['checks']}
        self.assertTrue(checks['published_files_identity']['passed'])
        self.assertIn('sites', checks['capture_and_raw_AIS_identity']['error'])


if __name__ == '__main__':
    unittest.main()
