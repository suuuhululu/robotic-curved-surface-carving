# main_v11 통합 문서·환경 점검

- 시험명 / 작성자 / 확인자 / 날짜: main_v11 문서·환경 점검 / Codex / 사람 검토 대기 / 2026-09-30
- Issue / PR / 시험한 커밋: 코드 PR #99 `3d882f6`, 문서 PR 작업트리
- 시험 수준: 문서 링크·Python 구문, 프런트 build·단위시험, ROS CLI 정적 기동 확인
- 실행 PC: Ubuntu 24.04 x86_64, ROS 2 Jazzy, Python 3.12.3,
  Node 18.19.1·24.19.0, pnpm 11.25.0
- 공작물·지그·TCP·하중·좌표계 적용: 없음. 로봇·드라이버·그리퍼·힘 명령 미실행
- 현장 절차에 따른 실행 전 확인: 적용 없음

| 시나리오 | 기대 결과 | 실제 결과 | 판정 | 증거 |
| --- | --- | --- | --- | --- |
| 문서·링크 검사 | 현재 파일을 가리키고 Python 구문·상대 링크가 유효 | 272개 파일 통과 | 통과 | `python3 tools/check_repository.py` |
| 저장소 관리 도구 | hook·Issue 설정과 시험이 오류 없이 끝남 | hook 8건, Issue 시험 27건 통과. 네트워크·변경 없음 | 통과 | 로컬 명령 출력 |
| 프런트 build | 고정 lockfile로 TypeScript/Vite 산출물 생성 | Node 18.19.1에서 성공 | 통과 | `CI=true pnpm install --frozen-lockfile && CI=true pnpm build` |
| preview 계산 | 표시 변환 시험 통과 | Node 24.19.0에서 5건 통과 | 통과 | `node --experimental-strip-types --test tests/preview.test.mjs` |
| 프런트 서식 | 현재 소스가 Prettier와 일치 | 기존 `Monitor.tsx` 불일치 1건 | 실패·후속 | 기능 변경과 분리한 서식 정리 필요 |
| 문서의 CLI 인자 | HMI·REAL 공정 노드 도움말과 일치 | `run_monitor.py`, `real_process_node --help` 일치 | 통과 | Jazzy·팀 overlay에서 읽기 전용 실행 |

- 반복 횟수: 각 검사 1회. PR #99의 코드 시험은 [현재 현황](../../../docs/REVIEW_STATUS.md)에 별도 기록했다.
- 미확인 한계: 실제 M0609 모션, 외부 드라이버 원본 커밋·패치 적용, 측정 반복성,
  충돌·정지 시간, 가공 깊이·품질은 확인하지 않았다.
- 연결 문서: [저장소 점검](../../../docs/MAIN_V11_AUDIT.md),
  [로컬 실행환경](../../../docs/LOCAL_ENVIRONMENT.md)
