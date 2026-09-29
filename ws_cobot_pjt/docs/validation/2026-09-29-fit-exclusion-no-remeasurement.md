# 실측 이상점 계산 제외 및 FIT 추가 재측정 제거

- 기준: `origin/main_v11` / `1c956f743e155bc4cfd188171f32437962f4090e`.
- 브랜치: `codex/main-v11-local-20260929`, 로컬 미커밋 변경. push/PR/병합 없음.
- 사용자 확정: 재측정 허용이 아니라 **이상점을 제외하고 계산**. 8점 취득 후 이전 점으로
  돌아가는 추가 재측정 모션을 제거한다. 측정 중 기준 힘/접촉 오류의 기존 제한 재시도와 구별한다.
- 계약 근거·전환: [PrepareWorkpiece](../PREPARE_WORKPIECE_ACTION.md),
  [양초 측정](../../ws_cobot1/src/c2_process/WORKPIECE_CALIBRATION.md).

## 발생 원인

이전 변경은 정상 7점 후보가 중심 판정을 통과하게 했지만 기존 FIT 재측정 분기로 연결했다.
요청 `5be9e2f7-355f-4464-bcc8-644ce6eed10e`의 실제 기록에서 318.511초에 재측정,
335.484초에 6번 재접촉 시작, 353.072초에 취득 완료, 357.075초에 다시 재측정을 시도했다.
360초 전체 제한에서 `FAILED/TIMEOUT`, 제어 Result `stop_confirmed=true`로 종료됐다.
이는 사용자 요청을 잘못 해석한 변경이다. 시간 제한을 늘려 재측정을 계속하도록 만들지 않는다.

## 최종 동작

1. 옆면 8점을 모두 취득하고 마지막 점의 기존 후퇴를 마친다.
2. 8점 원 맞춤이 기준을 만족하면 그대로 사용한다.
3. 현장 입력의 `fit_outlier_max_exclusions=1`이면 한 점씩 제외한 7점 후보를 계산한다.
   기존 잔차·반지름·중심·높이 조건을 만족하고 제외점이 잔차 한계 밖인 후보가
   정확히 하나일 때 그 원을 사용한다. 최대 1점이며 6번/8번을 하드코딩하지 않는다.
4. 추가 PROBE/점 재방문 없이 기존 측정 완료 후 홈 복귀·정지 확인으로 이어진다.
   후보 없음/중복/2점 이상 이상은 실패한다. 실패 후 자동 홈은 추가하지 않는다.

원본 8점은 삭제하거나 가상의 값으로 바꾸지 않는다. 내부 measurement에
`fit_used_point_indices`, `fit_excluded_point_indices`, 제외점 잔차와 8점 fit을 보존한다.
ROS v2 Result의 원본 접촉 배열 9개(윗면 포함)는 유지한다. `message`에는 제외 번호와
7점 계산임을 명시하며 잔차 필드는 채택한 7점 fit 값이다. HMI 원본 저장과 BIND는 동일한
Result를 해시로 연결하고 경로는 그 중심·반지름을 사용한다. ROS 필드·타입 변경은 없다.

중심 판정은 기존 탐색 양쪽 여유 안에서 실측 반지름 오차+허용 잔차를 예약하는 계산을
사용한다. 관절·힘·정지·탐색 거리·속도·360초 전체 제한과 잔차 0.3/0.6 mm는 유지한다.
새 입력 설정은 불변 설정 원본으로 새로 등록하며 이전 측정 설정/기록은 보존한다.

## 실제 좌표의 오프라인 계산

| 기록 | 제외점 | 7점 RMS | 7점 최대 잔차 | 반지름 |
| --- | --- | --- | --- | --- |
| 최초 8점 실패 `4b26a240-5189-47c3-8c25-414a52de48c9` | 6 | 0.087764 mm | 0.159868 mm | 34.143146 mm |
| TIMEOUT 최종 원본 `a58477ac-26f0-4cdb-b7ac-5db56219b8b8` | 6 | 0.090615 mm | 0.178611 mm | 34.094541 mm |

