# HMI·UI 화면 구성도 최종본

| 항목 | 내용 |
| --- | --- |
| 기준 코드 | `origin/main` `987a3b7` + PR #93 HMI 예외처리 변경 |
| 개정일 | 2026-09-27 |
| 편집 원본 | [HMI_UI_CONFIGURATION_FINAL_20260927.drawio](HMI_UI_CONFIGURATION_FINAL_20260927.drawio) |
| 발표·노션용 | [HMI_UI_CONFIGURATION_FINAL_20260927.pdf](../../../../output/pdf/HMI_UI_CONFIGURATION_FINAL_20260927.pdf) |
| 화면 구현 | `frontend/src/monitor/Monitor.tsx`, `PreparationPanel.tsx` |

## 문서 목적

이 구성도는 노드 구조가 아니라 운영자가 실제로 보는 화면과 화면에서 판단해야 하는 정보를 설명한다. 화면 모양만 재현하지 않고 입력, 상태 출처, 버튼 활성 조건, 오류 후 차단, 운영자 조치를 함께 표시한다.

## 페이지 구성

| 페이지 | 실제 화면 상태 | 핵심 확인 항목 |
| --- | --- | --- |
| 1 | 작업 준비 상단 · 준비/측정 | 양초 높이, 운영자 수동 확인, 8점 진행, 최종 준비 결과, 오류 코드·조치 |
| 2 | 작업 준비 하단 · 입력/미리보기/실행 | 이미지·배치, 2D/3D 미리보기, 적용 실행 설정, 경로/설정 동일성, 시작 차단 사유 |
| 3 | 공정 관제 | 현재 상태와 이벤트 분리, 5단계 진행, 조각 구간 진행률, 오류 코드·조치, REAL 최신성 |
| 4 | 실행 이력과 검사 모달 | 공정 결과와 품질 판정 분리, 오류 코드, 경로 ID·버전, 검사 근거 |
| 5 | 알람 | 활성/해제, 단계·심각도·코드, 운영자 조치, 해제 근거와 시각 |
| 6 | 설정 정보 | 작업영역·도구·좌표계, 실행 모드·접촉·깊이·속도·정지/J6, ID·SHA-256 |

## 이번 개정에서 추가한 표현

1. 준비·생성·실행 실패에 기계 판정용 오류 코드와 운영자 조치를 함께 표시한다.
2. 실행 준비에서 적용 깊이·속도·접촉 방식·정지 확인 제한을 읽기 전용으로 표시한다.
3. 경로와 프로파일의 ID·버전·SHA-256 및 모든 시작 차단 사유를 표시한다.
4. 공정 결과 `SUCCEEDED/FAILED/STOPPED`와 품질 판정 `PASS/HOLD/REJECT/미검사`를 분리한다.
5. 알람은 활성과 해제를 구분하며 해제된 알람도 이력과 해제 근거를 보존한다.
6. SIMULATION 관측과 REAL 최신 상태를 구분해 모의 값을 실제 센서값으로 표현하지 않는다.

## 해석 제한

- 화면의 드릴 ON 확인은 센서나 전원 제어 명령이 아니다.
- 경로 생성 성공은 실제 충돌 검사나 가공 품질 합격이 아니다.
- HMI의 정지 요청 접수는 실제 로봇 정지 완료가 아니다.
- 깊이·속도·J6 값 표시는 적용 후보 또는 설정 스냅샷의 값이며 현장 승인·실기 검증 완료를 뜻하지 않는다.
- 공통 ROS 타입, 모션 순서, 힘·깊이·속도·J6 알고리즘은 이번 화면 구성도 개정으로 변경되지 않는다.

## 재생성

기존 2026-09-25 draw.io/PDF 원본을 입력으로 사용해 다음 스크립트로 최종본을 재생성한다.

```bash
python3 tools/build_hmi_ui_configuration.py \
  --source-drawio HMI_Actual_UI_Wireframe_20260925.drawio \
  --source-pdf HMI_Actual_UI_Wireframe_20260925_Notion_Light.pdf \
  --output-drawio ws_cobot_pjt/docs/architecture/hmi-ui-20260927/HMI_UI_CONFIGURATION_FINAL_20260927.drawio \
  --output-pdf output/pdf/HMI_UI_CONFIGURATION_FINAL_20260927.pdf \
  --preview-dir tmp/pdfs/HMI_UI_CONFIGURATION_FINAL_20260927
```

PDF 생성 후 6개 페이지를 PNG로 다시 렌더링해 글자 잘림, 겹침, 상태 표기 누락을 확인한다.
