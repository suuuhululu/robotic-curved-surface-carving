# joint_check.py — 전체 경로의 IK·관절 한계·J6 누적 회전 검사. 최초 구현: 이시율. 담당: 김세은 (2026-09-20).
# 팀 규칙(INTERFACE_RECOMMENDATION 13절): 각도 범위·이음매는 c2_path 검증, "현재 관절·IK·전체 경로 J6 한계/여유" 는 공정 준비에서 확인.
# 상태 기계(PRECHECK)가 부른다. 로봇을 움직이지 않는다. 어댑터의 inverse_kinematics(제어기 ikin) 만 쓴다.
#   r = check_path_joints(path, adapter, tool_offset_m, ref_joints_rad, limits_deg=None, j6_margin_deg=10)
#   r.ok → 통과. 실패: FAILED/VALIDATION_FAILED (한계 초과·J6 여유 부족) 또는 FAILED/NOT_READY (IK 불가·어댑터 없음).
#   observed_state: joints_min_deg, joints_max_deg, j6_start/end/min/max, j6_total_rotation_deg, checked_waypoints, worst(segment_id, joint, value)
import hashlib
import json
import math
import time
from dataclasses import dataclass, field
from typing import Dict, List, Mapping, Optional

from .robot_adapter import RobotAdapter, StepResult

# M0609 관절 범위 [deg] (두산 사양. 현장 안전 설정이 더 좁으면 limits_deg 로 넘긴다)
DEFAULT_LIMITS_DEG = [(-360.0, 360.0), (-95.0, 95.0), (-135.0, 135.0), (-360.0, 360.0), (-135.0, 135.0), (-360.0, 360.0)]


@dataclass
class JointPathEvaluation:
    """한 번의 순차 IK 결과. 공정 내부에서만 재사용하고 ROS 결과에는 관절열을 싣지 않는다."""

    result: StepResult
    joints_deg: List[List[float]] = field(default_factory=list)
    start_joints_deg: List[float] = field(default_factory=list)
    inverse_kinematics_calls: int = 0
    elapsed_s: float = 0.0

    @property
    def final_joints_deg(self):
        if self.joints_deg:
            return list(self.joints_deg[-1])
        return list(self.start_joints_deg) if self.start_joints_deg else None


def _unwrap(prev_deg: float, cur_deg: float) -> float:
    """ikin 이 ±180 로 접어 준 J6 를 이전 값과 이어지게 펼친다 (연속 경로에서 360° 점프 방지)."""
    # fmod는 반복 없이 처리하며 기존의 +180/-180 방향을 보존한다.
    delta = cur_deg - prev_deg
    if not all(math.isfinite(v) for v in (prev_deg, cur_deg, delta)):
        raise ValueError("J6 각도는 유한한 숫자여야 함")
    delta = math.fmod(delta, 360.0)
    if delta > 180.0:
        delta -= 360.0
    elif delta < -180.0:
        delta += 360.0
    return prev_deg + delta


def _finite_joints(values):
    """문자열·bool·누락·NaN/무한대는 관절 측정값으로 인정하지 않는다."""
    try:
        return (isinstance(values, (list, tuple)) and len(values) == 6
                and all(isinstance(v, (int, float)) and not isinstance(v, bool)
                        and math.isfinite(v) for v in values))
    except (TypeError, ValueError, OverflowError):
        return False


