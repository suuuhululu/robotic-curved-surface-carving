# 로컬 실행환경 구성

> 기준: 2026-09-30 PR #99 head `3d882f6`. 이 문서는 현재 checkout의 코드로
> HMI·ROS 패키지를 준비하는 절차다. 명령은 로봇을 자동으로 움직이지 않지만,
> REAL 공정 노드와 외부 드라이버를 기동한 뒤의 HMI 요청은 모션을 만들 수 있다.

## 확인한 이 PC

| 항목 | 확인값 | 의미 |
| --- | --- | --- |
| OS / CPU | Ubuntu 24.04 / x86_64 | 현재 개발·시험 PC |
| ROS | ROS 2 Jazzy | 프로젝트 기준 배포판 |
| Python | 3.12.3 | 백엔드 `.venv`도 3.12.3 |
| Node / pnpm | 18.19.1 / 11.25.0 | 현재 프런트 의존성·build 확인 환경. lockfile을 우선 사용 |
| 프런트 시험용 Node | 24.19.0 | `--experimental-strip-types` preview 시험 5건 확인. 프로젝트가 이 런타임을 설치하지는 않음 |
| Docker / Compose | 29.8.1 / 5.5.1 | 설치돼 있지만 HMI 기본 실행에는 필요하지 않음 |
| 팀 ROS 소스 | `c2_interfaces`, `c2_path`, `c2_process` | checkout의 `ws_cobot1/src`에서 `colcon list`로 확인 |
| 외부 두산 소스 | checkout 안에는 전체 원본 없음 | 추적된 제어권 패치 4개만으로 드라이버를 빌드할 수 없음 |
| 외부 두산 설치본 | 별도 `ws_dsr/install` overlay | `dsr_msgs2`, `dsr_controller2`, `dsr_hardware2`가 이 overlay에서 조회됨 |

현재 셸에서 패키지가 조회된다는 사실만으로 checkout의 외부 소스가 재현됐다고
보지 않는다. 실제 overlay 위치는 PC마다 다르므로 아래처럼 변수로 지정한다.

```bash
export C2_REPO="$PWD"
export C2_DSR_WS="외부_cobot_rg2_워크스페이스_절대경로"
export C2_RUNTIME_DIR="$C2_REPO/.local/c2-runtime"
mkdir -p "$C2_RUNTIME_DIR"
```

## 앱 의존성

기본 이미지 워크플로도 `c2_path` 계산 모듈을 사용하므로 백엔드는 이미지 포함
잠금 파일로 설치한다.

```bash
cd "$C2_REPO/ws_cobot_pjt/backend"
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements-image.lock.txt

cd "$C2_REPO/ws_cobot_pjt/frontend"
pnpm install --frozen-lockfile
```

TypeScript/Vite build는 이 PC의 Node 18.19.1로 통과했다. 다만
`tests/preview.test.mjs`의 현재 명령은 Node의 `--experimental-strip-types`가 필요하므로
전체 프런트 시험까지 실행할 새 환경은 Node 22 이상을 사용한다.

`requirements.lock.txt`는 서버 기본 의존성만 담는다. `run_monitor.py`의 기본 이미지
변환까지 사용하려면 `requirements-image.lock.txt`가 필요하다. ROS Python 모듈은
pip로 대체하지 않고 Jazzy와 빌드한 overlay에서 가져온다.

## 두산 드라이버와 팀 ROS overlay

새 PC는 [외부 의존성 기록](DEPENDENCIES.md)에 적힌 승인 원본 전체를 별도
`C2_DSR_WS/src`에 준비한다. 기존 실행 PC의 외부 `.git`, 로컬 수정, build/install을
checkout의 부분 파일로 덮어쓰지 않는다. 제어권 패치 적용은
[관측 토픽 문서](../ws_cobot_pjt/docs/CONTROL_AUTHORITY_TOPIC.md)의 네 파일을 원본과
대조해 수행한다.

```bash
source /opt/ros/jazzy/setup.bash
source "$C2_DSR_WS/install/local_setup.bash"

cd "$C2_REPO/ws_cobot_pjt/ws_cobot1"
colcon list
colcon build --symlink-install
source install/local_setup.bash

ros2 pkg prefix dsr_msgs2
ros2 pkg prefix c2_interfaces
ros2 interface show c2_interfaces/action/PrepareWorkpiece
```

`ws_dsr`와 `ws_cobot1`의 `build/install/log`를 섞지 않는다. checkout 안
`ws_cobot_pjt/ws_dsr`의 `colcon list`가 비어 있으면 전체 외부 원본이 없는
상태이므로 그 위치에서 드라이버를 새로 빌드하지 않는다.

외부 드라이버의 실제 bringup 명령은 설치한 `cobot_rg2` 버전의 문서를 따른다.
저장소는 확인하지 않은 launch 파일·IP·모드를 대신 정하지 않는다. bringup 후에는
최소한 아래 인터페이스를 읽기 전용으로 확인한다.

```bash
ros2 service type /dsr01/dsr_controller2/system/get_robot_state
ros2 service type /dsr01/dsr_controller2/motion/check_motion
ros2 service type /dsr01/dsr_controller2/aux_control/get_current_posx
ros2 service type /dsr01/dsr_controller2/aux_control/get_current_posj
ros2 topic info /dsr01/dsr_controller2/control_authority -v
```

