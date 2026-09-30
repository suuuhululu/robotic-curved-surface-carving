"""ROS 게이트웨이 자체가 전체 공정 시간을 제한하지 않는지 검사한다."""
import asyncio
from types import SimpleNamespace

from app import ros_bridge
from app.ros_bridge import RosBridge


def test_execute_action_has_no_gateway_total_runtime_limit(monkeypatch):
    """긴 REAL 공정을 숨은 1시간 상한으로 취소하지 않는다."""
    async def scenario():
        timeouts=[]

        class Goal:
            def get_fields_and_field_types(self):
                return {'schema_version':'uint16','source_mode':'string','request_id':'string'}

        class Handle:
            accepted=True

            def get_result_async(self):return 'result-future'

        class Client:
            def server_is_ready(self):return True

            def send_goal_async(self,goal,feedback_callback):return 'accept-future'

        async def fake_await_ros(future,timeout):
            timeouts.append(timeout)
            if future=='accept-future':return Handle()
            return SimpleNamespace(result={'outcome':'SUCCEEDED'})

        monkeypatch.setattr(ros_bridge,'await_ros',fake_await_ros)
        bridge=RosBridge(None);bridge.loop=asyncio.get_running_loop();bridge.convert=lambda x:x
        bridge.generate_client=object();client=Client()
        result=await bridge.action(client,SimpleNamespace(Goal=Goal),
            {'schema_version':2,'source_mode':'SIMULATION','request_id':'long-run'})
        assert result=={'outcome':'SUCCEEDED'}
        assert timeouts==[3,None]

    asyncio.run(scenario())
