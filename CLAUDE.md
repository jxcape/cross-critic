# Cross-Critic

Cross-model critic 워크플로우 엔진. Claude + GPT(Codex CLI) 기반 다중 모델 검증 시스템.

## 프로젝트 목적

LLM의 misbehavior 문제 해결:
- 같은 모델이 검증하면 같은 blind spot 공유
- 다른 모델(GPT + Claude 서브에이전트)로 병렬 검증하여 다양한 관점 확보
- 사람 체크포인트로 최종 통제권 유지

## 핵심 워크플로우 (v2)

```
[Phase 1] Plan 작성 & 병렬 리뷰
  사용자 요청 → CC가 Plan 작성
                    ↓
            ┌─────────────────────────┐
            │       병렬 호출          │
            │ codex exec  │  claude -p │
            │   (GPT)     │  (Claude)  │
            └─────────────────────────┘
                    ↓
            피드백 종합 → 🔴 사용자 확인 → 계획 수정

[Phase 2] Code 작성
  CC(현재 세션)가 코드 작성

[Phase 3] Code Review (병렬)
  git diff → 병렬 호출 → 피드백 종합 → 🔴 사용자 확인

[Phase 4] Ralph Loop
  만족 → 종료 / 불만족 → Phase 2로 (최대 5회)

🔴 = 체크포인트 (진행/수정요청/중단 선택)
```

## 기술 스택

- Python 3.11+
- **Codex CLI** (GPT 연동) - `codex exec`
- **Claude CLI** (서브에이전트) - `claude -p --model sonnet`
- Claude Code (메인 에이전트)
- uv (패키지 관리)

## 디렉토리 구조

```
core/               # 핵심 엔진
  workflow.py       # 워크플로우 기본 클래스
  models.py         # 모델 래퍼 (Claude, GPT, etc.)
  checkpoints.py    # 사용자 체크포인트
  context.py        # Context 수집/관리
  parallel_review.py # 병렬 리뷰 엔진
  debate.py         # 경량 토론 엔진
  multi_model.py    # N-모델 병렬 리뷰 (MultiModelReviewer)
  history.py        # 세션 히스토리 관리 (HistoryManager)

scripts/            # CLI 스크립트
  gpt_review.py     # GPT 단독 리뷰
  parallel_review.py # GPT + Claude 병렬 리뷰
  debate.py         # 멀티라운드 토론 CLI

viewer/             # Streamlit 대시보드
  app.py            # 통합 뷰어 (Debate | Diff | History 탭)
  diff.py           # 코드 리뷰용 Diff 렌더러
  history.py        # 세션 히스토리 뷰어

workflows/          # 워크플로우 구현체
  full_cycle.py     # Full cycle critic

specs/              # 스펙 문서
  workflow.md       # 워크플로우 상세 스펙
  debate-light.md   # Debate Light 스펙
```

## 개발 규칙

### 체크포인트 필수
- 모든 Phase 반영 직전에 사람 확인
- 자동 진행 금지 (--auto 플래그 없으면)

### Context 전달
- 전체 전달 (요약 금지)
- 자동 탐지 후 사용자 조정

### 충돌 해결 전략
| 유형 | 전략 |
|------|------|
| 보안 | 더 보수적인 의견 우선 |
| 성능 | 측정 가능한 제안 우선 |
| 스타일 | 사용자 선택 |
| 아키텍처 | 양쪽 제시 후 사용자 결정 |

## 실행 방법

```bash
cd /Users/xcape/gemmy/10_Projects/cross-critic

# 테스트 실행
uv run pytest -v

# 병렬 리뷰 (계획)
uv run python scripts/parallel_review.py plan /path/to/plan.md

# 병렬 리뷰 (코드)
uv run python scripts/parallel_review.py code /path/to/plan.md --project-dir /path/to/project

# GPT 단독 리뷰 (기존)
uv run python scripts/gpt_review.py plan /path/to/plan.md

# Claude 모델 선택
uv run python scripts/parallel_review.py plan /path/to/plan.md --claude-model haiku

# JSON 출력
uv run python scripts/parallel_review.py plan /path/to/plan.md --json

# 토론 시작 (Round 1)
uv run python scripts/debate.py start /path/to/plan.md

# 토론 계속 (Round 2+)
uv run python scripts/debate.py continue /path/to/plan.md

# 특정 주제에 집중해서 토론
uv run python scripts/debate.py continue /path/to/plan.md --focus "에러 처리"

# 토론 상태 보기
uv run python scripts/debate.py status /path/to/plan.md

# 토론 리셋
uv run python scripts/debate.py reset /path/to/plan.md

# 뷰어 실행 (Streamlit 대시보드)
uv run python scripts/debate.py serve /path/to/plan.md
```

## 현재 상태 (2026-01-19)

### 완료
- [x] 프로젝트 구조
- [x] core 모듈 (models, context, checkpoints, workflow, parallel_review, debate)
- [x] CodexClient (GPT 연동)
- [x] ClaudeClient 개선 (--model 옵션, 서브에이전트)
- [x] ParallelReviewer (GPT + Claude 병렬 호출)
- [x] Ralph Loop 상태 관리 (LoopManager)
- [x] 프롬프트 품질 개선 (계층적 Step 1-4 구조)
- [x] DebateEngine (경량 멀티라운드 토론)
- [x] scripts/debate.py CLI (start/continue/status/reset/serve)
- [x] viewer/app.py - 통합 Streamlit 대시보드 (Debate | Diff | History)
- [x] **MultiModelReviewer** - N개 모델 병렬 호출, 합의 점수 계산
- [x] **DiffRenderer** - 코드 리뷰용 unified diff 파싱 및 렌더링
- [x] **HistoryManager** - 세션 히스토리 저장/조회/검색
- [x] 129개 테스트 통과
- [x] Claude Code skill (`/cross-critic`)

### TODO
- [ ] Adaptive Debate (자동 합의 판단, Severity 기반 진행)
- [ ] CC Skill 자동 링크 출력
- [ ] Mermaid 다이어그램 자동 생성

## Skill 사용법

Claude Code에서 `/cross-critic` 호출:

```bash
# 계획 파일로 워크플로우 시작
/cross-critic plan.md

# context 파일 추가
/cross-critic plan.md --context specs/agent.md src/core.py
```

워크플로우:
1. Phase 0: Context 자동 탐지 → 🔴 체크포인트
2. Phase 1: GPT + Claude 병렬 리뷰 → 🔴 체크포인트
3. Phase 2: Claude 코드 작성
4. Phase 3: GPT + Claude 병렬 코드 리뷰 → 🔴 체크포인트
5. Phase 4: Ralph Loop (만족할 때까지)

## 관련 문서

- `specs/workflow.md` - 워크플로우 상세 스펙
- `specs/debate-light.md` - Debate Light 스펙
- `BUGS.md` - 버그 추적
- `PROGRESS.md` - 진행 상황
