# 팀 ROS 개발 디렉토리

> 기준: 2026-09-30 PR #99 head `3d882f6`. 세 패키지의 노드·빌드 설정이 모두
> 존재한다. 이전 9/19의 “노드·패키지 미구현” 설명은 현재 상태가 아니다.

```text
src/
├── c2_interfaces/   # 공통 Action 3 · Service 1 · Message 2
├── c2_path/         # 이미지→2D→원통 3D 경로·검증 Action 서버
└── c2_process/      # 준비 측정·BIND·검사·조각·정지 공정 노드
```

| 패키지 | 실행 책임 | 주요 진입점 |
| --- | --- | --- |
| [c2_interfaces](c2_interfaces/README.md) | 송수신 PC가 함께 빌드할 고정 드릴 v2 타입. 실행 노드는 없음 | `ros2 interface show ...` |
| [c2_path](c2_path/README.md) | 경로 생성과 파일·기하 검증. 로봇 모션을 실행하지 않음 | `path_planner_node` |
| [c2_process](c2_process/README.md) | MEASURE/BIND, PRECHECK, ENTRY, ENGRAVE와 마지막 RETRACT, 정지·상태 | `process_controller_node`, `real_preparation_node`, `real_process_node`, `virtual_cell_node` |

시스템 모니터의 ROS 클라이언트는 별도 ROS 패키지가 아니라
[`backend/app/ros_bridge.py`](../../backend/README.md)의 `monitor_gateway_node`다.
화면은 HTTP·WebSocket으로만 서버와 통신한다. 별도 `c2_hmi`나 그리퍼 제어 패키지를
만들지 않는다.

빌드 순서는 외부 두산 overlay 뒤 팀 overlay다.

```bash
source /opt/ros/jazzy/setup.bash
source "$C2_DSR_WS/install/local_setup.bash"
cd ws_cobot_pjt/ws_cobot1
colcon build --symlink-install
source install/local_setup.bash
```

checkout 안 `ws_dsr/src`에 전체 외부 원본이 없으면 그 위치에서 드라이버를 빌드하지
않는다. 환경 구성은 [로컬 실행환경](../../../docs/LOCAL_ENVIRONMENT.md), 노드·파일
책임은 [시스템 구조](../../docs/SYSTEM_STRUCTURE.md), 통신 계약은
[인터페이스](../../docs/INTERFACE_RECOMMENDATION.md)를 따른다.

기존 `clay_carving`·`clay_hmi`·자동 집기/청소 코드는 현재 공정에 복원하지 않는다.
[보관 기록](../../docs/LEGACY_CLAY_ARCHIVE.md)은 역사 자료다.
