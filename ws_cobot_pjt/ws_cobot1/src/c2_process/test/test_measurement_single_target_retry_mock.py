"""측정 이동 복구의 단일 목표 재시도와 TRANSIT/PROBE 분리 시험. 실기 검증 아님.

- 이동 오차 복구는 실패한 목표 한 구간만 다시 검사하고 남은 계획 전체 preflight 를 반복하지 않는다.
- 기준 힘(baseline)은 PROBE 에서만 확보하고 TRANSIT(MOVE)에서는 호출하지 않는다.
- 감지 기준·힘 한계·정지 확인은 바꾸지 않는다.
"""
import pytest

from test_workpiece_guarded_flow_mock import KinematicIO, SimulatedGuardedAdapter
from test_move_recovery_mock import TARGET_LABEL, run_case


@pytest.fixture
def counters(monkeypatch):
    """계획 preflight·단일 목표 재검사·기준 힘·제어기 IK/FK 호출을 센다."""
    count = dict(preflight=[], recheck=[], baseline=[], ik=0, fk=0)
    raw_preflight = SimulatedGuardedAdapter.preflight_measurement
    raw_recheck = SimulatedGuardedAdapter.recheck_measurement_target
    raw_baseline = SimulatedGuardedAdapter._probe_stationary_baseline
    raw_ik, raw_fk = KinematicIO.ik, KinematicIO.fk

    def preflight(self, steps, *args):
        count['preflight'].append(len(steps))
        return raw_preflight(self, steps, *args)

    def recheck(self, step, *args):
        count['recheck'].append(step['label'])
        return raw_recheck(self, step, *args)

    def baseline(self, step, *args):
        count['baseline'].append((step['kind'], step['label']))
        return raw_baseline(self, step, *args)

    def ik(self, *args):
        count['ik'] += 1
        return raw_ik(self, *args)

    def fk(self, *args):
        count['fk'] += 1
        return raw_fk(self, *args)

    monkeypatch.setattr(SimulatedGuardedAdapter, 'preflight_measurement', preflight)
    monkeypatch.setattr(SimulatedGuardedAdapter, 'recheck_measurement_target', recheck)
    monkeypatch.setattr(SimulatedGuardedAdapter, '_probe_stationary_baseline', baseline)
    monkeypatch.setattr(KinematicIO, 'ik', ik)
    monkeypatch.setattr(KinematicIO, 'fk', fk)
    return count


def test_transit_never_collects_force_baseline(counters):
    r, _, attempts, _ = run_case()
    assert r.ok, (r.error_code, r.message)
    assert attempts['point_1_approach'] == 1
    # 기준 힘은 윗면 1회 + 옆면 8회의 PROBE 에서만 확보한다.
    assert {kind for kind, _ in counters['baseline']} == {'PROBE'}
    assert [label for _, label in counters['baseline']] == (
        ['top_touch'] + [f'point_{i}_touch' for i in range(1, 9)])


def test_probe_collects_baseline_then_records_contact(counters):
    r, logs, _, _ = run_case()
    assert r.ok
    points = r.observed_state['measurement']['points']
    assert [p['point_index'] for p in points] == list(range(1, 9))
    assert all(p['detected'] is True and len(p['tip_pose']) == 7 for p in points)
    events = [e for e, _ in logs]
    assert events.count('stationary_baseline') == 9


def test_transit_error_retries_only_that_target(counters):
    clean, _, _, _ = run_case()
    plans = list(counters['preflight'])
    counters['preflight'].clear()
    r, _, attempts, _ = run_case(offset_mm=.6)
    assert r.ok, (r.error_code, r.message)
    assert attempts[TARGET_LABEL] == 2
    # 계획 단위 preflight 는 복구가 없을 때와 같다. 남은 경로 전체를 다시 검사하지 않는다.
    assert counters['preflight'] == plans
    assert len(r.observed_state['plans']) == len(clean.observed_state['plans']) == 4
    assert counters['recheck'] == [TARGET_LABEL]
    assert [x['label'] for x in r.observed_state['target_rechecks']] == [TARGET_LABEL]
    # 다른 점의 접근은 한 번씩만 실행됐다.
    assert all(attempts[f'point_{i}_approach'] == 1 for i in (1, 3, 4, 5, 6, 7, 8))


def test_retry_limit_fails_without_unbounded_recursion(counters):
    r, _, attempts, config = run_case(offset_mm=.6, forever=True)
    limit = config['workcell']['move_recovery_max_attempts']
    assert r.outcome == 'FAILED' and r.error_code == 'RECOVERY_REQUIRED'
    assert attempts[TARGET_LABEL] == limit
    assert counters['recheck'] == [TARGET_LABEL] * (limit - 1)
    assert r.observed_state['stop_confirmed'] is True
    # 실패한 목표 뒤의 점은 시작하지 않는다.
    assert 'point_3_approach' not in attempts


def test_motion_incomplete_also_retries_single_target(counters):
    run_case()
    plans = list(counters['preflight'])
    counters['preflight'].clear()
    r, _, attempts, _ = run_case(post_move_drift_mm=.6)
    assert r.ok, (r.error_code, r.message)
    assert attempts[TARGET_LABEL] == 2
    assert counters['preflight'] == plans
    assert counters['recheck'] == [TARGET_LABEL]


def full_transit_check(config):
    config['guards']['transit_ik_preflight'] = True


def test_recovery_adds_only_one_segment_of_controller_ik_fk(counters):
    """TRANSIT 도 IK/FK 로 검사하는 설정에서는 복구 때 한 구간 분량만 늘어난다."""
    run_case(config_edit=full_transit_check)
    clean_ik, clean_fk = counters['ik'], counters['fk']
    counters['ik'] = counters['fk'] = 0
    r, _, _, _ = run_case(offset_mm=.6, config_edit=full_transit_check)
    assert r.ok
    extra_ik, extra_fk = counters['ik'] - clean_ik, counters['fk'] - clean_fk
    # 옆면 48구간 전체 분량과 비교해 충분히 작아야 한다.
    assert 0 < extra_ik < clean_ik * .1, (extra_ik, clean_ik)
    assert 0 < extra_fk < clean_fk * .1, (extra_fk, clean_fk)
    assert r.observed_state['target_rechecks'][0]['report']['transit_ik_fk_checked'] is True


def test_simple_transit_recovery_adds_no_controller_ik_fk(counters):
    """배포 설정(TRANSIT 단순 이동)에서는 복구 재검사가 현장 간섭 검사만 한다."""
    run_case()
    clean_ik, clean_fk = counters['ik'], counters['fk']
    counters['ik'] = counters['fk'] = 0
    r, _, attempts, _ = run_case(offset_mm=.6)
    assert r.ok and attempts[TARGET_LABEL] == 2
    assert (counters['ik'], counters['fk']) == (clean_ik, clean_fk)
    report = r.observed_state['target_rechecks'][0]['report']
    assert report['validation_level'] == 'SINGLE_TARGET_RECHECK_SCENE_ONLY'
    assert report['transit_ik_fk_checked'] is False and report['probe_envelopes_checked'] is True


def test_recheck_rejects_a_target_that_was_never_prechecked():
    from c2_process.workpiece_calibration import MeasurementError
    ad = SimulatedGuardedAdapter.__new__(SimulatedGuardedAdapter)
    ad.expected, ad.native_targets = {}, {}
    step = dict(kind='MOVE', label='orbit', target_pose=[.4, 0., .3, 0., 1., 0., 0.], profile='travel')
    with pytest.raises(MeasurementError, match='사전 검사하지 않은 목표'):
        ad.recheck_measurement_target(step, {}, {}, None)
