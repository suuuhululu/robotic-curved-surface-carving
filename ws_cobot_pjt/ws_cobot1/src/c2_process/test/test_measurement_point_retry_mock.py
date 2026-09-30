"""점 재취득의 가짜 I/O 시험. ROS/실기 도달성·충돌 시험은 아님."""
from collections import Counter
from copy import deepcopy
import json
from pathlib import Path
import pytest
from test_workpiece_guarded_flow_mock import Clock, KinematicIO, SimulatedGuardedAdapter
from c2_process.workpiece_calibration import (MeasurementContext, measure_workpiece,
                                             MeasurementError, PointMeasurementError, fit_circle)
from c2_process.robot_adapter import StepResult, posx_to_pose, pose_to_posx
from c2_process.workpiece_real_trial import check_trial_scene


def trial(scenario, *, before_search=False):
    cfg=json.loads((Path(__file__).resolve().parents[1]/'config/workpiece_real_trial_0921.json').read_text())
    w=cfg['workcell'];w['source_mode']='SIMULATION'
    if not before_search:
        # 기존 접촉 창의 호환성 시험. 새 모드는 별도 전체 흐름 시험으로 검증한다.
        w.pop('side_search_m',None);w.pop('side_baseline_lead_in_m',None)
        w.update(start_gap_m=.008,inside_limit_m=.0035,slow_retract_gap_m=.005)
    clock=Clock();io=KinematicIO(w,clock,True)
    io.center=w['seed_axis_xy_m'][:];io.radius=w['seed_radius_m']
    nominal_radius=io.radius
    if scenario in ('shifted_outlier','shifted_persistent_outlier'):
        # 실제 실패의 정상 7점 원을 모형의 표면으로 사용한다. 실제 힘/IK 재현은 아님.
        points=json.loads((Path(__file__).parent/'fixtures/workpiece_fit_failure_20260929.json').read_text())['points_m']
        fit=fit_circle(points[:5]+points[6:])
        io.center=fit['axis_xy_m'];nominal_radius=fit['radius_m']
    ctx=MeasurementContext('retry','prep','SIMULATION',monotonic=clock)
    attempts=Counter();steps=[];events=[];traces=[];active=None;read_no=0
    def ready(c):return dict(ownership_confirmed=True,control_authority=True,measurement_id=c.measurement_id,checked_at_monotonic_s=clock())
    ad=SimulatedGuardedAdapter(io,w['tool_offset_m'],cfg['guards'],ready,check_trial_scene,clock=clock,sleep=clock.sleep)
    ad.trace=lambda e,d:traces.append((e,deepcopy(d)))
    raw_exec=ad.execute_measurement_step;raw_read=io.read;raw_stop=ad.stop_measurement
    raw_ik=io.ik
    def execute(step,*args):
        nonlocal active
        active=step;steps.append((step['label'],deepcopy(step)))
        if step['kind']=='PROBE':
            index=step['point_index'];attempts[index]+=1
            io.radius=nominal_radius
            if scenario in ('shifted_outlier','shifted_persistent_outlier') and index==6 and (attempts[index]==1 or scenario=='shifted_persistent_outlier'):
                io.radius-=.002285
            if scenario in ('outlier','persistent_outlier') and index==4 and (attempts[index]==1 or scenario=='persistent_outlier'):
                io.radius+=.0015
            if scenario in ('early','early_repeat','retract_failure') and index==2 and (attempts[index]==1 or scenario=='early_repeat'):
                io.radius+=.0042  # baseline 확보 뒤 허용 접촉 구간보다 앞에서 접촉
            if scenario=='late' and index==2 and attempts[index]==1:
                io.radius-=.004
            if index==2:
                if scenario=='communication':raise ConnectionError('응답 미확인')
                if scenario=='tcp':raise MeasurementError('PROFILE_MISMATCH','TCP 변경')
                if scenario=='authority':raise MeasurementError('NOT_READY','제어권 상실')
                if scenario=='timeout':raise TimeoutError('응답 기한 초과')
        if scenario=='retract_failure' and step['label']=='point_2_retract':
            raise MeasurementError('FORCE_LIMIT','후퇴 중 힘 한계')
        try:
            return raw_exec(step,*args)
        except PointMeasurementError as exc:
            if scenario=='baseline_unknown':
                exc.probe_command_sent=None  # 무이동 증거가 없는 다른 백엔드의 호환 동작
            raise
    def read():
        nonlocal read_no
        result=raw_read();read_no+=1
        if active and active.get('point_index')==2:
            unstable=scenario in ('baseline','baseline_noop_ik','baseline_unknown','baseline_shift',
                                 'baseline_lateral','baseline_repeat','stop_unknown','cancel') and (attempts[2]==1 or scenario=='baseline_repeat')
            if unstable and not io.active:
                result['force_n'][0]+=.35 if read_no%2 else -.35
            if scenario=='moving_baseline' and attempts[2]==1 and io.active:
                tip=posx_to_pose(result['posx'],w['tool_offset_m'])
                travel=sum((tip[k]-active['start_pose'][k])*active['direction'][k] for k in range(3))
                if .002<=travel<=.0033:
                    result['force_n'][0]+=.35 if read_no%2 else -.35
            if scenario=='absolute_force':result['force_n']=[20.,0.,0.]
            if scenario=='protection':result['robot_state']=3
        return result
    def stop(profile):
        if active and active.get('point_index')==2:
            if scenario=='stop_unknown':return StepResult('UNKNOWN','STOP_UNCONFIRMED',observed_state={'stop_confirmed':False})
            if scenario=='cancel':ctx.cancel.set()
            if attempts[2]==1 and scenario in ('baseline_shift','baseline_lateral'):
                tip=posx_to_pose(io.p,w['tool_offset_m'])
                direction=active['direction'] if scenario=='baseline_shift' else [0.,0.,1.]
                tip[:3]=[tip[k]+direction[k]*2*w['pose_tolerance_m'] for k in range(3)]
                io.p=pose_to_posx(tip,w['tool_offset_m'])
        return raw_stop(profile)
    def ik(target,space):
        result=raw_ik(target,space)
        if scenario=='baseline_noop_ik' and active and active.get('point_index')==2 and attempts[2]==1:
            # 기준선 실패 직후 불필요한 재검사가 제어기의 다른 IK 해를 선택하는 상황.
            # 기준선만 재수집하면 이 IK 호출 자체가 없어야 한다.
            result[2]=cfg['guards']['joint_max_deg'][2]+1.
        return result
    ad.execute_measurement_step=execute;io.read=read;ad.stop_measurement=stop;io.ik=ik
    result=measure_workpiece(ad,w,cfg['profiles'],ctx,events.append)
    return result,attempts,steps,events,traces


