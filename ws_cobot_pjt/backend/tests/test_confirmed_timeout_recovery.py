"""최종 TIMEOUT의 정지 증거로만 HMI의 잘못된 UNKNOWN을 정리한다. 로봇 호출 없음."""
import asyncio
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.preparation import PreparationService, confirmed_timeout_failure
from app.storage import Storage


def sample():
    path=Path(__file__).resolve().parents[2]/'ws_cobot1/src/c2_process/test/fixtures/prepare_workpiece_action_samples/success.json'
    value=json.loads(path.read_text())
    goal=value['goal'];raw=value['result']
    raw.update(outcome='FAILED',error_code='TIMEOUT',stop_confirmed=True,
               geometry_ready=False,snapshot_bound=False,message='측정 취소')
    return goal,raw


@pytest.mark.parametrize('defect',[None,'stop','request','measurement','hash','missing_hash','success','unknown','not_timeout'])
def test_recovery_requires_matching_hashed_final_timeout_with_stop(tmp_path,defect):
    async def scenario():
        goal,raw=sample()
        if defect=='stop':raw['stop_confirmed']=False
        if defect=='request':raw['request_id']='other-request'
        if defect=='measurement':raw['measurement_id']='other-measurement'
        if defect=='success':raw['outcome']='SUCCEEDED'
        if defect=='unknown':raw['outcome']='UNKNOWN'
        if defect=='not_timeout':raw['error_code']='COMMUNICATION_LOST'
        store=Storage(tmp_path)
        asset=store.put_json(dict(contract='prepare-workpiece-result/1',result=raw),'measurement_record','result.json')
        if defect=='hash':asset['sha256']='0'*64
        if defect=='missing_hash':asset['sha256']=None
        record=dict(request_id=goal['request_id'],state='UNKNOWN',action_goal=goal,
                    measurement_record=asset,error_code='STOP_UNCONFIRMED')
        store.save_preparation(record)
        service=PreparationService(SimpleNamespace(transport='ros',store=store))
        service.current=deepcopy(record)
        await service.reconcile_confirmed_timeout()
        if defect is None:
            assert service.current['state']=='FAILED' and service.current['error_code']=='TIMEOUT'
            assert not service.blocks_work()
            assert service.current['timeout_reconciliation']['previous_state']=='UNKNOWN'
            assert store.recover_preparation()['state']=='FAILED'
            assert json.loads(store.read_asset(asset['id']))['result']==raw
        else:
            assert service.current==record and service.blocks_work()
    asyncio.run(scenario())


def test_timeout_final_response_does_not_become_unknown_after_hmi_cancel(tmp_path):
    async def scenario():
        goal,raw=sample();release=asyncio.Event();calls=[]
        class Peer:
            async def prepare_raw(self,g,feedback):
                calls.append(g['operation']);await release.wait();return deepcopy(raw)
            async def cancel_preparation(self,rid):
                assert rid==goal['request_id'];release.set()
        store=Storage(tmp_path)
        owner=SimpleNamespace(store=store,transport='ros',peer=Peer(),fresh=lambda:True)
        service=PreparationService(owner);service.timeout_s=.001
        service.current=dict(request_id=goal['request_id'],state='ACCEPTED',feedback=[])
        await service.run_ros(goal,asyncio.Event())
        assert service.current['state']=='FAILED',service.current
        assert service.current['error_code']=='TIMEOUT' and not service.blocks_work()
        assert calls==['MEASURE'] and 'bind_goal' not in service.current
    asyncio.run(scenario())
