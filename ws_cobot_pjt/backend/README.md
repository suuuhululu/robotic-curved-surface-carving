# 새김 시스템 모니터 서버

> 기준: 2026-09-30 PR #99 head `3d882f6`. FastAPI·SQLite·관리 파일과
> `monitor_gateway_node`를 제공한다. 이전 `HMI_*_202609*.md`는 당시 구현 기록이며
> 현재 실행 조건은 이 문서와 [인터페이스](../docs/INTERFACE_RECOMMENDATION.md)를
> 따른다.

## 역할

- 브라우저의 HTTP·WebSocket 요청을 검증하고 준비·경로 생성·실행·정지를 ROS에
  전달한다.
- 이미지, 측정 원본, 설정 스냅샷, 경로와 보고서를 UUID·버전·원본 바이트 SHA-256으로
  저장한다.
- 같은 요청 ID의 재전송과 충돌을 구분하고 늦은 응답·통신 상실·정지 미확인을
  성공으로 바꾸지 않는다.
- 좌표 생성과 로봇 모션 순서는 각각 `c2_path`와 `c2_process`가 소유한다.

| 모드 | 실행 범위 |
| --- | --- |
| 기본 `SIMULATION/mock` | 로봇 없는 HMI·서버·모의 준비/공정. 기본 이미지 변환은 실제 `c2_path` 계산 모듈 사용 |
| `SIMULATION/ros` | 실제 팀 ROS 타입과 경로 노드, 선택적으로 가상 공정 Action 연결 |
| `REAL/ros` | 실제 준비 MEASURE/BIND, REAL 경로 후보와 별도 실행 요청. 공정 노드·두산 드라이버는 별도 기동 |

REAL에서 준비 설정은 필수다. 실행 프로파일이 없거나 잘못되면 측정과 test-only
미리보기까지만 허용하고 BIND·실행 후보·조각을 차단한다. 준비 JSON과 실행
프로파일을 사전 검사 과정에서 수정하지 않는다.

## 설치

Python 3.12 가상환경을 사용한다. 기본 이미지 워크플로까지 실행하려면 이미지 포함
잠금 파일을 설치한다.

```bash
cd ws_cobot_pjt/backend
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements-image.lock.txt
```

ROS의 `rclpy`, 생성된 `c2_interfaces`, 외부 `dsr_msgs2`는 pip로 대체하지 않는다.
Jazzy와 각 overlay를 source한다. 새 PC의 전체 환경은
[로컬 실행환경](../../docs/LOCAL_ENVIRONMENT.md)을 따른다.

## 실행

저장소 루트에서 HMI와 서버를 함께 실행한다.

```bash
python3 ws_cobot_pjt/run_monitor.py
```

- 화면: `http://127.0.0.1:5174/operator`
- API 문서: `http://127.0.0.1:8010/docs`
- 종료: 실행 터미널에서 `Ctrl+C`

ROS SIM:

```bash
python3 ws_cobot_pjt/run_monitor.py \
  --transport ros --mode SIMULATION --process-integration --ros-domain-id 20
```

REAL:

```bash
python3 ws_cobot_pjt/run_monitor.py \
  --transport ros --mode REAL --ros-domain-id 20 \
  --preparation-config ws_cobot_pjt/ws_cobot1/src/c2_process/config/workpiece_real_trial_0921.json \
  --execution-profile ws_cobot_pjt/ws_cobot1/src/c2_process/config/real_execution_profile_20260923.json
```

`run_monitor.py`는 필요할 때 `c2_path`를 함께 시작한다. 이미 실행 중인 경로 노드를
사용할 때만 `--external-path-node`를 지정한다. `real_process_node`와 외부 두산
드라이버는 자동 기동하지 않는다.

서버만 실행하는 MOCK 개발 모드:

```bash
cd ws_cobot_pjt/backend
C2_MONITOR_MODE=SIMULATION C2_MONITOR_TRANSPORT=mock \
  .venv/bin/python -m uvicorn app.monitor:app --host 127.0.0.1 --port 8010
```

`--workers`는 1만 지원한다. 같은 DB를 쓰는 중복 서버는 파일 잠금으로 거절한다.
REAL은 위 통합 실행기를 사용해 `mode=REAL`, `transport=ros`, 준비 설정을 함께
고정한다.

## 데이터와 환경 변수

| 항목 | 기본값·의미 |
| --- | --- |
| `C2_MONITOR_DATA` | MOCK `backend/monitor_data`, ROS SIM `monitor_data/ros_path`, REAL `monitor_data/real_preparation` |
| `C2_PREPARATION_CONFIG` | REAL 측정 설정. `--preparation-config`가 설정 |
| `C2_EXECUTION_PROFILE` | REAL 실행 정책. `--execution-profile`이 설정 |
| `C2_MONITOR_MODE` | `SIMULATION` 또는 `REAL` |
| `C2_MONITOR_TRANSPORT` | `mock` 또는 `ros` |
| `ROS_DOMAIN_ID` | 통합 실행기의 기본 20 |

SQLite는 `monitor.sqlite3`, 관리 파일은 `assets/<UUID>.bin`이다. 이전
`data/saegim.sqlite3`를 자동 마이그레이션하지 않는다. 백업은 서버를 정상 종료한 뒤
해당 데이터 디렉터리 전체를 복사한다. 자동 보관 만료·삭제는 없다.

## ROS 연결과 준비 상태

`app/ros_bridge.py`는 같은 프로세스의 `monitor_gateway_node`다.

- `/c2/prepare_workpiece`
- `/c2/generate_path`
- `/c2/execute_process`
- `/c2/stop_process`
- `/c2/process_state`
- `/c2/process_events`

게이트웨이는 실행 Action 전체에 별도의 고정 제한시간을 두지 않는다. 최종 Result나
명시적 취소를 기다리며, 개별 모션·측정·정지 제한시간은 공정 노드의 승인된 실행
프로파일이 적용한다.

MEASURE 성공 뒤 서버가 원본과 설정을 저장하고, 유효한 실행 프로파일이 있으면
`BIND_SNAPSHOT`으로 공정 노드의 같은 측정과 대조한다. BIND는 실행 승인이나 측정
정확도 증명이 아니다. 현재 공정 상태·제어권·관측이 무효화되거나 공정 노드가
재시작되면 저장 파일만으로 자동 복구하지 않는다.

같은 MEASURE 요청의 저장된 최종 결과가 `FAILED/TIMEOUT`,
`stop_confirmed=true`, 형상·스냅샷 없음으로 확인되면 재연결 뒤 `UNKNOWN`이 아닌
확인된 실패로 표시한다. 이를 성공이나 새 측정 요청으로 바꾸지 않는다.

HMI·서버에는 진행 중 PRECHECK·측정·조각을 다음 날 이어가는 pause/resume 계약이
없다. 확인된 정지 후 새 준비부터 시작한다.

## 시험

```bash
cd ws_cobot_pjt/backend
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=. .venv/bin/pytest -q
```

ROS 계약 시험은 Jazzy와 같은 checkout의 `c2_interfaces` overlay를 source한 뒤
실행한다. 시험 통과는 실제 M0609의 정지·충돌·측정 정확도·가공 품질 합격이 아니다.
