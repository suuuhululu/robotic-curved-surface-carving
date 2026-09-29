# 전체 경로 IK·J6 검사 모의 시험
import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from c2_process.robot_adapter import MockRobotAdapter, matrix_to_quat  # noqa: E402
from c2_process.joint_check import (candidate_diagnostic_window, check_path_joints,
                                    diagnose_path_joint_candidates)  # noqa: E402


def upright(yaw_deg):
    """툴 Z 아래, 툴 Y 가 base yaw 방향"""
    t = math.radians(yaw_deg)
    x = [-math.cos(t), -math.sin(t), 0.0]; y = [-math.sin(t), math.cos(t), 0.0]; z = [0.0, 0.0, -1.0]
    return matrix_to_quat([[x[0], y[0], z[0]], [x[1], y[1], z[1]], [x[2], y[2], z[2]]])


def arc_path(yaw_from, yaw_to, n=40):
    wps = [[0.4, 0.0, 0.2, *upright(yaw_from + (yaw_to - yaw_from) * i / (n - 1))] for i in range(n)]
    return dict(schema_version=2, segments=[dict(segment_id="s1", stroke_id="st1", kind="CUT", waypoints=wps, motion_profile_id="cut")])


REF = [0.0, 0.0, math.radians(90), 0.0, math.radians(90), 0.0]


def test_pass_within_limits():
    ad = MockRobotAdapter()
    r = check_path_joints(arc_path(90, -60), ad, None, REF)
    assert r.ok, r
    assert r.observed_state["j6_total_rotation_deg"] > 100 and r.observed_state["checked_waypoints"] >= 10


def test_fail_when_j6_exceeds_margin():
    ad = MockRobotAdapter(); ad.ik_j6_offset = 300.0                  # 시작 J6 가 이미 300° 근처
    ref = list(REF); ref[5] = math.radians(300.0)                      # 현재 J6 = 300 → 첫 점은 가까운 해(390)로 이어짐
    r = check_path_joints(arc_path(90, 160), ad, None, ref)          # +70° 더 돌면 370 > 350
    assert r.outcome == "FAILED" and r.error_code == "VALIDATION_FAILED", r
    assert r.observed_state["worst"]["joint"] == 6


def test_j6_approved_boundary_is_inclusive():
    class BoundaryIK:
        def inverse_kinematics(self, pose, offset, ref):
            return [0.0, 0.0, 0.0, 0.0, 0.0, 345.0]

    limits = [list(pair) for pair in [(-360, 360), (-95, 95), (-135, 135),
                                      (-360, 360), (-135, 135), (-345, 345)]]
    result = check_path_joints(arc_path(0, 0, n=2), BoundaryIK(), None,
                               [0.0] * 5 + [math.radians(340.0)],
                               limits_deg=limits, j6_margin_deg=0.0)

    assert result.ok
    assert result.observed_state["j6_max_deg"] == 345.0


def test_j6_overrun_reports_limits_point_and_remaining_margin():
    path = arc_path(0, 0, n=2)
    points = path["segments"][0]["waypoints"]

    class OverrunIK:
        def inverse_kinematics(self, pose, offset, ref):
            return [0.0, 0.0, 0.0, 0.0, 0.0, 344.0 if pose is points[0] else 346.0]

    limits = [list(pair) for pair in [(-360, 360), (-95, 95), (-135, 135),
                                      (-360, 360), (-135, 135), (-345, 345)]]
    result = check_path_joints(path, OverrunIK(), None,
                               [0.0] * 5 + [math.radians(340.0)],
                               limits_deg=limits, j6_margin_deg=0.0)

    assert (result.outcome, result.error_code) == ("FAILED", "VALIDATION_FAILED")
    assert result.observed_state["j6_min_deg"] == 340.0
    assert result.observed_state["j6_max_deg"] == 346.0
    assert result.observed_state["worst"] == {
        "segment_id": "s1", "index": 1, "checked_waypoints": 1,
        "inspection_scope": "SURFACE_PATH", "joint": 6, "value_deg": 346.0,
        "limits_deg": [-345, 345], "margin_deg": 0.0,
        "remaining_margin_deg": -1.0,
    }


