# 현재 개발·검증 현황

> 기준: 2026-09-30 [PR #99](https://github.com/suuuhululu/C-2/pull/99)
> head `3d882f6` (`origin/main` `d17a2f6` + `main_v11` `1c956f7` 통합).
> 원격 `main`에 두 PR이 병합되기 전에는 설치 PC와 이 기준이 같다고 가정하지 않는다.

## 현재 코드

| 영역 | 구현 | 검증 경계 |
| --- | --- | --- |
| 공통 계약 | `PrepareWorkpiece`, `GeneratePath`, `ExecuteProcess` Action, `StopProcess` Service, `ProcessState`, `ProcessEvent` Message | 고정 드릴 `schema_version=2`. 모든 ROS 프로세스가 같은 checkout의 생성 타입을 사용해야 한다. |
| HMI·서버 | React HMI, FastAPI·SQLite, 관리 자산 ID/SHA-256, MOCK/ROS SIM/REAL 준비·경로·별도 실행·정지·이력 | HTTP 접수와 ROS Goal 수락, 실제 모션 완료, 가공 품질은 서로 다른 상태다. |
| 경로 | PNG/JPEG→2D 중심선/해칭→원통 3D 도구 끝 경로, 미리보기·기하 보고서, 조건부 REAL 실행 후보 | 경로 노드는 모션을 실행하지 않는다. 후보 표시는 공정 PRECHECK나 실제 충돌 검사를 대신하지 않는다. |
| 공정 | MEASURE/BIND, 상태·제어권 관측, PRECHECK, 검사된 ENTRY·ENGRAVE·RETURN_HOME, 정지·상태·이벤트 | 실패·보호정지·정지 미확인 뒤 자동 HOME·재시작을 하지 않는다. |
| 실행기 | `run_monitor.py`가 HMI·서버·필요시 경로 노드를 시작 | 외부 두산 드라이버와 `real_process_node`는 별도 기동한다. |

REAL 또는 승인된 entry 활성 흐름은 다음과 같다.

`MEASURE → 측정 원본 저장 → BIND_SNAPSHOT → GeneratePath → 미리보기 → 별도 ExecuteProcess → PRECHECK → ENTRY → ENGRAVE → RETURN_HOME → FINISH`

entry 비활성 호환 흐름에서는 `ENTRY`와 `RETURN_HOME` 콜백이 생략될 수 있다.
고정 드릴을 철사로 장착한 동안 그리퍼 열기, 자동 집기·반납·청소는 없다. 화면의
드릴 ON 확인은 전원 센서나 자동 드릴 제어가 아니다.

## main_v11 통합 동작

- 탐색 명령 전 `UNSTABLE_BASELINE`이고 PROBE 명령 미전송과 시작점 유지가
  확인되면 이동·IK 재검사 없이 기준선만 다시 수집한다.
- 실제 탐색 이동 뒤 `CONTACT_NOT_FOUND`·`CONTACT_OUT_OF_RANGE`가 발생하면 정지
  확인과 검사된 방사선 후퇴 뒤 같은 점만 제한 횟수 안에서 다시 측정한다.
- 힘 한계, 통신 상실, 보호정지, 정지 미확인은 자동 재시도하지 않는다.
- 옆면 8점은 한 번씩만 측정한다. 전체 fit 실패 시 최대 한 점을 제외한 7점 중
  기존 품질 조건을 통과하는 유일한 해만 사용하고 FIT 단계에서 다시 움직이지 않는다.
- 같은 MEASURE 요청의 확인된 `FAILED/TIMEOUT`은 HMI 재연결 뒤 성공이나 새 측정으로
  바꾸지 않고 확인된 실패로 복구한다.
- 최신 `main`의 HMI 경로 표시, PRECHECK IK 궤적 재사용, HOME 작업영역 검사는
  유지했다.

공통 ROS 필드·좌표계·단위는 변경하지 않았다. 상세 계약은
[인터페이스](../ws_cobot_pjt/docs/INTERFACE_RECOMMENDATION.md), 실행환경은
[로컬 환경](LOCAL_ENVIRONMENT.md)을 따른다.

## 확인한 시험

PR #99 head `3d882f6`, Ubuntu 24.04, Python 3.12.3, ROS 2 Jazzy, 로봇 미연결:

- `c2_process`: `1057 passed, 5 skipped`
- Backend: `246 passed, 5 skipped`
- 측정·ENTRY·HOME 통합 충돌 구간 표적 시험: `68 passed`
- `colcon build --packages-select c2_process --symlink-install`: 성공

이 문서 브랜치에서 추가로 확인한 항목:

- Node 18.19.1·pnpm 11.25.0, 고정 lockfile로 TypeScript/Vite build: 성공
- Node 24.19.0 preview 시험: 5건 통과. 시스템 Node 18은 해당 시험의
  `--experimental-strip-types` 옵션을 지원하지 않음
- 저장소 검사 272개 파일, Git hook 8건, Issue 도구 시험 27건, diff 공백 검사: 통과
- `run_monitor.py`, `real_process_node`의 `--help`와 문서 인자: 일치

2026-09-23에는 측정→BIND→경로→PRECHECK→ENTRY→55구간 실행→FINISH 원장을
확보했다. 이는 당시 코드·설정의 통합 실행 기록이며 조각 형상·깊이·반복 품질 합격은
아니다. [기록](../ws_cobot_pjt/docs/validation/2026-09-23-first-real-integration.md)

## 남은 확인

1. PR #99 코드로 실제 M0609의 기준선 무이동 재시도, 탐색 후 후퇴, 한 점 제외 fit을
   반복 확인한다.
2. 실행 PC의 외부 `cobot_rg2` 정확한 커밋과 로컬 수정, 제어권 패치 4개 적용,
   `dsr_msgs2` 타입을 기록한다. 현재 checkout에는 전체 외부 원본이 없다.
3. 같은 ID·해시의 최종 경로에 대해 접근·이탈·HOME, 관절 경계, 정지 시간을 현장에서
   검증한다.
4. 작은 조각의 깊이·선폭·오류 복구를 반복 측정하고 커밋·설정·원본 해시를 남긴다.
5. 전체 링크의 연속 충돌, 힘 유지 중 중간 자세 관절 연속성은 구현·검증 완료로
   표시하지 않는다.
6. 기존 `frontend/src/monitor/Monitor.tsx`의 Prettier 불일치는 기능 변경과 분리해
   정리한다. 현재 TypeScript/Vite build 실패는 아니다.

진행 중 공정을 다음 날 이어가는 pause/resume 계약은 없다. BIND는 현재 공정 노드의
측정·상태·제어권에 묶이므로 재시작 뒤 자동 복구하지 않는다.

## GitHub 관리 상태

- Issue #35는 이미 구현된 `c2_path` 패키지를 TODO로 남긴 오래된 관리 항목이다.
- Issue #19는 9/18 기록 파일이 존재하지만 TODO로 남은 역사 기록 항목이다.
- PR #98은 자동 다중 IK 후보 전환 전의 실험 PR로 현재 기준에 포함되지 않는다.
- PR #99가 코드 버전 통합, 그 위의 문서 PR이 현재 안내 정리다.

파일별 결과와 처리 기준은 [main_v11 점검](MAIN_V11_AUDIT.md)에 기록한다. 날짜별
`daily/`, `validation/`, `evidence/` 문서는 해당 날짜·커밋의 근거이며 현재 실행
지침의 우선 출처가 아니다.
