# ws_dsr · 외부 로봇·그리퍼 실행환경

이 디렉터리는 수업 지정 `cobot_rg2` 전체 소스를 PC별로 준비하는 외부
워크스페이스다. 전체 `src/`는 기본 Git 제외이며 C-2는 제어권 관측 패치 4개 파일만
예외적으로 추적한다. 네 파일만으로 `dsr_msgs2`·`dsr_controller2`를 빌드할 수 없다.

2026-09-30 이 checkout에는 외부 `src/.git`과 전체 패키지가 없고 `colcon list`도
비어 있다. 현재 PC에서 조회되는 `dsr_msgs2`·`dsr_controller2`·`dsr_hardware2`는
checkout 밖의 기존 설치 overlay에서 온다. 따라서 현재 셸에서 패키지가 보인다는
사실을 이 checkout의 재현 가능한 드라이버 빌드로 기록하지 않는다.

## 준비 원칙

- 새 PC는 [의존성 기록](../../docs/DEPENDENCIES.md)의 승인 원본 전체를 별도
  `ws_dsr/src`에 준비하고 정확한 커밋과 로컬 변경을 기록한다.
- 기존 실행 PC의 외부 `.git`, 로컬 수정, build/install/log를 C-2의 부분 파일로
  덮어쓰거나 초기화하지 않는다.
- 공식 `doosan-robot2` Jazzy와 수업 지정 `cobot_rg2` 설치본을 같은 워크스페이스에
  중복 배치하지 않는다.
- 팀이 만드는 `c2_interfaces`, `c2_path`, `c2_process`는 옆의 `ws_cobot1/src`에서
  관리한다. `ws_dsr/src`에 팀 코드를 추가하면 C-2 PR로 공유되지 않는다.
- 그리퍼·드릴·브링업 명령은 실제 설치 원본과 현장 배포 절차를 따른다. 확인하지
  않은 launch 파일·IP·모드를 이 문서에서 만들지 않는다.

## 제어권 관측 패치

추적 파일은 다음 네 개다.

- `doosan-robot2/dsr_controller2/include/dsr_controller2/dsr_controller2.hpp`
- `doosan-robot2/dsr_controller2/src/dsr_controller2.cpp`
- `doosan-robot2/dsr_hardware2/include/dsr_hardware2/control_authority_observation.hpp`
- `doosan-robot2/dsr_hardware2/src/dsr_hw_interface2.cpp`

적용 전에 설치한 외부 원본과 diff를 검토한다. 파일 전체를 다른 버전에 무조건
덮어쓰지 않는다. 빌드·토픽 계약은
[제어권 관측 문서](../docs/CONTROL_AUTHORITY_TOPIC.md)를 따른다.

## source 순서

PC마다 외부 워크스페이스 위치가 다르므로 변수로 지정한다.

```bash
export C2_DSR_WS="외부_cobot_rg2_워크스페이스_절대경로"
source /opt/ros/jazzy/setup.bash
source "$C2_DSR_WS/install/local_setup.bash"
source ws_cobot_pjt/ws_cobot1/install/local_setup.bash

ros2 pkg prefix dsr_msgs2
ros2 pkg prefix dsr_controller2
```

설치·빌드·HMI·공정 노드의 전체 순서는
[로컬 실행환경](../../docs/LOCAL_ENVIRONMENT.md)을 따른다. 외부 소스의 일반 원칙과
확인 양식은 [워크스페이스 가이드](../../docs/WORKSPACES.md)에 있다.
