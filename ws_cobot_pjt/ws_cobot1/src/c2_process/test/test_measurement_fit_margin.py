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
    assert fit_center_limit(w,clean)==pytest.approx(.00385682328255)


@pytest.mark.parametrize('bad_indices',[[],[6],[8],[6,8]])
def test_fit_uses_all_points_or_one_unique_outlier_only(recorded,bad_indices):
    w,_=recorded
    points=[]
    for index,angle in enumerate(w['angles_deg'],1):
        a=math.radians(angle);radius=w['seed_radius_m']-(.0024 if index in bad_indices else 0.)
        points.append([w['seed_axis_xy_m'][0]+radius*math.cos(a),
                       w['seed_axis_xy_m'][1]+radius*math.sin(a),.2])
    if len(bad_indices)>1:
        with pytest.raises(MeasurementError,match='단일 이상점 식별 불가'):
            fit_measured_points(w,points)
    else:
        fit,details=fit_measured_points(w,points)
        assert details['fit_excluded_point_indices']==bad_indices
        assert fit['radius_m']==pytest.approx(w['seed_radius_m'])
        assert fit['axis_xy_m']==pytest.approx(w['seed_axis_xy_m'])


def test_missing_opt_in_keeps_eight_point_requirement(recorded):
    w,points=recorded;w.pop('fit_outlier_max_exclusions')
    with pytest.raises(MeasurementError,match='추가 재측정 없음'):
        fit_measured_points(w,points)


def test_radius_reserve_and_pose_margin_stay_inside_original_search(recorded):
    w,_=recorded
    for radius_error in (-.001,-.0005,0.,.00024317671745,.0005,.001):
        fit={'radius_m':w['seed_radius_m']+radius_error}
        limit=fit_center_limit(w,fit)
        assert limit>=side_center_limit(w)-1e-12
        # 원래 최대 형상 불확실성 4.7 mm와 위치 여유 0.3 mm를 초과하지 않는다.
        reserve=min(w['max_radius_error_m'],abs(radius_error)+w['max_fit_residual_m'])
        assert limit+reserve+w['pose_tolerance_m']<=min(w['start_gap_m'],w['side_search_m']-w['start_gap_m'])+1e-12


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