def test_candidate_diagnostic_selects_limit_compliant_alternative_without_approval():
    class Candidates:
        def inverse_kinematics_candidates(self, pose, offset, ref, cancel=None):
            values = []
            for space, j6 in ((0, 174.0), (1, 160.0)):
                q = [0.0] * 5 + [j6]
                delta = [abs(q[i] - ref[i]) for i in range(6)]
                values.append(dict(solution_space=space, joints_deg=q,
                                   joint_delta_deg=delta,
                                   max_joint_delta_deg=max(delta),
                                   total_joint_delta_deg=sum(delta)))
            return dict(status="SUCCEEDED", candidates=values,
                        service_error_spaces=[], no_solution_spaces=list(range(2, 8)))

    limits = [[-360, 360], [-95, 95], [-135, 135], [-360, 360],
              [-135, 135], [-170, 170]]
    report = diagnose_path_joint_candidates(
        arc_path(0, 0, n=3), Candidates(), None,
        [0.0] * 5 + [math.radians(160.0)], limits, 0.0)

    assert report['status'] == 'SUCCEEDED'
    assert report['selected_solution_spaces'] == [1]
    assert report['solution_space_switches'] == 0
    assert report['j6_min_deg'] == report['j6_max_deg'] == 160.0
    assert report['minimum_j6_remaining_deg'] == 10.0
    assert report['used_for_execution_approval'] is False
    assert report['cartesian_solution_space_verified'] is False
    assert len(report['sequence_sha256']) == 64


def test_candidate_diagnostic_keeps_service_failure_distinct_from_no_solution():
    class Unavailable:
        def inverse_kinematics_candidates(self, pose, offset, ref, cancel=None):
            return dict(status="SERVICE_ERROR", candidates=[],
                        service_error_spaces=list(range(8)), no_solution_spaces=[])

    limits = [[-360, 360], [-95, 95], [-135, 135], [-360, 360],
              [-135, 135], [-345, 345]]
    report = diagnose_path_joint_candidates(
        arc_path(0, 0, n=2), Unavailable(), None, REF, limits, 0.0)

    assert report['status'] == 'INCOMPLETE'
    assert report['reason'] == 'SERVICE_ERROR_WITHOUT_SAFE_CANDIDATE'
    assert report['failure_waypoint']['query_status'] == 'SERVICE_ERROR'
    assert report['failure_waypoint']['service_error_spaces'] == list(range(8))


def test_candidate_diagnostic_window_limits_query_to_failure_neighborhood():
    path = arc_path(0, 0, n=20)
    scoped, global_start, metadata = candidate_diagnostic_window(
        path, {'worst': {'segment_id': 's1', 'index': 12}}, radius=3)

    assert global_start == 9
    assert len(scoped['segments'][0]['waypoints']) == 7
    assert scoped['inspection_scope'] == 'IK_CANDIDATE_FAILURE_WINDOW'
    assert metadata == {
        'segment_id': 's1', 'failure_index': 12,
        'window_start_index': 9, 'window_end_index': 15,
        'waypoint_count': 7, 'global_start_index': 9,
    }


def test_unwrap_keeps_continuity_across_180():
    ad = MockRobotAdapter()
    ref = list(REF); ref[5] = math.radians(-100.0)                     # 모의 IK: J6 = yaw+90 → 170° 에서 -100
    r = check_path_joints(arc_path(170, 190), ad, None, ref)          # atan2 가 ±180 에서 접히는 구간
    assert r.ok and r.observed_state["j6_total_rotation_deg"] < 25, r


def test_ik_failure_reported():
    ad = MockRobotAdapter(); ad.ik_fail_at_call = 3
    r = check_path_joints(arc_path(0, 30), ad, None, REF)
    assert r.outcome == "FAILED" and r.error_code == "NOT_READY" and "IK" in r.message


import pytest
from c2_process.joint_check import _unwrap


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -float("inf"), None, "20", True])
@pytest.mark.parametrize("joint", [0, 4, 5])
def test_invalid_ik_result_blocks_following_checks(bad, joint):
    class InvalidIK:
        calls = 0
        def inverse_kinematics(self, pose, offset, ref):
            self.calls += 1
            result = [0.0] * 6
            result[joint] = bad
            return result
    adapter = InvalidIK()
    result = check_path_joints(arc_path(0, 30), adapter, None, REF)
    assert (result.outcome, result.error_code) == ("UNKNOWN", "VALIDATION_UNAVAILABLE")
    assert adapter.calls == 1
    assert result.observed_state == {"segment_id": "s1", "index": 0, "checked_waypoints": 0, "inspection_scope": "SURFACE_PATH"}


@pytest.mark.parametrize("values", [[], [0]*5, [0]*7, "000000", [0, 0, 0, 0, 0, float("nan")]])
def test_invalid_reference_does_not_call_ik(values):
    adapter = MockRobotAdapter()
    adapter.inverse_kinematics = lambda *args: pytest.fail("invalid reference must not reach IK")
    assert check_path_joints(arc_path(0, 30), adapter, None, values).outcome == "UNKNOWN"


@pytest.mark.parametrize("values", [[], [0]*5, [0]*7, 3, "000000"])
def test_invalid_ik_shape(values):
    adapter = MockRobotAdapter()
    adapter.inverse_kinematics = lambda *args: values
    assert check_path_joints(arc_path(0, 30), adapter, None, REF).outcome == "UNKNOWN"