@pytest.mark.parametrize('scenario',['baseline','moving_baseline','early','late'])
def test_same_point_reacquired_then_remaining_seven_preserved(scenario):
    r,attempts,steps,events,traces=trial(scenario)
    assert r.ok,(r.error_code,r.message)
    assert attempts==Counter({0:1,1:1,2:2,3:1,4:1,5:1,6:1,7:1,8:1})
    labels=[label for label,_ in steps]
    first=labels.index('point_2_touch');second=labels.index('point_2_touch',first+1)
    if scenario=='baseline':
        assert labels[first+1:second]==[]
        assert r.observed_state['target_rechecks']==[]
    else:
        # 시작점까지 후퇴한 뒤 PROBE가 다시 접근한다. 같은 시작점으로 MOVE를 반복하지 않는다.
        assert labels[first+1:second]==['point_2_retract']
        assert steps[first+1][1]['profile']=='retract'
        assert steps[first+1][1]['target_pose']==steps[first][1]['start_pose']
    assert len(r.observed_state['measurement']['points'])==8
    assert [p['point_index'] for p in r.observed_state['measurement']['points']]==list(range(1,9))
    assert r.observed_state['home_return_confirmed']
    assert any(e=='stationary_baseline' and d['label']=='point_2_touch' for e,d in traces)


@pytest.mark.parametrize('before_search',[False,True])
def test_stationary_retry_does_not_recheck_ik_or_move(before_search):
    r,attempts,steps,events,_=trial('baseline_noop_ik',before_search=before_search)
    assert r.ok,(r.error_code,r.message)
    assert attempts[2]==2
    labels=[label for label,_ in steps]
    first=labels.index('point_2_touch');second=labels.index('point_2_touch',first+1)
    assert labels[first+1:second]==[]
    assert r.observed_state['target_rechecks']==[]


