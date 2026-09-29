"""측정 TRANSIT 단순화(guards.transit_ik_preflight=false) 시험. 실기 검증 아님.

TRANSIT(MOVE)은 고정 Cartesian 목표를 그대로 직선 이동하고 애플리케이션 레벨 IK/FK 표본
검사를 하지 않는다. 아래 안전 기능은 이 설정과 무관하게 유지되는지 확인한다:
현장 간섭 검사, TCP/하중 대조, 접촉 구간 IK/FK, 실행 중 관절 범위·힘 한계·이동 시작·정지 확인.
"""
import json
from pathlib import Path

import pytest

from test_measurement_robot_adapter_mock import setup  # noqa: F401  (fixture)
from test_move_recovery_mock import run_case
from c2_process.measurement_robot_adapter import GuardedMeasurementAdapter
from c2_process.workpiece_calibration import MeasurementError, facing_pose

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def simple(setup):
    ad, io, ctx, c, step, clock = setup
    ad.transit_ik_preflight = False
    calls = dict(ik=0, fk=0)
    raw_ik, raw_fk = io.ik, io.fk

    def ik(*args):
        calls['ik'] += 1
        return raw_ik(*args)

    def fk(*args):
        calls['fk'] += 1
        return raw_fk(*args)

    io.ik, io.fk = ik, fk
    return ad, io, ctx, c, step, clock, calls


def probe_step():
    start = facing_pose([.426, 0.], .039, .2, 0.)
    end = start[:]
    end[0] -= .0055
    return dict(kind='PROBE', start_pose=start, target_pose=end, direction=[-1., 0., 0.], max_m=.0055,
                profile='side_touch', label='point_1_touch', point_index=1)


def test_deployed_real_config_selects_simple_transit():
    config = json.loads((ROOT / 'config/workpiece_real_trial_0921.json').read_text())
    assert config['guards']['transit_ik_preflight'] is False
    assert '실기 검증은 미수행' in config['transit_preflight_source']
    # 속도·허용오차·측정 각도는 이 변경과 함께 바꾸지 않는다.
    assert config['workcell']['angles_deg'] == [90., 135., 180., 225., 270., 315., 360., 405.]
    assert config['workcell']['pose_tolerance_m'] == .0003
    assert config['profiles']['travel']['speed_m_s'] == .06


def test_missing_key_keeps_full_check(setup):
    ad, io, ctx, c, step, clock = setup
    assert ad.transit_ik_preflight is True
    r = ad.preflight_measurement([step], c['workcell'], c['profiles'], ctx)
    assert r.observed_state['transit_ik_fk_checked'] is True
    assert r.observed_state['sample_count'] == 20
    assert r.observed_state['validation_level'] == 'SAMPLED_CONTROLLER_IK_FK_AND_EXTERNAL_SCENE_CHECK'


@pytest.mark.parametrize('value', [0, 1, 'false', None])
def test_setting_must_be_bool(setup, value):
    ad, io, ctx, c, step, clock = setup
    guards = dict(ad.g, transit_ik_preflight=value)
    with pytest.raises(ValueError, match='transit_ik_preflight'):
        GuardedMeasurementAdapter(io, ad.offset, guards, ad.readiness, ad.scene_check)


def test_transit_is_not_sampled_but_report_says_so(simple):
    ad, io, ctx, c, step, clock, calls = simple
    r = ad.preflight_measurement([step], c['workcell'], c['profiles'], ctx)
    assert r.ok and calls == dict(ik=0, fk=0)
    state = r.observed_state
    # all_segments_checked 는 구간 종류별로 정해진 검사를 통과했다는 뜻이고,
    # TRANSIT 의 IK/FK 수행 여부는 별도 필드로 밝힌다.
    assert state['all_segments_checked'] is True
    assert state['transit_ik_fk_checked'] is False and state['probe_ik_fk_checked'] is True
    assert state['transit_segments'] == 1 and state['probe_segments'] == 0
    assert state['sample_count'] == 0
    assert state['validation_level'] == 'SCENE_CHECK_WITH_PROBE_ONLY_IK_FK'
    assert state['full_continuous_collision_checked'] is False
    # 목표 자세 표현(회전 연속)은 그대로 계산한다.
    assert ad.native_targets[tuple(step['target_pose'])][5] == pytest.approx(190.)
    assert ad.expected[tuple(step['target_pose'])] is None
    assert io.moves == []


def test_scene_rejection_still_blocks_transit(simple):
    ad, io, ctx, c, step, clock, calls = simple
    ad.scene_check = lambda *a: dict(path_checked=False)
    with pytest.raises(MeasurementError, match='간섭 검사'):
        ad.preflight_measurement([step], c['workcell'], c['profiles'], ctx)
    assert not io.moves


def test_tcp_mismatch_still_blocks_transit(simple):
    ad, io, ctx, c, step, clock, calls = simple
    c['workcell']['tcp_id'] = 'another-tcp'
    with pytest.raises(MeasurementError, match='TCP'):
        ad.preflight_measurement([step], c['workcell'], c['profiles'], ctx)
    assert not io.moves