TIMEOUT 원본 SHA-256: `f8bf057f9f520b37a65612e883b3f362aa68b422eb3ee5e4ac3ccc065a292d20`.
두 결과는 저장 좌표 재계산이며 새 로봇 측정·실제 가공 정밀도 검증이 아니다.

## TIMEOUT 상태 처리

HMI는 취소가 설정된 뒤 `STOPPED`가 아닌 Result를 모두 UNKNOWN으로 취급했다.
이 때문에 제어 노드의 `FAILED/TIMEOUT/stop_confirmed=true`도 미확인으로 잘못 남았다.
동일 MEASURE의 요청·준비·측정·설정 ID/해시·모드가 일치하는 최종 TIMEOUT과
명시적 정지 확인만 `FAILED`로 분류한다. 늦은 성공·정지 미확인·다른 요청은 계속 차단한다.

HMI 시작 시 UNKNOWN 기록에 저장된 원본 Result를 파일 해시로 검증해 위 조건을
만족할 때만 확정 실패로 정리하고 이전 상태와 원본 참조를 감사 필드에 보존한다.
실패를 성공으로 바꾸거나 측정/모션을 자동 시작하지 않는다. 기록·원장 삭제 없음.

## 적용

검증 결과:

- 전체 공정 시험: 1,044 통과, 환경 조건부 5 제외.
- 전체 백엔드 시험: 245 통과, 환경 조건부 5 제외. 마지막 해시 누락 방어 추가 후
  TIMEOUT 복구 시험 10개 별도 통과. pytest 외부 플러그인은 비활성화한 명령으로 수행했다.
- 실제 TIMEOUT 원본을 임시 저장소에 복사한 재현: 원본 해시 일치,
  UNKNOWN→FAILED, 정지 확인 보존, 모션/실제 DB 수정 없음.
- Jazzy `c2_process` 빌드 성공. `install/main_v11`이 수정 Python 소스를 참조함을 확인.
  현장 JSON은 설치 share 경로가 아니라 HMI 명령의 명시적 소스 경로로 읽는다.
- 저장소 검사, Git hook 8개, Issue 도구 27개 및 diff 공백 검사 통과.

로그: `/tmp/c2-v11-fit-exclusion-process-tests.log`,
`/tmp/c2-v11-fit-exclusion-backend-tests.log`, `/tmp/c2-v11-fit-exclusion-build.log`.

새 코드·설정은 빌드 뒤 **공정 노드와 HMI를 각각 기존 터미널에서 재시작**해 적용한다.
기존 `/tmp/c2-main-v11-real-4` 데이터와 `install/main_v11` overlay를 그대로 사용한다.
드라이버 재시작·그리퍼 조작·보호정지 자동 해제는 필요하지 않으며 수행하지 않았다.
이 수정 작업 중에는 모션 호출이나 실제 실행 프로세스 재시작을 하지 않았다.

기존 ROS 환경이 설정된 터미널 3(공정), 2(HMI)를 `Ctrl+C`로 종료한 뒤,
터미널 2에서 다음을 실행한다.

```bash
cd /home/rokey/cobot1
C2_MONITOR_DATA=/tmp/c2-main-v11-real-4 \
python3 ws_cobot_pjt/run_monitor.py --transport ros --mode REAL --ros-domain-id 20 \
  --preparation-config "$PWD/ws_cobot_pjt/ws_cobot1/src/c2_process/config/workpiece_real_trial_0921.json" \
  --execution-profile "$PWD/ws_cobot_pjt/ws_cobot1/src/c2_process/config/real_execution_profile_20260923.json"
```

터미널 3에서는 다음을 실행한다.

```bash
cd /home/rokey/cobot1
source ws_cobot_pjt/ws_cobot1/install/main_v11/local_setup.bash
ros2 run c2_process real_process_node \
  --preparation-backend-url http://127.0.0.1:8010 \
  --preparation-journal-path /tmp/c2-main-v11-real-4/preparation.sqlite3 \
  --execution-journal-path /tmp/c2-main-v11-real-4/execution.sqlite3 \
  --controller-prefix /dsr01/dsr_controller2
```
