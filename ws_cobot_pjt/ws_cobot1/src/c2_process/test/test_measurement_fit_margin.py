"""실측 좌표의 오프라인 재계산과 도달 여유 경계 검사. 로봇을 호출하지 않는다."""
from copy import deepcopy
import json
import math
from pathlib import Path

import pytest

from c2_process.workpiece_calibration import (fit_circle, fit_center_limit, fit_is_acceptable,
                                             side_center_limit, fit_measured_points, MeasurementError)


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def recorded():
    w=json.loads((ROOT/'config/workpiece_real_trial_0921.json').read_text())['workcell']
    points=json.loads((ROOT/'test/fixtures/workpiece_fit_failure_20260929.json').read_text())['points_m']
    return w,points


def test_recorded_failure_identifies_only_point_six_without_accepting_bad_eight(recorded):
    w,points=recorded
    fit=fit_circle(points)
    assert fit['residual_rms_m']==pytest.approx(.0006370782252)
    assert not fit_is_acceptable(w,fit,points)
    before=deepcopy(points)
    clean,details=fit_measured_points(w,points)
    assert details['fit_excluded_point_indices']==[6]
    assert details['fit_used_point_indices']==[1,2,3,4,5,7,8]
    assert points==before
    assert clean['residual_rms_m']==pytest.approx(.00008776416345)
    assert math.dist(clean['axis_xy_m'],w['seed_axis_xy_m'])>side_center_limit(w)
    assert fit_center_limit(w,clean)==pytest.approx(.0047)


@pytest.mark.parametrize('bad_indices',[[],[6],[8],[6,8]])
def test_fit_uses_all_points_or_one_unique_outlier_only(recorded,bad_indices):
    w,_=recorded
    points=[]
    for index,angle in enumerate(w['angles_deg'],1):
        a=math.radians(angle);radius=w['seed_radius_m']-(.0024 if index in bad_indices else 0.)
        points.append([w['seed_axis_xy_m'][0]+radius*math.cos(a),
                       w['seed_axis_xy_m'][1]+radius*math.sin(a),.2])
    fit,details=fit_measured_points(w,points)
    if len(bad_indices)<=1:
        assert details['fit_excluded_point_indices']==bad_indices
        assert fit['radius_m']==pytest.approx(w['seed_radius_m'])
        assert fit['axis_xy_m']==pytest.approx(w['seed_axis_xy_m'])
    else:
        assert len(details['fit_excluded_point_indices'])==1
        assert len(details['fit_used_point_indices'])==7
        assert details['fit_selection']=='BEST_LEAVE_ONE_OUT'


def test_missing_opt_in_keeps_eight_point_requirement(recorded):
    w,points=recorded;w.pop('fit_outlier_max_exclusions')
    with pytest.raises(MeasurementError,match='추가 재측정 없음'):
        fit_measured_points(w,points)


def test_measured_center_limit_uses_completed_search_corridor(recorded):
    w,_=recorded
    for radius_error in (-.001,-.0005,0.,.00024317671745,.0005,.001):
        fit={'radius_m':w['seed_radius_m']+radius_error}
        limit=fit_center_limit(w,fit)
        assert limit>=side_center_limit(w)-1e-12
        assert limit+w['pose_tolerance_m']==pytest.approx(
            min(w['start_gap_m'],w['side_search_m']-w['start_gap_m']))


def test_latest_real_eight_points_pass_without_arbitrary_exclusion(recorded):
    w,_=recorded
    points=[
        [0.42323976023667365,0.030350018017098135,0.19638389010882823],
        [0.4022680270925102,0.021332961624010258,0.19635613722239914],
        [0.3918868012458978,0.0003332610696096571,0.19634461188324107],
        [0.3987225547532066,-0.024326397003708602,0.1964346848542593],
        [0.42325581700924353,-0.037637429286940555,0.1964032129229644],
        [0.45065334207883917,-0.02705334266746766,0.19639763441108818],
        [0.4595968393251044,0.00033425134737327493,0.19635553888990437],
        [0.4462904440704528,0.023358202664180136,0.196303796699502],
    ]
    fit,details=fit_measured_points(w,points)
    assert details['fit_excluded_point_indices']==[]
    assert fit['residual_rms_m']==pytest.approx(9.344001530737231e-05)


@pytest.mark.parametrize('field,value',[
    ('residual_rms_m',.00031),('residual_max_m',.00061),
    ('radius_m',.0351),('axis_xy_m',[.430,.00032844108604387424]),
])
def test_other_quality_and_range_failures_still_rejected(recorded,field,value):
    w,points=recorded;points=points[:5]+points[6:]
    fit=fit_circle(points);fit[field]=value
    assert not fit_is_acceptable(w,fit,points)


def test_height_spread_still_rejected(recorded):
    w,points=recorded;points=deepcopy(points[:5]+points[6:])
    fit=fit_circle(points);points[0][2]+=.001
    assert not fit_is_acceptable(w,fit,points)


def test_legacy_center_bound_unchanged(recorded):
    w,points=recorded;w.pop('side_search_m')
    assert fit_center_limit(w,fit_circle(points))==w['max_center_shift_m']