def test_unchecked_target_is_still_refused(simple):
    ad, io, ctx, c, step, clock, calls = simple
    with pytest.raises(MeasurementError, match='검사하지 않은'):
        ad.execute_measurement_step(step, c['profiles']['travel'], ctx, 10)
    assert not io.moves


def test_transit_reaches_target_by_cartesian_arrival(simple):
    ad, io, ctx, c, step, clock, calls = simple
    ad.preflight_measurement([step], c['workcell'], c['profiles'], ctx)
    r = ad.execute_measurement_step(step, c['profiles']['travel'], ctx, 10)
    assert r.ok and r.observed_state['stop_confirmed'] is True
    assert len(io.moves) == 1 and calls == dict(ik=0, fk=0)
    assert 'contact' not in r.observed_state


def test_hard_force_limit_still_stops_transit(simple):
    ad, io, ctx, c, step, clock, calls = simple
    ad.preflight_measurement([step], c['workcell'], c['profiles'], ctx)
    io.force = [100., 0., 0.]
    with pytest.raises(MeasurementError, match='힘 한계'):
        ad.execute_measurement_step(step, c['profiles']['travel'], ctx, 10)
    assert not io.moves


def test_runtime_joint_range_still_stops_transit(simple):
    ad, io, ctx, c, step, clock, calls = simple
    ad.preflight_measurement([step], c['workcell'], c['profiles'], ctx)
    io.q = [0., 200., 60., 0., 90., 0.]
    with pytest.raises(MeasurementError, match='관절 범위'):
        ad.execute_measurement_step(step, c['profiles']['travel'], ctx, 10)
    assert not io.moves


def test_motion_not_started_is_still_detected_without_resend(simple):
    ad, io, ctx, c, step, clock, calls = simple
    ad.preflight_measurement([step], c['workcell'], c['profiles'], ctx)
    io.start_delay = 10000
    with pytest.raises(MeasurementError, match='이동 시작 미확인'):
        ad.execute_measurement_step(step, c['profiles']['travel'], ctx, 10)
    assert len(io.moves) == 1


def test_probe_segment_is_still_checked_by_controller_ik_fk(simple):
    ad, io, ctx, c, step, clock, calls = simple
    probe = probe_step()
    approach = dict(kind='MOVE', target_pose=probe['start_pose'], profile='approach', label='point_1_approach')
    r = ad.preflight_measurement([approach, probe], c['workcell'], c['profiles'], ctx)
    assert r.ok and r.observed_state['sample_count'] > 0
    assert calls['ik'] == r.observed_state['sample_count'] + 1   # 접촉 구간 시작점의 관절 해 1회
    assert calls['fk'] == r.observed_state['sample_count']
    assert ad.expected[tuple(approach['target_pose'])] is None
    assert ad.expected[tuple(probe['target_pose'])] is not None


def test_probe_segment_joint_limit_is_rejected_before_motion(simple):
    ad, io, ctx, c, step, clock, calls = simple
    probe = probe_step()
    approach = dict(kind='MOVE', target_pose=probe['start_pose'], profile='approach', label='point_1_approach')
    io.ik = lambda *a: [0., 200., 60., 0., 90., 0.]
    with pytest.raises(MeasurementError, match='관절 범위'):
        ad.preflight_measurement([approach, probe], c['workcell'], c['profiles'], ctx)
    assert not io.moves


def with_transit_check(value):
    def edit(config):
        config['guards']['transit_ik_preflight'] = value
    return edit


def commands(logs):
    return [(d['step']['kind'], d['step']['label'], d['native_target'], d['profile']['speed_m_s'])
            for e, d in logs if e == 'command']


def test_whole_measurement_sends_identical_commands_in_both_modes():
    full, full_logs, _, _ = run_case(config_edit=with_transit_check(True))
    simple_, simple_logs, _, _ = run_case(config_edit=with_transit_check(False))
    assert full.ok and simple_.ok
    assert commands(full_logs) == commands(simple_logs)
    a, b = full.observed_state['measurement'], simple_.observed_state['measurement']
    for key in ('axis_xy_m', 'radius_m', 'top_z_m', 'bottom_z_m', 'residual_rms_m', 'residual_max_m'):
        assert a[key] == b[key]
    assert simple_.observed_state['home_return_confirmed'] is True
    assert [p['report']['transit_ik_fk_checked'] for p in simple_.observed_state['plans']] == [False] * 4
    assert [p['report']['transit_ik_fk_checked'] for p in full.observed_state['plans']] == [True] * 4


def test_simple_transit_samples_only_probe_segments():
    full, full_logs, _, _ = run_case(config_edit=with_transit_check(True))
    simple_, simple_logs, _, _ = run_case(config_edit=with_transit_check(False))
    count = lambda logs: len([1 for e, _ in logs if e == 'ik_sample'])
    labels = {d['label'] for e, d in simple_logs if e == 'ik_sample'}
    assert labels == {'top_touch'} | {f'point_{i}_touch' for i in range(1, 9)}
    assert 0 < count(simple_logs) < count(full_logs) * .15