@pytest.mark.parametrize('scenario',['baseline_unknown','baseline_shift'])
def test_stationary_retry_requires_command_evidence_and_start_position(scenario):
    r,attempts,steps,events,_=trial(scenario)
    assert r.ok,(r.error_code,r.message)
    labels=[label for label,_ in steps]
    first=labels.index('point_2_touch');second=labels.index('point_2_touch',first+1)
    assert labels[first+1:second]==['point_2_retract']
    assert [s['label'] for s in r.observed_state['target_rechecks']]==['point_2_retract']
    assert any(e.get('values',{}).get('stationary_retry') is False for e in events if e.get('values'))


def test_baseline_failure_outside_radial_corridor_blocks_retry():
    r,attempts,steps,_,_=trial('baseline_lateral')
    assert r.error_code=='RECOVERY_REQUIRED'
    assert attempts[2]==1 and attempts[3]==0
    assert steps[-1][0]=='point_2_touch'
    assert r.observed_state['target_rechecks']==[]


def test_single_fit_outlier_is_excluded_without_reacquisition():
    r,attempts,steps,events,_=trial('outlier')
    assert r.ok,(r.error_code,r.message)
    assert attempts==Counter({i:1 for i in range(9)})
    assert len(r.observed_state['measurement']['points'])==8
    assert r.observed_state['measurement']['fit_excluded_point_indices']==[4]
    assert not r.observed_state.get('superseded_points')
    labels=[x[0] for x in steps];last=labels.index('point_8_outer')
    assert not any(label.startswith('point_') or step['kind']=='PROBE' for label,step in steps[last+1:])
    from c2_process.preparation_action import result_from_step
    result=result_from_step({'source_mode':'SIMULATION'},r)
    assert result['outcome']=='SUCCEEDED'
    assert result['contact_indices']==list(range(9))
    assert '4번 이상점 제외' in result['message']
    assert result['residual_max_m']==r.observed_state['measurement']['residual_max_m']
    assert '4번 이상점 제외' in r.message


@pytest.mark.parametrize('scenario',['shifted_outlier','shifted_persistent_outlier'])
def test_shifted_circle_uses_seven_points_and_never_returns_to_sixth(scenario):
    r,attempts,steps,events,_=trial(scenario,before_search=True)
    assert r.ok,(r.error_code,r.message)
    assert attempts==Counter({i:1 for i in range(9)})
    assert len(r.observed_state['measurement']['points'])==8
    assert r.observed_state['measurement']['fit_excluded_point_indices']==[6]
    assert r.observed_state['measurement']['fit_used_point_indices']==[1,2,3,4,5,7,8]
    assert not r.observed_state.get('superseded_points')
    assert r.observed_state['home_return_confirmed']
    assert any(e['stage']=='FIT' and '6번 이상점 제외' in e['message'] for e in events)
    labels=[label for label,_ in steps];last=labels.index('point_8_outer')
    assert not any(label.startswith('point_') or step['kind']=='PROBE' for label,step in steps[last+1:])


@pytest.mark.parametrize('scenario',['baseline_repeat','early_repeat'])
def test_repeat_failure_has_three_total_attempts_and_confirmed_stop(scenario):
    r,attempts,steps,_,_=trial(scenario)
    assert r.error_code=='RECOVERY_REQUIRED',(r.error_code,r.message)
    assert attempts[2]==3
    assert r.observed_state['stop_confirmed'] and not r.observed_state['home_return_confirmed']
    assert steps[-1][0]==('point_2_touch' if scenario=='baseline_repeat' else 'point_2_retract')
    assert attempts[3]==0


@pytest.mark.parametrize('scenario,code',[('absolute_force','FORCE_LIMIT'),('protection','NOT_READY'),('communication','COMMUNICATION_LOST'),('tcp','PROFILE_MISMATCH'),('authority','NOT_READY'),('timeout','TIMEOUT'),('stop_unknown','STOP_UNCONFIRMED'),('cancel','CANCELLED')])
def test_fatal_or_uncertain_failure_never_reapproaches(scenario,code):
    r,attempts,steps,_,_=trial(scenario)
    assert not r.ok and r.error_code==code,(r.error_code,r.message)
    assert attempts[2]==1 and attempts[3]==0
    assert steps[-1][0]=='point_2_touch'
    if scenario=='stop_unknown':assert r.outcome=='UNKNOWN' and r.observed_state['stop_confirmed'] is False


def test_recovery_motion_failure_is_not_retried():
    r,attempts,steps,_,_=trial('retract_failure')
    assert r.error_code=='FORCE_LIMIT'
    assert attempts[2]==1 and steps[-1][0]=='point_2_retract'
