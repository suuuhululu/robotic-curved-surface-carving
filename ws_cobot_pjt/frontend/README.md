# 새김 · 운영자 HMI

> 기준: 2026-09-30 PR #99 head `3d882f6`. React 19·TypeScript·Vite 기반의
> 로컬 작업자 관제 화면이다. 이전 `HMI_*_202609*.md`는 당시 개발 기록이며 현재
> 모드·계약은 이 문서와 [백엔드](../backend/README.md)를 따른다.

## 설치와 실행

현재 PC에서는 Node 18.19.1, pnpm 11.25.0과 저장된 lockfile로 build를 확인했다.
`--experimental-strip-types`를 쓰는 preview 시험까지 실행할 환경은 Node 22 이상을
사용한다. 의존성 버전은 `package.json`과 `pnpm-lock.yaml`을 함께 따른다.

```bash
cd ws_cobot_pjt/frontend
pnpm install --frozen-lockfile
```

저장소 루트에서 다음을 실행한다.

```bash
python3 ws_cobot_pjt/run_monitor.py
```

화면은 `http://127.0.0.1:5174/operator`, API는 `http://127.0.0.1:8010`이다.
기본은 SIMULATION/MOCK이다. ROS SIM과 REAL 옵션은
[로컬 실행환경](../../docs/LOCAL_ENVIRONMENT.md)을 따른다.

화면만 개발할 때는 `pnpm dev`를 사용한다. Vite 5174의 `/api/operator` 요청을
8010으로 전달한다. `pnpm preview`에는 이 API 프록시가 없으므로 전체 흐름 시험에
사용하지 않는다.

```bash
pnpm build
pnpm exec prettier --check 'src/monitor/*.{ts,tsx,css}' src/main.tsx vite.config.ts
node --experimental-strip-types --test tests/preview.test.mjs
```

2026-09-30 확인에서 build와 Node 24 preview 시험 5건은 통과했다. Prettier 검사는
기존 `src/monitor/Monitor.tsx` 불일치 1건이 남아 있으며 기능 시험 통과와 구분한다.

## 현재 작업 순서

1. 준비 설정과 현장 확인을 검토하고 MEASURE를 요청한다.
2. 서버가 접촉 9점 원본을 저장하고 유효한 실행 설정이 있으면 BIND한다.
3. PNG/JPEG와 배치값으로 경로를 생성하고 전개면·원기둥 미리보기를 확인한다.
4. 같은 경로·스냅샷·해시와 공작물 고정을 확인한 뒤 별도 ExecuteProcess를 요청한다.
5. `PRECHECK → ENTRY → ENGRAVE → RETURN_HOME → FINISH` 진행과 정지 결과를 확인한다.
6. 실행 이력에서 결과와 사후 검사를 기록한다.

entry 비활성 호환 흐름에서는 `ENTRY`와 `RETURN_HOME`이 생략될 수 있다. 화면의
드릴 ON 체크는 운영자의 수동 전원 절차 확인이며 센서값이나 드릴 제어 명령이 아니다.

## 표시 의미

- MOCK은 이미지 계산과 공정 상태를 시험하기 위한 모의 결과다.
- ROS SIM은 실제 팀 ROS 타입을 사용하지만 로봇 실기 결과가 아니다.
- REAL 경로의 `real_execution_allowed=true`는 실행 후보 표시다. 공정 PRECHECK,
  실제 충돌 검사, 가공 품질 합격을 뜻하지 않는다.
- 구간 색상은 미완료, 진행, 이동 완료, 실패, 진행 미확인을 구분한다. 이동 완료를
  가공 품질 합격으로 표시하지 않는다.
- 정지 요청 접수와 실제 정지 확인을 구분한다. `UNKNOWN` 또는
  `STOP_UNCONFIRMED`이면 현장 상태 확인 전 새 작업을 시작하지 않는다.

REAL 실행 프로파일이 없거나 형식이 틀리면 측정과 test-only 미리보기까지만
가능하다. BIND·REAL 실행 후보·조각은 차단한다. 준비 상태·제어권·관측 상실로
BIND가 무효화되면 기존 파일만으로 자동 복구하지 않는다.

진행 중 공정의 pause/resume은 없다. 브라우저 새로고침은 저장된 기록을 다시 읽지만
공정 노드의 모션을 다음 날 이어서 시작하는 기능이 아니다.

## 소스

- `src/main.tsx`: 모니터 진입점
- `src/monitor/Monitor.tsx`: 준비·관제·이력·알람·설정
- `src/monitor/PreparationPanel.tsx`: 준비 요청·취소·측정 진행·결과
- `src/monitor/LivePathPreview.tsx`: 경로와 구간 상태
- `src/monitor/Previews.tsx`, `preview.ts`: 전개면·원기둥 표시
- `src/monitor/api.ts`: HTTP 타입·요청·오류
- `src/monitor/monitor.css`: 1920×1080 작업자 화면 스타일

화면은 로봇 좌표나 모션 순서를 직접 만들지 않는다. 한 운영자용 루프백 개발
화면이며 외부 공개·다중 사용자 인증은 현재 범위가 아니다.
