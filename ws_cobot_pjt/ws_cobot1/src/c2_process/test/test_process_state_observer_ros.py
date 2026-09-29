"""격리된 모의 서비스 → 공유 캐시 → 기존 ProcessState 발행 검사. 로봇 명령 없음."""
import math
import os
from pathlib import Path
import sys
import time
from uuid import uuid4

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def test_pause_discards_pending_query_and_requires_matching_resume():
    import threading
    from c2_process.process_state_observer import ProcessStateObserver

    class Future:
        def __init__(self):
            self.cancelled = False

        def done(self):
            return False

        def cancel(self):
            self.cancelled = True

    class Cache:
        def __init__(self):
            self.captures = []

        def capture(self, *args, **kwargs):
            self.captures.append((args, kwargs))

    observer = object.__new__(ProcessStateObserver)
    observer.lock = threading.RLock()
    observer.pending = {'futures': [Future()]}
    future = observer.pending['futures'][0]
    observer.closed = False
    observer.pause_depth = 0
    observer.recovery_pending = False
    observer.recovery_deadline = 0.0
    observer.timeout = 0.5
    observer.cache = Cache()
    observer.max_age = 0.5

    assert observer.pause() is True
    assert observer.pause() is True
    assert observer.pending is None and future.cancelled
    assert len(observer.cache.captures) == 1
    assert observer.resume() is False
    assert observer.pause_depth == 1
    assert observer.resume() is True
    assert observer.pause_depth == 0
    assert observer.defer_binding_invalidation(now=observer.recovery_deadline) is True
    assert observer.defer_binding_invalidation(now=observer.recovery_deadline + .001) is False
    assert observer.resume() is False

@pytest.mark.skipif(os.environ.get('C2_RUN_OBSERVER_ROS_TEST') != '1',
                    reason='격리 ROS 환경과 빌드된 c2_interfaces 필요')
def test_existing_publisher_reads_observations_before_during_after_measurement():
    import rclpy
    from rclpy.executors import MultiThreadedExecutor
    from rclpy.node import Node
    from dsr_msgs2.srv import GetCurrentPosj, GetCurrentPosx, GetRobotState
    from std_msgs.msg import Float64MultiArray
    from c2_interfaces.msg import ProcessState
    from c2_process.node import create_ros_node
    from c2_process.process_state_observer import ProcessStateObserver

    prefix = '/observer_test_' + uuid4().hex
    args = ['--ros-args']
    for name in ('execute_process', 'stop_process', 'process_state', 'process_events'):
        args += ['-r', '/c2/'+name+':='+prefix+'/'+name]
    rclpy.init(args=args)
    server = create_ros_node(runtime_mode='SIMULATION', enable_preparation=False)
    fake = Node('fake_readonly_driver')
    healthy = [True]
    def joints(request, response):
        response.success = healthy[0]
        response.pos = [0., 90., 0., 0., 0., 0.]
        return response
    def tcp(request, response):
        assert request.ref == 0
        response.success = healthy[0]
        response.task_pos_info = [Float64MultiArray(data=[426., 100., 330., 0., 180., 0.])]
        return response
    def state(request, response):
        response.success = healthy[0]
        response.robot_state = 1
        return response
    for kind, path, callback in (
        (GetCurrentPosj, 'aux_control/get_current_posj', joints),
        (GetCurrentPosx, 'aux_control/get_current_posx', tcp),
        (GetRobotState, 'system/get_robot_state', state),
    ):
        fake.create_service(kind, prefix+'/driver/'+path, callback)
    received = []
    fake.create_subscription(ProcessState, prefix+'/process_state', received.append, 10)
    observer = ProcessStateObserver(server, server.observations, prefix+'/driver', .5, .5)
    executor = MultiThreadedExecutor(num_threads=4)
    executor.add_node(server)
    executor.add_node(fake)
    def wait_for(predicate):
        deadline = time.monotonic()+5
        while time.monotonic() < deadline:
            executor.spin_once(timeout_sec=.02)
            if predicate():return
        raise AssertionError('ROS 상태 수신 제한 시간 초과')
    try:
        previous_stamp = 0
        for status in ('IDLE', 'RUNNING', 'SUCCEEDED', 'IDLE'):
            received.clear()
            with server.lock:server.status = status
            wait_for(lambda: received and received[-1].status == status
                     and received[-1].tcp_quality == 'VALID'
                     and received[-1].tcp.header.stamp.sec*10**9 + received[-1].tcp.header.stamp.nanosec > previous_stamp)
            packet = received[-1]
            previous_stamp = packet.tcp.header.stamp.sec*10**9 + packet.tcp.header.stamp.nanosec
            assert packet.source_mode == 'SIMULATION'
            assert packet.joints[1] == pytest.approx(math.pi/2)
            assert packet.tcp.pose.position.x == pytest.approx(.426)
            assert packet.tcp.header.frame_id == 'c2_base'
        healthy[0] = False
        wait_for(lambda: received[-1].tcp_quality == 'UNKNOWN')
        healthy[0] = True
        wait_for(lambda: received[-1].tcp_quality == 'VALID')
        sequence = received[-1].seq
        observer.close()
        wait_for(lambda: received[-1].seq > sequence and received[-1].tcp_quality == 'UNKNOWN')
        assert server.count_publishers(prefix+'/process_state') == 1
    finally:
        observer.close()
        executor.shutdown()
        fake.destroy_node()
        server.destroy_node()
        rclpy.shutdown()