def evaluate_path_joints(path: Dict, adapter: RobotAdapter,
                         tool_offset_m: Optional[List[float]],
                         ref_joints_rad: List[float], limits_deg: Optional[List] = None,
                         j6_margin_deg: float = 10.0, cancel=None) -> JointPathEvaluation:
    """경로를 한 번 순회하며 판정과 이후 검사에서 재사용할 관절열을 함께 만든다."""
    started = time.monotonic()
    trajectory = []
    ik_calls = 0

    def done(result, start=None):
        elapsed = max(0.0, time.monotonic() - started)
        return JointPathEvaluation(result, trajectory,
                                   list(start) if start is not None else [],
                                   ik_calls, elapsed)

    limits = DEFAULT_LIMITS_DEG if limits_deg is None else limits_deg
    if (not isinstance(limits, (list, tuple)) or len(limits) != 6
            or any(not isinstance(pair, (list, tuple)) or len(pair) != 2
                   or any(type(v) not in (int, float) or not math.isfinite(v) for v in pair)
                   or pair[0] >= pair[1] for pair in limits)
            or type(j6_margin_deg) not in (int, float) or not math.isfinite(j6_margin_deg)
            or j6_margin_deg < 0 or 2*j6_margin_deg >= limits[5][1]-limits[5][0]):
        return done(StepResult("FAILED", "NOT_READY", "관절 한계/여유 형식 오류", "joint_check"))
    if not hasattr(adapter, "inverse_kinematics"):
        return done(StepResult("FAILED", "NOT_READY", "어댑터에 inverse_kinematics 없음", "joint_check"))
    if not _finite_joints(ref_joints_rad):
        return done(StepResult("UNKNOWN", "VALIDATION_UNAVAILABLE", "현재 관절값은 유한한 숫자 6개여야 함", "joint_check"))
    ref = [math.degrees(v) for v in ref_joints_rad]
    if not _finite_joints(ref):
        return done(StepResult("UNKNOWN", "VALIDATION_UNAVAILABLE", "현재 관절값의 도 단위 변환 불가", "joint_check"))
    start_ref = list(ref)
    jmin = list(ref); jmax = list(ref)
    j6_start = ref[5]; j6_prev = ref[5]; j6_min = j6_max = ref[5]
    worst = None; n_checked = 0
    segments = path.get("segments")
    if not isinstance(segments, list) or not segments:
        return done(StepResult("FAILED", "INVALID_INPUT", "검사할 경로 구간 없음 또는 형식 오류", "joint_check",
                               dict(checked_waypoints=0)), start_ref)
    for seg in segments:
        wps = seg.get("waypoints") or []
        if not wps:
            return done(StepResult("FAILED", "INVALID_INPUT", "검사할 waypoint가 없는 구간", "joint_check",
                                   dict(segment_id=seg.get("segment_id"), checked_waypoints=n_checked)), start_ref)
        # CUT을 포함한 모든 명시 waypoint를 순서대로 검사한다.
        # 표면 경로 또는 실행기가 만든 계획을 검사한다. 점 사이 보간·충돌 보장은 아니다.
        for i, waypoint in enumerate(wps):
            detail = dict(segment_id=seg.get("segment_id"), index=i, checked_waypoints=n_checked,
                          inspection_scope=path.get("inspection_scope", "SURFACE_PATH"))
            if path.get("inspection_scope"):
                detail.update(inspection_scope=path["inspection_scope"], stroke_id=seg.get("stroke_id"),
                              movement_kind=seg.get("movement_kind"), applied_offset_m=seg.get("applied_offset_m"),
                              applied_depth_m=seg.get("applied_depth_m"))
            if cancel is not None and cancel.is_set():
                return done(StepResult("STOPPED", "NONE", "IK 검사 취소", "joint_check", detail), start_ref)
            ik_calls += 1
            q = adapter.inverse_kinematics(waypoint, tool_offset_m, ref)
            if cancel is not None and cancel.is_set():
                return done(StepResult("STOPPED", "NONE", "IK 검사 중 취소", "joint_check", detail), start_ref)
            if q is None:
                return done(StepResult("FAILED", "NOT_READY", f"IK 실패: segment {seg.get('segment_id')} 점 {i}", "joint_check",
                                       detail), start_ref)
            if not _finite_joints(q):
                return done(StepResult("UNKNOWN", "VALIDATION_UNAVAILABLE", "IK 관절값은 유한한 숫자 6개여야 함", "joint_check",
                                       detail), start_ref)
            q = list(q)
            try:
                q[5] = _unwrap(j6_prev, q[5])
            except ValueError:
                return done(StepResult("UNKNOWN", "VALIDATION_UNAVAILABLE", "IK J6 각도 전개 불가", "joint_check",
                                       detail), start_ref)
            for k in range(6):
                jmin[k] = min(jmin[k], q[k]); jmax[k] = max(jmax[k], q[k])
                lo, hi = limits[k]
                margin = j6_margin_deg if k == 5 else 0.0
                if q[k] < lo + margin or q[k] > hi - margin:
                    if worst is None or abs(q[k]) > abs(worst["value_deg"]):
                        worst = dict(detail, joint=k + 1, value_deg=q[k], limits_deg=[lo, hi], margin_deg=margin,
                                     remaining_margin_deg=min(q[k]-lo-margin, hi-margin-q[k]))
            j6_prev = q[5]; j6_min = min(j6_min, q[5]); j6_max = max(j6_max, q[5])
            ref = q
            trajectory.append(list(q))
            n_checked += 1
    obs = dict(inspection_scope=path.get("inspection_scope", "SURFACE_PATH"), joints_min_deg=[round(v, 1) for v in jmin], joints_max_deg=[round(v, 1) for v in jmax],
               j6_start_deg=round(j6_start, 1), j6_end_deg=round(j6_prev, 1), j6_min_deg=round(j6_min, 1), j6_max_deg=round(j6_max, 1),
               j6_total_rotation_deg=round(j6_max - j6_min, 1), checked_waypoints=n_checked, worst=worst)
    if worst is not None:
        return done(StepResult("FAILED", "VALIDATION_FAILED",
                               f"관절 한계/여유 초과: J{worst['joint']} {worst['value_deg']:.0f}° (segment {worst['segment_id']})", "joint_check", obs),
                    start_ref)
    return done(StepResult("SUCCEEDED", "NONE", f"{n_checked} 점 IK 통과, J6 {j6_min:.0f}~{j6_max:.0f}°", "joint_check", obs),
                start_ref)


