"""기존 공정 노드의 ObservationCache에 조회값을 공급한다.

새 노드·토픽·메시지를 만들지 않는다. ProcessState 발행과 공정 상태는
node.py 담당이며, 이 모듈은 현재 관절·제어기 TCP·연결 관측만 갱신한다.
"""
import math
import threading
import time

from .robot_adapter import RobotState, posx_to_pose


class ProcessStateObserver:
    """5 Hz 비동기 조회. executor 콜백에서 서비스 응답을 기다리지 않는다."""

    def __init__(self, node, cache, controller_prefix, timeout_s, max_age_s):
        from dsr_msgs2.srv import GetCurrentPosj, GetCurrentPosx, GetRobotState
        from rclpy.callback_groups import MutuallyExclusiveCallbackGroup

        if (not isinstance(controller_prefix, str) or not controller_prefix.startswith('/')
                or controller_prefix.rstrip('/') == ''
                or not callable(getattr(cache, 'capture', None))):
            raise ValueError('제어기 절대 namespace와 공정 ObservationCache 필요')
        if any(type(v) not in (int, float) or not math.isfinite(v) or v <= 0
               for v in (timeout_s, max_age_s)):
            raise ValueError('조회 제한 시간과 관측 유효기간은 양수 초')
        self.node, self.cache = node, cache
        self.settings = (controller_prefix.rstrip('/'), timeout_s, max_age_s)
        self.timeout, self.max_age = min(timeout_s, max_age_s), max_age_s
        self.lock = threading.RLock()
        self.pending = None
        self.closed = False
        self.pause_depth = 0
        self.recovery_pending = False
        self.recovery_deadline = 0.0
        self.group = MutuallyExclusiveCallbackGroup()
        self.clients = {}
        for key, endpoint, kind in (
            ('joints', 'aux_control/get_current_posj', GetCurrentPosj),
            ('tcp', 'aux_control/get_current_posx', GetCurrentPosx),
            ('robot', 'system/get_robot_state', GetRobotState),
        ):
            request = kind.Request()
            if key == 'tcp':request.ref = 0  # 제어기 BASE, 기존 c2_base 등록 기준
            client = node.create_client(kind, self.settings[0]+'/'+endpoint, callback_group=self.group)
            self.clients[key] = (client, request)
        self.timer = node.create_timer(0.2, self._tick, callback_group=self.group)

    def _unknown(self):
        self.cache.capture(RobotState(), None, self.max_age)

    def _discard(self):
        previous, self.pending = self.pending, None
        if previous is not None:
            for future in previous['futures']:
                if not future.done():future.cancel()

    def _tick(self):
        with self.lock:
            if self.closed or self.pause_depth:return
            if self.pending is not None:
                if time.monotonic()-self.pending['started'] < self.timeout:return
                self._discard()
                self._unknown()
            if not all(c.service_is_ready() for c, _ in self.clients.values()):
                self._unknown()
                return
            # 응답에는 원본 시각이 없다. 이 조회 묶음의 시작 시각을 보수적으로 사용한다.
            batch = dict(started=time.monotonic(), utc_ns=time.time_ns(), answers={}, futures=[])
            self.pending = batch
            try:
                for key, (client, request) in self.clients.items():
                    if self.pending is not batch:break
                    future = client.call_async(request)
                    batch['futures'].append(future)
                    future.add_done_callback(lambda f, k=key: self._received(batch, k, f))
            except Exception:
                self._discard()
                self._unknown()

    def pause(self):
        """고부하 장치 조회 구간에서 중복 상태 조회를 일시 중단한다.

        중첩 호출을 허용하며, 진행 중인 조회 응답은 폐기하고 캐시는 즉시 UNKNOWN으로
        바꾼다. 로봇 상태를 추측해 유지하지 않고 모션 명령에도 관여하지 않는다.
        """
        with self.lock:
            if self.closed:
                return False
            self.pause_depth += 1
            if self.pause_depth == 1:
                self.recovery_pending = True
                self.recovery_deadline = float('inf')
                self._discard()
                self._unknown()
            return True

    def resume(self):
        """마지막 pause와 짝이 맞을 때 다음 타이머 주기부터 조회를 재개한다."""
        with self.lock:
            if self.closed or self.pause_depth == 0:
                return False
            self.pause_depth -= 1
            if self.pause_depth == 0:
                # 다음 0.2초 타이머와 한 묶음의 서비스 제한 시간을 보장하되,
                # 드라이버가 회복하지 않으면 BIND가 무기한 남지 않게 한다.
                self.recovery_deadline = time.monotonic() + self.timeout + 0.4
            return self.pause_depth == 0

    def defer_binding_invalidation(self, *, now=None):
        """의도적 일시중단/첫 조회 복구 중에만 기존 BIND 삭제를 유예한다.

        실행 가능 판정이 아니며, 제한시간 뒤에는 실패 관측을 그대로 반영한다.
        """
        with self.lock:
            if self.closed or not self.recovery_pending:
                return False
            current = time.monotonic() if now is None else now
            if self.pause_depth > 0 or current <= self.recovery_deadline:
                return True
            self.recovery_pending = False
            return False

    def _received(self, batch, key, future):
        with self.lock:
            if self.closed or self.pending is not batch:return
            try:
                response = future.result()
                if response is None or not response.success:
                    raise ValueError('조회 실패')
                if time.monotonic()-batch['started'] >= self.timeout:
                    raise TimeoutError('늦은 조회 응답')
                batch['answers'][key] = response
                if len(batch['answers']) != len(self.clients):return
                answers = batch['answers']
                joints = list(answers['joints'].pos)
                native_tcp = list(answers['tcp'].task_pos_info[0].data[:6])
                for values in (joints, native_tcp):
                    if len(values) != 6 or not all(math.isfinite(v) for v in values):
                        raise ValueError('잘못된 위치/관절 응답')
                code = answers['robot'].robot_state
                if type(code) is not int or code not in (*range(11), 15):
                    raise ValueError('미지원 로봇 상태')
                state = RobotState(joints_rad=[math.radians(v) for v in joints],
                    tcp_pose=posx_to_pose(native_tcp), frame_id='c2_base', robot_state=code,
                    measured_at=batch['started'], quality='VALID')
                # offset=None: 위 Pose는 도구 끝이 아니라 원래 제어기 TCP다.
                now = time.monotonic()
                self.cache.capture(state, None, self.max_age,
                    now=now, utc_ns=batch['utc_ns']+int((now-batch['started'])*1e9))
                self.pending = None
                self.recovery_pending = False
                self.recovery_deadline = 0.0
            except Exception:
                self._discard()
                self._unknown()

    def close(self):
        """노드 종료/관측 중단용. 로봇 명령·모션 잠금에는 관여하지 않는다."""
        with self.lock:
            if self.closed:return
            self.closed = True
            self.pause_depth = 0
            self.recovery_pending = False
            self.recovery_deadline = 0.0
            self._discard()
            self._unknown()
            self.node.destroy_timer(self.timer)
            for client, _ in self.clients.values():self.node.destroy_client(client)