## HMI 실행

기본 MOCK은 로봇·드라이버를 기동하지 않는다.

```bash
cd "$C2_REPO"
python3 ws_cobot_pjt/run_monitor.py
```

- 화면: `http://127.0.0.1:5174/operator`
- API: `http://127.0.0.1:8010/docs`
- 종료: 실행 터미널에서 `Ctrl+C`

ROS SIM은 같은 checkout의 타입·경로·공정 overlay를 source한 터미널에서 실행한다.

```bash
source /opt/ros/jazzy/setup.bash
source "$C2_DSR_WS/install/local_setup.bash"
source "$C2_REPO/ws_cobot_pjt/ws_cobot1/install/local_setup.bash"
cd "$C2_REPO"
python3 ws_cobot_pjt/run_monitor.py \
  --transport ros --mode SIMULATION --process-integration --ros-domain-id 20
```

REAL HMI에는 측정 설정이 필수다. 실행 프로파일이 없으면 측정과 test-only
미리보기까지만 허용하며 BIND·실행 후보·조각은 차단한다.

```bash
source /opt/ros/jazzy/setup.bash
source "$C2_DSR_WS/install/local_setup.bash"
source "$C2_REPO/ws_cobot_pjt/ws_cobot1/install/local_setup.bash"
cd "$C2_REPO"
python3 ws_cobot_pjt/run_monitor.py \
  --transport ros --mode REAL --ros-domain-id 20 \
  --preparation-config ws_cobot_pjt/ws_cobot1/src/c2_process/config/workpiece_real_trial_0921.json \
  --execution-profile ws_cobot_pjt/ws_cobot1/src/c2_process/config/real_execution_profile_20260923.json
```

`run_monitor.py`는 HMI·FastAPI와 필요할 때 `c2_path` 노드를 시작한다. 두산
드라이버와 `real_process_node`는 시작하지 않는다. 이미 같은 ROS domain에서
`c2_path`가 실행 중이면 `--external-path-node`를 사용해 중복 기동을 막는다.

## REAL 공정 노드

공정 노드는 backend가 기동되고 외부 드라이버·제어권 토픽이 준비된 뒤 별도
터미널에서 시작한다. 저널 파일은 기존 기록을 보존할 전용 디렉터리에 둔다.

```bash
source /opt/ros/jazzy/setup.bash
source "$C2_DSR_WS/install/local_setup.bash"
source "$C2_REPO/ws_cobot_pjt/ws_cobot1/install/local_setup.bash"
mkdir -p "$C2_RUNTIME_DIR"

ros2 run c2_process real_process_node \
  --preparation-backend-url http://127.0.0.1:8010 \
  --preparation-journal-path "$C2_RUNTIME_DIR/preparation.sqlite3" \
  --execution-journal-path "$C2_RUNTIME_DIR/execution.sqlite3" \
  --controller-prefix /dsr01/dsr_controller2
```

namespace remap을 추가해 서비스 prefix와 제어권 토픽을 이중 변경하지 않는다.
기본 제어권 토픽은 `<controller-prefix>/control_authority`다.

## 데이터·재시작·다음 날 운용

- 기본 데이터는 `ws_cobot_pjt/backend/monitor_data`에 있으며 Git에서 제외한다.
  백업은 서버를 정상 종료한 뒤 디렉터리 전체를 복사한다.
- 측정 원본·설정·경로 파일은 ID와 SHA-256으로 저장되지만 BIND는 살아 있는 공정
  노드의 현재 측정·상태·제어권에도 묶인다. 노드 재시작 후 파일만으로 BIND를
  자동 복구하지 않는다.
- 진행 중 PRECHECK·측정·조각의 pause/resume은 구현돼 있지 않다. 다음 날 이어서
  시작하려면 확인된 정지 상태에서 새 MEASURE → BIND → 경로 생성 → 미리보기 →
  별도 실행 요청 순서를 다시 수행한다.
- `TIMEOUT`, 통신 상실, 보호정지, 정지 미확인은 자동 재시도하지 않는다. 현재 위치와
  실제 정지를 확인하기 전 새 모션을 요청하지 않는다.
- HMI에서 미확인 실행을 처음부터 다시 시작할 때는 읽기 전용 제어기 검사로
  STANDBY·motion_status=0·REAL/AUTO·현재 관절·TCP 좌표를 다시 확인한다.
  재시작 직후 빈 문자열일 수 있는 TCP/load 이름은 이 무동작 해제에서 제외하고,
  새 준비·실행 직전 검사에서 등록 TCP/load를 다시 확인한다.
  통과하면 이전 준비 BIND와 경로 실행 승인을 폐기하므로 새 MEASURE부터 수행한다.

## 로봇 없이 확인

```bash
cd "$C2_REPO"
python3 tools/check_repository.py
python3 tools/test_git_hooks.py
python3 tools/issue_manager.py
python3 tools/test_issue_manager.py

cd "$C2_REPO/ws_cobot_pjt/backend"
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=. .venv/bin/pytest -q

cd "$C2_REPO/ws_cobot_pjt/ws_cobot1/src/c2_process"
../../../backend/.venv/bin/pytest -q
```

빌드·모의시험 통과는 실제 M0609의 충돌·정지·측정 정확도·가공 품질 합격이 아니다.
