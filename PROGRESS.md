# PROGRESS.md

## 현재 상태

**Phase**: M2.5 Debate Light + Viewer 완료
**Updated**: 2026-01-19 16:30

## 마일스톤

### M1: MVP (완료)

- [x] 프로젝트 구조 생성
- [x] specs/workflow.md 작성
- [x] core/models.py - 모델 래퍼 (Codex, Claude)
- [x] core/context.py - Context 자동 탐지/수집
- [x] core/checkpoints.py - 사용자 체크포인트
- [x] core/workflow.py - 워크플로우 엔진
- [x] workflows/full_cycle.py - Full cycle 구현
- [x] CLI 진입점 (cli.py)
- [x] 테스트 (42개 통과)
- [x] uv 프로젝트 설정
- [x] **CodexClient 구현 및 테스트** (gpt-5.2-codex)
- [x] **워크플로우 E2E 테스트** (Plan Review 동작 확인)

### M1.5: Claude 통합 (완료)

- [x] Phase 2 Claude 코드 작성 통합 설계
- [x] Claude Code skill 연결 (`/cross-critic`)
- [x] GPT 리뷰 헬퍼 스크립트 (`scripts/gpt_review.py`)
- [x] 실제 프로젝트에서 테스트

### M2: 병렬 리뷰 (완료)

- [x] ClaudeClient 개선 (--model 옵션, 서브에이전트로 활용)
- [x] core/parallel_review.py - ParallelReviewer 병렬 호출 엔진
- [x] 프롬프트 품질 개선 (계층적 Step 1-4 구조)
- [x] scripts/parallel_review.py - 병렬 리뷰 CLI
- [x] Ralph Loop 상태 관리 (LoopManager, LoopState)
- [x] SKILL.md 워크플로우 v2 업데이트
- [x] 테스트 61개 통과

### M2.5: Debate Light + Viewer (완료)

- [x] core/debate.py - 경량 토론 엔진
- [x] DebateEngine, DebateRound, DebateResult 클래스
- [x] scripts/debate.py - 토론 CLI (start/continue/status/reset/serve)
- [x] 히스토리 기반 멀티라운드 토론 (최대 5라운드)
- [x] user_focus 옵션 (특정 주제 집중 토론)
- [x] viewer/app.py - Streamlit 대시보드
- [x] GPT/Claude Side-by-side 비교 뷰
- [x] 공통점/차이점 자동 분석
- [x] tests/test_debate.py - 21개 테스트
- [x] 전체 82개 테스트 통과

### M3: Adaptive Debate (예정)

- [ ] 자동 합의 판단
- [ ] Severity 기반 자동 진행
- [ ] 발산 감지
- [ ] 다중 모델 (3+) 지원

### M4: 시각화 확장 (예정)

- [x] Streamlit 대시보드 (M2.5에서 완료)
- [ ] Diff 뷰어 (code review용)
- [ ] 실행 히스토리
- [ ] Mermaid 다이어그램 자동 생성

---

## 변경 이력

| 날짜 | 내용 |
|------|------|
| 2026-01-19 | **M2.5 + Viewer**: Streamlit 대시보드, Side-by-side 비교, serve 명령어 |
| 2026-01-19 | **M2.5 Debate Light 완료**: DebateEngine, scripts/debate.py CLI, 82개 테스트 |
| 2026-01-18 | **M2 병렬 리뷰 완료**: ClaudeClient 개선, ParallelReviewer, 프롬프트 개선, Ralph Loop |
| 2026-01-18 | M1.5 시작: `/cross-critic` skill 생성, `scripts/gpt_review.py` 헬퍼 추가 |
| 2026-01-18 | CodexClient 추가, 워크플로우 E2E 테스트 성공 (42개 테스트) |
| 2026-01-18 | MVP 완료: core 모듈, CLI |
| 2026-01-18 | 프로젝트 초기화 |

## 기술 결정

| 결정 | 이유 |
|------|------|
| Claude 서브에이전트 | 기존 구독 활용, 추가 비용 없음, 독립적 관점 |
| ThreadPoolExecutor | GPT + Claude 병렬 호출로 시간 단축 |
| Codex CLI 사용 | OpenCode는 Z.AI 설정 문제로 작동 안 함 |
| `-o` 옵션으로 출력 | Codex stdout 파싱보다 깔끔 |
| uv 패키지 관리 | 빠른 의존성 관리 |
