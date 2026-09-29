# main_v11 기준 저장소·GitHub 점검

> 점검일: 2026-09-30. 코드 기준은 `origin/main` `d17a2f6`에
> `main_v11` `1c956f7`의 동작과 현장 측정 수정분을 통합한
> [PR #99](https://github.com/suuuhululu/C-2/pull/99) head `3d882f6`이다.
> 이 문서 PR은 PR #99 위에 쌓인 문서 전용 변경이다. 두 PR이 순서대로 병합되기
> 전에는 원격 `main`이 이 기준과 같다고 표시하지 않는다.

## 점검 결론

- 공통 ROS 계약은 고정 드릴 `schema_version=2`를 유지한다. Action 3개,
  Service 1개, Message 2개의 이름·필드·단위는 PR #99에서 바뀌지 않았다.
- 최신 `main`의 HMI 경로 표시, PRECHECK IK 궤적 재사용, 조각 후 검사된 HOME
  복귀는 유지했다. `main_v11`의 상태 관측 부하 축소와 측정 복구를 그 위에
  적용했다.
- 움직이기 전 `UNSTABLE_BASELINE`은 시작점과 명령 미전송이 확인될 때 이동 없이
  기준선만 다시 수집한다. 실제 탐색 이동 뒤의 접촉 실패만 정지 확인과 검사된
  방사선 후퇴를 거친다.
- 옆면 8점은 한 번씩 측정한다. 전체 fit 실패 시 최대 한 점을 제외한 7점 중 기존
  잔차·반지름·중심 범위를 통과하는 유일한 해만 사용하며 FIT 단계에서 재측정하지
  않는다.
- 백엔드가 같은 MEASURE 요청의 `FAILED/TIMEOUT`과 `stop_confirmed=true`를 저장
  결과로 확인하면 재연결 뒤 확인된 실패로 복구한다. 성공이나 새 모션으로
  바꾸지는 않는다.

## 수정한 문서 불일치

| 발견 내용 | 코드 근거 | 문서 조치 |
| --- | --- | --- |
| 루트·협업·인터페이스 문서가 `6536a29` 또는 `987a3b7`을 현재 기준으로 표시 | 원격 `main=d17a2f6`, PR #99=`3d882f6` | 현재 문서의 기준을 PR #99 통합 기준으로 통일 |
| 백엔드·프런트 README가 REAL 경로·준비·조각을 미연결 또는 차단으로 설명 | `run_monitor.py`, `PreparationService`, `RosBridge`, `real_process_node` | 현재 MOCK/ROS SIM/REAL 실행 조건으로 다시 작성 |
| ROS 소스 README가 `c2_path`·`c2_process` 노드와 패키지를 미구현으로 표시 | 두 패키지의 `package.xml`, `setup.py`, 노드 entry point 존재 | 실제 세 패키지와 책임을 표시 |
| 측정 문서가 준비 Action 수신부를 미구현으로 표시 | `PrepareWorkpiece.action`, `preparation_action.py`, `node.py` | 구현 상태와 실기 검증 경계를 분리 |
| 설정 문서가 YAML 후보를 현행 입력처럼 반복 설명 | 실제 로더는 준비 JSON과 실행 프로파일 JSON 사용 | 존재하지 않는 YAML 안내를 제거하고 실제 파일을 원본으로 지정 |
| 백엔드 설치가 기본 lock만 설치하도록 안내 | 기본 이미지 흐름이 `c2_path`의 scikit-image·networkx를 사용 | 새 환경은 `requirements-image.lock.txt` 사용 |
| 프런트 Node 요구 범위가 불명확 | Node 18.19.1로 TypeScript/Vite build 통과. `--experimental-strip-types` preview 시험은 Node 24.19.0에서 5건 통과 | build와 Node 22+ 시험 조건을 구분하고 lockfile 사용을 명시 |

날짜가 붙은 `daily/`, `validation/`, `evidence/`, 설계안과 시행착오 문서는 해당
날짜의 증거라서 커밋 번호와 당시의 미완료 표현을 바꾸지 않는다. 현재 상태를
설명하는 문서에서 그 기록을 우선 지침으로 인용하지 않도록 길잡이와 배너를
정리했다.

## GitHub 미결 항목

| 항목 | 점검 결과 | 조치 |
| --- | --- | --- |
| Issue #35 `c2_path ROS 패키지 반영` | 패키지·노드·이미지 변환·시험이 이미 저장소에 있다. 체크박스와 `status:todo`가 오래됐다. | 구현 누락으로 취급하지 않는다. 담당자가 결과 PR/검증 링크를 확인해 완료 처리할 관리 항목으로 남긴다. |
| Issue #19 `9/18 실기 기록` | 일지·evidence·`LESSONS_ROBOT.md`는 존재한다. 미검증 물결 시험은 현재 고정 드릴 공정의 완료 조건이 아니다. | 역사 기록 이슈로 분류하거나 닫을 관리 항목이다. 과거 좌표를 현재 승인값으로 사용하지 않는다. |
| PR #98 다중 IK entry trial | 아직 열린 실험 PR이며 PR #99 또는 `main_v11` 기준에 포함되지 않았다. | 공급자 Cartesian solution-space 보장과 실기 시험 전 자동 후보 전환으로 병합하지 않는다. |
| PR #99 main_v11 버전 통합 | 이 문서 PR의 선행 변경이다. | 먼저 검토·병합하고 문서 PR을 뒤따라 병합한다. |

이 점검은 이슈를 자동으로 닫거나 PR #98을 병합하지 않는다. GitHub 표시를 코드
완료 상태와 일치시키는 최종 상태 변경은 각 항목 담당 검토와 함께 수행한다.

## 실제로 남은 기술·현장 검증

1. PR #99 코드로 실제 M0609에서 움직이기 전 기준선 재시도가 모션·IK를 만들지
   않는지, 탐색 후 실패만 검사된 후퇴를 수행하는지 확인해야 한다.
2. 8점 중 한 점 제외 fit의 물리적 타당성, 반복성, 실제 제외 점과 측정 원본을
   확인해야 한다. 두 점 이상 이상치는 계속 실패해야 한다.
3. 저장소 checkout 안의 `ws_dsr/src`에는 전체 외부 원본이 없다. 이 PC에서 보이는
   `dsr_msgs2`·`dsr_controller2`는 별도 설치 overlay에서 왔으므로 정확한 소스
   커밋과 4개 제어권 패치 적용 여부를 기록해야 한다.
4. BIND는 공정 프로세스의 현재 상태·제어권·관측 유효성에 묶인다. 관측 만료나
   공정 노드 재시작 뒤 저장 파일만으로 자동 복구하지 않는다.
5. 진행 중 PRECHECK·측정·조각을 다음 날 이어가는 pause/resume 계약은 없다. 정상
   종료 또는 확인된 정지 뒤 새 준비부터 시작해야 한다.
6. 명시 waypoint IK·관절·단순 작업영역 검사는 있지만 전체 로봇 링크의 연속 충돌,
   힘 유지 중 모든 중간 자세의 관절 연속성, 반복 가공 품질은 실기 합격 상태가
   아니다.
7. 프런트 build와 preview 시험은 통과했지만 기존 `Monitor.tsx`가 현재 Prettier
   검사와 맞지 않는다. 동작 변경과 섞지 말고 별도 서식 정리 대상으로 남긴다.

환경 구성과 기동 순서는 [로컬 실행환경](LOCAL_ENVIRONMENT.md), 현재 구현·검증
수준은 [진행 현황](REVIEW_STATUS.md)을 따른다.