@pytest.mark.parametrize("previous,current,expected", [
    (0, 370, 10), (170, -170, 190), (-170, 170, -190),
    (0, 180, 180), (0, -180, -180), (0, 540, 180), (0, -540, -180),
    (300, 30, 390),
])
def test_unwrap_preserves_direction(previous, current, expected):
    assert _unwrap(previous, current) == expected


def test_unwrap_extreme_values_terminate_in_subprocess():
    # 무한 반복이 재발해도 시험 전체가 멈추지 않도록 별도 프로세스에 제한을 둔다.
    import subprocess
    code = """
from c2_process.joint_check import _unwrap
import math
for value in [float('nan'), float('inf'), -float('inf')]:
    try:
        _unwrap(0, value)
    except ValueError:
        pass
    else:
        raise AssertionError('invalid angle accepted')
assert abs(_unwrap(0, 1e300)) <= 180
assert abs(_unwrap(0, -1e300)) <= 180
try:
    _unwrap(-1e308, 1e308)
except ValueError:
    pass
else:
    raise AssertionError('overflow accepted')
"""
    env = dict(os.environ, PYTHONPATH=os.path.dirname(os.path.dirname(__file__)))
    subprocess.run([sys.executable, "-c", code], env=env, check=True, timeout=5)


@pytest.mark.parametrize('bad_index', [1, 2, 3])
@pytest.mark.parametrize('failure', ['ik', 'j5', 'j6'])
def test_cut_previously_skipped_points_are_rejected(bad_index, failure):
    path = arc_path(0, 0, n=6)
    points = path['segments'][0]['waypoints']
    for i, point in enumerate(points): point[0] = .4 + i * .001
    class Adapter:
        def inverse_kinematics(self, pose, offset, ref):
            i = points.index(pose)
            if i == bad_index and failure == 'ik': return None
            return [0, 0, 0, 0, 175 if i == bad_index and failure == 'j5' else 0,
                    355 if i == bad_index and failure == 'j6' else 340]
    result = check_path_joints(path, Adapter(), None, [0, 0, 0, 0, 0, math.radians(340)])
    assert result.outcome == 'FAILED'
    if failure == 'ik':
        assert result.error_code == 'NOT_READY'
        assert result.observed_state['index'] == bad_index
        assert result.observed_state['checked_waypoints'] == bad_index
    else:
        assert result.error_code == 'VALIDATION_FAILED'
        assert result.observed_state['worst']['index'] == bad_index
        assert result.observed_state['worst']['joint'] == (5 if failure == 'j5' else 6)


def test_all_segment_waypoints_are_checked_in_order_with_previous_solution():
    path = {'segments': []}
    for kind, count in [('APPROACH', 2), ('CUT', 6), ('TRAVEL', 2), ('CUT', 3), ('RETRACT', 1)]:
        path['segments'].append({'kind': kind, 'waypoints': [[len(path['segments']), i, 0, 0, 0, 0, 1]
                                                          for i in range(count)]})
    points = [p for s in path['segments'] for p in s['waypoints']]
    class Adapter:
        calls = []
        def inverse_kinematics(self, pose, offset, ref):
            assert ref == [0, 0, 0, 0, 0, len(self.calls)]
            self.calls.append(pose)
            return [0, 0, 0, 0, 0, len(self.calls)]
    adapter = Adapter()
    result = check_path_joints(path, adapter, None, [0]*6)
    assert result.ok and adapter.calls == points
    assert result.observed_state['checked_waypoints'] == len(points)


@pytest.mark.parametrize('kind', ['CUT', 'TRAVEL'])
def test_empty_segment_is_not_silently_skipped(kind):
    adapter = MockRobotAdapter()
    result = check_path_joints({'segments': [{'kind': kind, 'waypoints': []}]}, adapter, None, REF)
    assert (result.outcome, result.error_code) == ('FAILED', 'INVALID_INPUT')
    assert adapter.calls == []


def test_empty_path_does_not_report_zero_point_ik_success():
    adapter = MockRobotAdapter()
    result = check_path_joints({'segments': []}, adapter, None, REF)
    assert (result.outcome, result.error_code) == ('FAILED', 'INVALID_INPUT')
    assert result.observed_state['checked_waypoints'] == 0
    assert adapter.calls == []


def test_joint_checker_still_accepts_non_cut_motion_for_reuse():
    adapter = MockRobotAdapter()
    path = arc_path(0, 5, n=2)
    path['segments'][0]['kind'] = 'TRAVEL'
    result = check_path_joints(path, adapter, None, REF)
    assert result.ok and result.observed_state['checked_waypoints'] == 2