def start_process_state_observer(node, config):
    """공정 노드가 기존 캐시를 만든 뒤 직접 호출한다. 측정 함수에서는 호출하지 않는다.

    준비 요청 전 시작하고 측정 결과 반환 후에도 유지한다. 같은 설정의 중복 호출은
    재사용하며, 종료 시 stop_process_state_observer(node)를 공정 노드가 호출한다.
    """
    if getattr(getattr(node, 'coordinator', None), 'runtime_mode', None) != 'REAL':
        raise ValueError('실제 조회는 REAL 공정 노드에서만 연결')
    settings = (config['controller_prefix'].rstrip('/'), config['service_timeout_s'],
                config['guards']['max_state_age_s'])
    with _attach_lock:
        observer = getattr(node, '_c2_process_state_observer', None)
        if observer is not None and not observer.closed:
            if observer.settings != settings:raise ValueError('기존 관측기 설정 불일치')
            return observer
        observer = ProcessStateObserver(node, node.observations, *settings)
        node._c2_process_state_observer = observer
        return observer


def stop_process_state_observer(node):
    """노드 종료 시 직접 호출. 여러 번 호출해도 같은 자원을 중복 정리하지 않는다."""
    with _attach_lock:
        observer = getattr(node, '_c2_process_state_observer', None)
        if observer is not None:observer.close()


_attach_lock = threading.Lock()