def check_path_joints(path: Dict, adapter: RobotAdapter,
                      tool_offset_m: Optional[List[float]], ref_joints_rad: List[float],
                      limits_deg: Optional[List] = None, j6_margin_deg: float = 10.0,
                      cancel=None) -> StepResult:
    """기존 공개 계약을 유지하는 wrapper."""
    return evaluate_path_joints(
        path, adapter, tool_offset_m, ref_joints_rad,
        limits_deg=limits_deg, j6_margin_deg=j6_margin_deg, cancel=cancel).result


def candidate_diagnostic_window(path: Dict, observed_state: Mapping,
                                radius: int = 5):
    """관절/IK 실패점 앞뒤의 제한된 진단 경로와 전체 경로 시작 index를 만든다."""
    if not isinstance(path, dict) or not isinstance(observed_state, Mapping):
        return None
    detail = observed_state.get("worst")
    if not isinstance(detail, Mapping):
        detail = observed_state
    segment_id, index = detail.get("segment_id"), detail.get("index")
    if not isinstance(segment_id, str) or type(index) is not int or index < 0:
        return None
    segments = path.get("segments")
    if not isinstance(segments, list) or type(radius) is not int or radius < 0:
        return None
    global_offset = 0
    for segment in segments:
        waypoints = segment.get("waypoints") or []
        if segment.get("segment_id") != segment_id:
            global_offset += len(waypoints)
            continue
        if index >= len(waypoints):
            return None
        start, end = max(0, index - radius), min(len(waypoints), index + radius + 1)
        scoped_segment = dict(segment)
        scoped_segment["waypoints"] = [list(point) for point in waypoints[start:end]]
        scoped = dict(path)
        scoped["inspection_scope"] = "IK_CANDIDATE_FAILURE_WINDOW"
        scoped["segments"] = [scoped_segment]
        metadata = dict(segment_id=segment_id, failure_index=index,
                        window_start_index=start, window_end_index=end - 1,
                        waypoint_count=end - start,
                        global_start_index=global_offset + start)
        return scoped, global_offset + start, metadata
    return None


