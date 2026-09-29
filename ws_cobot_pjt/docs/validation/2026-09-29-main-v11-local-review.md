# main_v11 로컬 정렬·측정 재시도 검토

- 날짜/검토: 2026-09-29, Codex 로컬 코드 검토. 사람의 승인·실기 검증을 대신하지 않는다.
- 기준/결과 HEAD: `origin/main_v11`, `1c956f743e155bc4cfd188171f32437962f4090e`.
- 작업 위치: `/home/rokey/cobot1`, 브랜치 `codex/main-v11-local-20260929`.
  `main_v11`은 다른 worktree에서 사용 중이므로 같은 커밋을 추적하는 로컬 브랜치를 만들었다.
- 사용자 지시: 작동하지 않는 main 대신 main_v11 유지. main의 변경은 병합하지 않았다.
- 관련 이력: PR #99의 단일 목표 재검사 방식과 v11의 CPU 부하 감소를 유지한다.
  공개 ROS v2 Action 3개·Service 1개·Message 2개는 변경하지 않았다.
- 결과는 위 HEAD에 로컬 미커밋 수정으로 남겼으며 commit/push/PR/병합은 수행하지 않았다.

## 변경과 재현

이후 실측 8점 실패와 사용자 판정 완화 요청에 따른 중심 판정 변경은
[후속 검증 기록](2026-09-29-measurement-fit-center-margin.md)에 별도로 기록했다.
아래 재시도 수정 당시의 설정·시험 결과와 구분한다.

1. 원격 v11에서는 정지 기준 힘 실패에도 retract/approach의 IK를 다시 호출했다.
   다른 IK 해가 관절 한계를 넘도록 한 모의 회귀시험이 구형 접촉 창/현행 탐색 모드 모두
   `JOINT_LIMIT`로 실패했다. 기존 공정 시험 1,025개 통과만으로 이 문제를 찾지 못했다.
2. `measurement_robot_adapter.py`는 탐색 명령을 보내기 전의 기준 힘 실패에만
   내부 예외의 `probe_command_sent=False`를 기록한다. 이동 중에도 같은 오류명이 나오므로
   오류명만으로 무이동을 추정하지 않는다.
3. `workpiece_calibration.py`는 위 증거와 실제 정지, 시작점 위치·자세를 확인한 경우
   MOVE/IK 재검사 없이 PROBE의 기준 힘을 다시 수집한다. 이동했거나 증거가 없으면
   기존 방사선·정지·단일 구간 검사를 거쳐 후퇴한다. 후퇴 완료 뒤 같은 시작점으로 보내던
   중복 approach만 제거하며, PROBE가 새 기준 힘 수집과 재접근을 수행한다.
4. 힘/통신/보호정지/정지 미확인 오류, 취소, 재시도 횟수 제한, 다음 점 진입 차단은 유지한다.
   테스트의 후퇴 실패는 실제 탐색 후 실패에 주입하도록 수정했다.

다른 작업 폴더에 있던 관절 범위 확대, 관절 판정 ±0.1° 추가,
힘 안정성·원 맞춤 허용치 확대, 중심 판정 5 µm 여유, 전체/통신 시간 제한 변경은
이번 원인 수정에 포함하지 않았다. 준비·실행 JSON, HOME 복귀, HMI 및 드라이버 소스는
main_v11 원본 그대로다. 해당 폴더의 작업 자체를 삭제하거나 덮어쓰지 않았다.

## 수행한 검사

| 수준/검사 | 결과 |
| --- | --- |
| 원격 v11 기존 공정 시험 | 1,025 통과, 5 제외 |
| 수정 후 전체 공정 시험 | 1,030 통과, 5 제외 |
| 최종 로컬 측정 재시도 시험 | 22 통과, 검토한 최소 수정본으로 재확인 |
| 백엔드 전체 시험 | 236 통과, 5 제외; 의존성 경고 1개 |
| 경로 패키지 시험 | 237 통과 |
| Jazzy c2_interfaces·c2_path·c2_process 빌드 | 3개 성공 |
| 생성 ROS 타입 직렬화/기본값 시험 | 18 통과; colcon 집계는 CTest 항목 포함 19 |
| 프런트엔드 TypeScript/Vite 빌드 | 성공 |
| HMI 실제 HTTP 기동 | 별도 임시 MOCK DB/포트에서 snapshot·operator·docs 모두 200, 종료 완료 |
| 준비/실행 JSON 교차 정적 검사 | main_v11 원본으로 통과, 파일 수정 없음 |
| 저장소 검사·hook 8개·Issue 도구 27개·diff 공백 검사 | 통과, Issue 네트워크/변경 없음 |
| 설치본 확인 | 새 overlay에서 수정된 원본 Python을 참조함; REAL CLI --help 확인 |

ROS 네트워크 통합 등 명시 활성화가 필요한 시험은 제외했다. 새 REAL 노드 기동,
드라이버 재시작, 로봇 모션·그리퍼·힘 명령은 수행하지 않았다. 실제 로봇의 IK 해 선택,
후퇴/재접근·정지 시간·가공 품질은 현장 검증이 남아 있다.

시험 환경은 Ubuntu Python 3.12.3/ROS 2 Jazzy이며 Python 시험은 기존 backend venv를 사용했다.
이 PC의 Node는 18.19.1/npm 9.2.0이고 실제 빌드는 통과했다. README의 새 PC 권장 Node 22와는 다르다.
검토용 worktree에서 시험한 변경 파일과 현재 작업 파일의 바이트 일치를 확인했다.