def diagnose_path_joint_candidates(path: Dict, adapter: RobotAdapter,
                                    tool_offset_m: Optional[List[float]],
                                    ref_joints_rad: List[float], limits_deg: List,
                                    j6_margin_deg: float = 0.0, cancel=None,
                                    joint_constraints: Optional[Mapping] = None) -> Dict:
    """전체 명시 waypoint의 다중 IK 후보열을 계산하는 읽기 전용 진단.

    선택 결과는 Cartesian 실행 승인에 사용하지 않는다. 각 waypoint의 유효 후보를
    연결해 solution-space 전환 수, 관절 이동량, J6 잔여 여유 순으로 비교한다.
    """
    started = time.monotonic()
    constraints = dict(joint_constraints or {})
    constraint_names = ("min_j3_abs_deg", "min_j5_margin_deg",
                        "max_joint_step_deg")
    base = dict(mode="DIAGNOSTIC_ONLY", used_for_execution_approval=False,
                cartesian_solution_space_verified=False, queried_waypoints=0,
                candidate_query_calls=0, service_error_waypoints=0,
                incomplete_query=False,
                joint_constraints_applied={
                    key: constraints.get(key) for key in constraint_names
                    if key in constraints})
    query = getattr(adapter, "inverse_kinematics_candidates", None)
    if not callable(query):
        return dict(base, status="UNAVAILABLE", reason="CANDIDATE_API_UNAVAILABLE",
                    elapsed_s=max(0.0, time.monotonic() - started))
    if (not _finite_joints(ref_joints_rad) or not isinstance(limits_deg, (list, tuple))
            or len(limits_deg) != 6
            or any(not isinstance(pair, (list, tuple)) or len(pair) != 2
                   or any(type(v) not in (int, float) or not math.isfinite(v) for v in pair)
                   or pair[0] >= pair[1] for pair in limits_deg)
            or type(j6_margin_deg) not in (int, float)
            or not math.isfinite(j6_margin_deg) or j6_margin_deg < 0
            or any(type(constraints.get(key)) not in (int, float)
                   or not math.isfinite(constraints[key]) or constraints[key] <= 0
                   for key in constraint_names if key in constraints)):
        return dict(base, status="INVALID_INPUT", reason="INVALID_LIMIT_OR_REFERENCE",
                    elapsed_s=max(0.0, time.monotonic() - started))
    ref = [math.degrees(v) for v in ref_joints_rad]
    # score: space 전환 최소 → 전체 관절 이동 최소 → J6 최소 여유 최대.
    states = [dict(q=ref, space=None, switches=0, total_motion=0.0,
                   max_step=0.0, min_j6_margin=float("inf"), j6_min=ref[5],
                   j6_max=ref[5], min_j3_abs=float("inf"),
                   min_j5_margin=float("inf"), runs=[], hasher=hashlib.sha256())]
    checked = 0
    service_error_waypoints = 0
    segments = path.get("segments") if isinstance(path, dict) else None
    if not isinstance(segments, list) or not segments:
        return dict(base, status="INVALID_INPUT", reason="EMPTY_PATH",
                    elapsed_s=max(0.0, time.monotonic() - started))
    for segment in segments:
        waypoints = segment.get("waypoints") or []
        if not waypoints:
            return dict(base, status="INVALID_INPUT", reason="EMPTY_SEGMENT",
                        failure_waypoint=dict(segment_id=segment.get("segment_id"), index=0),
                        elapsed_s=max(0.0, time.monotonic() - started))
        for index, waypoint in enumerate(waypoints):
            if cancel is not None and cancel.is_set():
                return dict(base, status="CANCELED", reason="CANCEL_REQUESTED",
                            queried_waypoints=checked, candidate_query_calls=checked,
                            service_error_waypoints=service_error_waypoints,
                            elapsed_s=max(0.0, time.monotonic() - started))
            reference = min(states, key=lambda state: (
                state["switches"], state["total_motion"], -state["min_j6_margin"]))["q"]
            report = query(waypoint, tool_offset_m, reference, cancel=cancel)
            checked += 1
            if not isinstance(report, dict):
                report = dict(status="SERVICE_ERROR", candidates=[],
                              service_error_spaces=list(range(8)))
            query_status = report.get("status", "SERVICE_ERROR")
            if query_status == "CANCELED":
                return dict(base, status="CANCELED", reason="CANCEL_REQUESTED",
                            queried_waypoints=checked, candidate_query_calls=checked,
                            service_error_waypoints=service_error_waypoints,
                            elapsed_s=max(0.0, time.monotonic() - started))
            if query_status in {"SERVICE_ERROR", "PARTIAL"}:
                service_error_waypoints += 1
            candidates = report.get("candidates")
            if not isinstance(candidates, list):
                candidates = []
            next_states = {}
            rejected = 0
            for candidate in candidates:
                q_raw = candidate.get("joints_deg") if isinstance(candidate, dict) else None
                space = candidate.get("solution_space") if isinstance(candidate, dict) else None
                if not _finite_joints(q_raw) or type(space) is not int or not 0 <= space < 8:
                    rejected += 1
                    continue
                for previous in states:
                    q = list(q_raw)
                    try:
                        q[5] = _unwrap(previous["q"][5], q[5])
                    except ValueError:
                        rejected += 1
                        continue
                    valid = True
                    for joint, (lo, hi) in enumerate(limits_deg):
                        margin = j6_margin_deg if joint == 5 else 0.0
                        if q[joint] < lo + margin or q[joint] > hi - margin:
                            valid = False
                            break
                    if not valid:
                        rejected += 1
                        continue
                    delta = [abs(q[j] - previous["q"][j]) for j in range(6)]
                    j3_abs = abs(q[2])
                    j5_margin = min(abs(q[4]), abs(180.0 - abs(q[4])))
                    if (("min_j3_abs_deg" in constraints
                            and j3_abs < constraints["min_j3_abs_deg"])
                            or ("min_j5_margin_deg" in constraints
                                and j5_margin < constraints["min_j5_margin_deg"])
                            or ("max_joint_step_deg" in constraints
                                and max(delta) > constraints["max_joint_step_deg"])):
                        rejected += 1
                        continue
                    remaining = min(q[5] - limits_deg[5][0] - j6_margin_deg,
                                    limits_deg[5][1] - j6_margin_deg - q[5])
                    switched = previous["space"] is not None and previous["space"] != space
                    runs = list(previous["runs"])
                    if not runs or runs[-1] != space:
                        runs.append(space)
                    digest = previous["hasher"].copy()
                    digest.update(json.dumps(
                        [segment.get("segment_id"), index, space,
                         [round(v, 8) for v in q]], separators=(",", ":"),
                        ensure_ascii=True).encode())
                    state = dict(q=q, space=space,
                                 switches=previous["switches"] + int(switched),
                                 total_motion=previous["total_motion"] + sum(delta),
                                 max_step=max(previous["max_step"], max(delta)),
                                 min_j6_margin=min(previous["min_j6_margin"], remaining),
                                 j6_min=min(previous["j6_min"], q[5]),
                                 j6_max=max(previous["j6_max"], q[5]),
                                 min_j3_abs=min(previous["min_j3_abs"], j3_abs),
                                 min_j5_margin=min(previous["min_j5_margin"], j5_margin),
                                 runs=runs, hasher=digest)
                    key = (space, round(q[5], 6))
                    score = (state["switches"], state["total_motion"],
                             -state["min_j6_margin"])
                    old = next_states.get(key)
                    if old is None or score < old[0]:
                        next_states[key] = (score, state)
            if not next_states:
                uncertain = query_status in {"SERVICE_ERROR", "PARTIAL"}
                return dict(base,
                            status="INCOMPLETE" if uncertain else "NO_SAFE_SEQUENCE",
                            reason=("SERVICE_ERROR_WITHOUT_SAFE_CANDIDATE" if uncertain
                                    else "NO_LIMIT_COMPLIANT_CANDIDATE"),
                            queried_waypoints=checked, candidate_query_calls=checked,
                            service_error_waypoints=service_error_waypoints,
                            incomplete_query=uncertain,
                            failure_waypoint=dict(
                                segment_id=segment.get("segment_id"), index=index,
                                checked_waypoints=checked - 1,
                                query_status=query_status,
                                candidate_count=len(candidates),
                                rejected_candidate_transitions=rejected,
                                service_error_spaces=report.get("service_error_spaces", []),
                                no_solution_spaces=report.get("no_solution_spaces", [])),
                            elapsed_s=max(0.0, time.monotonic() - started))
            states = [item[1] for item in next_states.values()]
    selected = min(states, key=lambda state: (
        state["switches"], state["total_motion"], -state["min_j6_margin"]))
    runs = selected["runs"]
    return dict(base, status="PARTIAL" if service_error_waypoints else "SUCCEEDED",
                queried_waypoints=checked,
                candidate_query_calls=checked,
                service_error_waypoints=service_error_waypoints,
                incomplete_query=service_error_waypoints > 0,
                selected_solution_spaces=runs[:32],
                selected_solution_spaces_truncated=len(runs) > 32,
                solution_space_switches=selected["switches"],
                j6_min_deg=round(selected["j6_min"], 3),
                j6_max_deg=round(selected["j6_max"], 3),
                minimum_j6_remaining_deg=round(selected["min_j6_margin"], 3),
                minimum_j3_abs_deg=round(selected["min_j3_abs"], 3),
                minimum_j5_margin_deg=round(selected["min_j5_margin"], 3),
                max_joint_step_deg=round(selected["max_step"], 3),
                total_joint_motion_deg=round(selected["total_motion"], 3),
                sequence_sha256=selected["hasher"].hexdigest(),
                failure_waypoint=None,
                elapsed_s=max(0.0, time.monotonic() - started))