외부 실행환경 `/home/rokey/ws_cobot_pjt/ws_dsr/src`는 cobot_rg2
`4d5657f36a160eedb533ab1c975cd8a30c3e53b2`에 로컬 변경이 있다.
팀 추적 드라이버 4개 파일 중 3개는 같고 `dsr_controller2.cpp`는 상태 조회 로그의
INFO→DEBUG 한 줄이 다르다. 그 외 공급자 변경과 설치물은 보존했으며 재빌드하지 않았다.

## 보존 위치

- 이전 브랜치/HEAD: `codex/reduce-real-driver-polling-20260929`, `d17a2f6`.
- 이전 작업 stash: `35edb695d7010bf3bc449acf1fc449a8aaea64e9`.
- 별도 파일 백업과 시험 로그:
  `/home/rokey/cobot1-backups/before-main-v11-20260929-205017`.
- 백업에는 추적 변경 patch, staged patch, 미추적 파일 73개 tar, 원래 상태와 stash ID가 있다.
- `/home/rokey/cobot1-main-v9-cpu-fix`의 미커밋 변경은 보존했다. 작업 시작 당시 이 폴더의
  HMI·공정 및 외부 드라이버 프로세스가 있었으나 로봇이 움직인다는 의미로 해석하지 않는다.
  사용자 후속 설명과 최종 프로세스 조회 시 해당 실행 프로세스가 종료된 상태를 확인했다.

## 이 PC에서 실행

아래 세 터미널을 사용한다. 이미 같은 프로세스를 다시 켰다면 중복 기동하지 않는다.
기존 HMI 데이터·준비·실행 원장은 `/tmp/c2-main-v11-real-4`를 그대로 사용하며 삭제/초기화하지 않는다.
UNKNOWN/미확인 정지를 새 DB로 우회하지 않는다. 이 경로는 이번 세션의 확인값이며 재부팅 뒤
사라졌다면 빈 원장을 만들지 말고 기존 기록을 복구·확인한다.

각각 새 터미널에서 다음 공통 환경을 설정한다. 이전 `install/local_setup.bash` 대신
이번에 별도로 빌드한 `install/main_v11/local_setup.bash`를 사용한다.

```bash
cd /home/rokey/cobot1
source /opt/ros/jazzy/setup.bash
source /home/rokey/ws_cobot_pjt/ws_dsr/install/local_setup.bash
source ws_cobot_pjt/ws_cobot1/install/main_v11/local_setup.bash
export ROS_DOMAIN_ID=20
export ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST
export ROS_STATIC_PEERS=''
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp
```

터미널 1 — 기존 설치 드라이버(이번 작업에서는 실행하지 않고 명령만 제공):

```bash
ros2 launch m0609_rg2_bringup bringup.launch.py \
  mode:=real host:=192.168.1.100 port:=12345
```

이 명령의 주소·포트는 이번 세션의 기존 실행 명령과 설치 launch에서 확인한 값이다.
별도 그리퍼 개폐 서비스나 초기화 명령을 호출하지 않는다.

터미널 2 — HMI·경로 노드:

```bash
test -f /tmp/c2-main-v11-real-4/monitor.sqlite3 && \
C2_MONITOR_DATA=/tmp/c2-main-v11-real-4 \
python3 ws_cobot_pjt/run_monitor.py --transport ros --mode REAL --ros-domain-id 20 \
  --preparation-config "$PWD/ws_cobot_pjt/ws_cobot1/src/c2_process/config/workpiece_real_trial_0921.json" \
  --execution-profile "$PWD/ws_cobot_pjt/ws_cobot1/src/c2_process/config/real_execution_profile_20260923.json"
```

터미널 3 — 공정 노드:

```bash
test -f /tmp/c2-main-v11-real-4/preparation.sqlite3 && \
test -f /tmp/c2-main-v11-real-4/execution.sqlite3 && \
ros2 run c2_process real_process_node \
  --preparation-backend-url http://127.0.0.1:8010 \
  --preparation-journal-path /tmp/c2-main-v11-real-4/preparation.sqlite3 \
  --execution-journal-path /tmp/c2-main-v11-real-4/execution.sqlite3 \
  --controller-prefix /dsr01/dsr_controller2
```

화면: `http://127.0.0.1:5174/operator`. 기동과 측정·조각 실행은 별개다.
현장 설정·장치 상태를 확인한 뒤 HMI에서 새 준비/측정→BIND→경로→미리보기→별도 실행 순서를 따른다.
이 명령은 소스·설정·설치 경로를 맞춘 것이며 실제 로봇에서 문제없다는 승인 명령이 아니다.

로봇 없이 화면만 확인하려면 8010/5174 포트가 비어 있는 상태에서 저장소 루트에서 실행한다.

```bash
python3 ws_cobot_pjt/run_monitor.py --transport mock --mode SIMULATION
```

원격 main_v11에는 이번 수정이 아직 없다. 로컬 변경을 보존하고 동료 검토 후 별도로 제출한다.
main의 HOME 복귀 수정 미포함에 따른 작업영역 판정 차이는 남아 있으며,
이번에는 사용자 지시에 따라 v11의 HOME 복귀 구현을 변경하지 않았다.
