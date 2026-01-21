# Workflow Specification v2

Cross-Critic 워크플로우 상세 스펙.

> **Updated**: 2026-01-18 22:00 (M2 병렬 리뷰)

## 개요

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    FULL CYCLE CRITIC WORKFLOW v2                         │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  Phase 0: CONTEXT                                                        │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐                           │
│  │ 계획입력  │ → │ 자동탐지  │ → │🔴 사람   │                           │
│  │(신규/기존)│    │specs/코드 │    │ 조정     │                           │
│  └──────────┘    └──────────┘    └──────────┘                           │
│       ↓                                                                  │
│  Phase 1: PLAN (병렬 리뷰)                                               │
│  ┌─────────────────────────────┐                                        │
│  │      ThreadPoolExecutor      │                                        │
│  │  ┌─────────┐  ┌─────────┐   │    ┌──────────┐    ┌────────┐         │
│  │  │  GPT    │  │ Claude  │   │ → │🔴 사람   │ → │ Claude │         │
│  │  │ 리뷰    │  │ 리뷰    │   │    │ 확인     │    │ 반영   │         │
│  │  └─────────┘  └─────────┘   │    └──────────┘    └────────┘         │
│  └─────────────────────────────┘                                        │
│       ↓                                                                  │
│  Phase 2: CODE                                                           │
│  ┌──────────┐                                                           │
│  │ Claude   │  (현재 세션이 코드 작성)                                   │
│  │ 코드작성  │                                                           │
│  └──────────┘                                                           │
│       ↓                                                                  │
│  Phase 3: CODE REVIEW (병렬 리뷰)                                        │
│  ┌─────────────────────────────┐                                        │
│  │      ThreadPoolExecutor      │                                        │
│  │  ┌─────────┐  ┌─────────┐   │    ┌──────────┐    ┌────────┐         │
│  │  │  GPT    │  │ Claude  │   │ → │🔴 사람   │ → │ Claude │         │
│  │  │ 리뷰    │  │ 리뷰    │   │    │ 확인     │    │ 반영   │         │
│  │  └─────────┘  └─────────┘   │    └──────────┘    └────────┘         │
│  └─────────────────────────────┘                                        │
│       ↓                                                                  │
│  Phase 4: RALPH LOOP                                                     │
│  ┌──────────┐                                                           │
│  │🔴 사람   │ ─────→ 만족 → 종료                                        │
│  │ 확인     │ ─────→ 불만족 → Phase 2로 (최대 5회)                       │
│  │          │ ─────→ 테스트 추가 → Phase 5                              │
│  └──────────┘                                                           │
│       ↓ (선택)                                                           │
│  Phase 5: TEST                                                           │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐                           │
│  │ GPT      │ → │🔴 사람   │ → │ Claude   │                           │
│  │ 테스트작성│    │ 확인     │    │ 실행/검증 │                           │
│  └──────────┘    └──────────┘    └──────────┘                           │
│                                                                          │
│  🔴 = 체크포인트: 진행/수정요청/중단 선택 가능                           │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Phase 0: Context 수집

### 입력

| 필드 | 필수 | 설명 |
|------|------|------|
| `plan_path` | O | 계획 문서 경로 (기존) 또는 None (신규 작성) |
| `context_paths` | X | 추가 context 파일 경로들 |
| `auto_detect` | X | 자동 탐지 여부 (default: true) |

### 자동 탐지 로직

```python
def auto_detect_context(plan_content: str, project_root: str) -> list[str]:
    """
    계획에서 언급된 파일/모듈 자동 탐지

    1. specs/ 디렉토리 전체 스캔
    2. 계획에서 파일명 패턴 추출 (예: `src/pipeline.py`)
    3. 함수/클래스명으로 grep
    """
    detected = []

    # 1. specs/ 전체
    detected += glob("specs/**/*.md")

    # 2. 파일명 패턴
    file_patterns = extract_file_patterns(plan_content)
    for pattern in file_patterns:
        matches = glob(pattern)
        detected += matches

    # 3. 코드 참조 분석
    code_refs = extract_code_references(plan_content)
    for ref in code_refs:
        matches = find_definition(ref, project_root)
        detected += matches

    return deduplicate(detected)
```

### 체크포인트: Context 조정

```yaml
prompt: "이 파일들을 GPT/Claude에게 전달할까요?"
options:
  - label: "진행"
    action: continue
  - label: "파일 추가"
    action: add_files
    input: file_paths
  - label: "파일 제거"
    action: remove_files
    input: file_indices
  - label: "중단"
    action: abort
```

### 출력

```python
@dataclass
class ContextResult:
    plan_content: str           # 계획 내용
    context_files: list[str]    # 확정된 context 파일 경로
    context_contents: dict      # {path: content}
```

---

## Phase 1: Plan Review (병렬)

### 입력

- `ContextResult` from Phase 0

### 병렬 리뷰 아키텍처

```python
class ParallelReviewer:
    """GPT + Claude 병렬 호출"""

    def review(self, prompt: str, context: str) -> ParallelReviewResult:
        with ThreadPoolExecutor(max_workers=2) as executor:
            gpt_future = executor.submit(self.gpt_client.call, prompt, context)
            claude_future = executor.submit(self.claude_client.call, prompt, context)

        return ParallelReviewResult(
            gpt_review=gpt_future.result(),
            claude_review=claude_future.result(),
            synthesized=self._synthesize(...),
            conflicts=self._detect_conflicts(...)
        )
```

### 계층적 프롬프트 (Step 1-4)

```markdown
## 계획
{plan_content}

## 리뷰 요청

아래 단계에 따라 계획을 비판적으로 리뷰해줘.
각 단계에서 해당 사항이 없으면 "없음"이라고 명시해줘.

### Step 1: Fatal Flaw Detection (치명적 결함)
이 계획에 구현을 막거나 큰 문제를 야기할 치명적 결함이 있나?
- 기술적 불가능성
- 심각한 보안 취약점
- 근본적인 설계 오류

### Step 2: Missing Requirements (누락된 요구사항, 최대 3개)
빠진 요구사항이 있다면, **왜** 누락되면 안 되는지 근거와 함께 설명해줘.

### Step 3: Edge Cases (엣지 케이스, 최대 3개)
고려하지 않은 엣지 케이스가 있다면:
- 구체적인 입력 예시
- 예상되는 문제
- 권장 처리 방법

### Step 4: Actionable Improvements (즉시 적용 가능한 개선, 최대 3개)
바로 반영할 수 있는 구체적인 개선 제안.
추상적인 조언 대신 코드나 명세 수정 예시를 포함해줘.
```

### 체크포인트: Plan Review 확인

```yaml
prompt: "병렬 리뷰를 확인하세요"
display:
  - gpt_review
  - claude_review
  - synthesized_summary
  - conflicts (if any)
options:
  - label: "진행 (리뷰 반영)"
    action: continue_with_feedback
  - label: "수정 요청"
    action: request_modification
    input: user_feedback
  - label: "충돌 해결 필요"
    action: resolve_conflict
    input: selected_opinion
  - label: "리뷰 무시하고 진행"
    action: continue_without_feedback
  - label: "중단"
    action: abort
```

### 충돌 해결 전략

| 유형 | 전략 | 키워드 |
|------|------|--------|
| 보안 | 더 보수적인 의견 우선 | security, vulnerability, injection, xss |
| 성능 | 측정 가능한 제안 우선 | performance, slow, memory, optimization |
| 스타일 | 사용자 선택 | naming, convention, format, style |
| 아키텍처 | 양쪽 제시 후 사용자 결정 | - |

### 출력

```python
@dataclass
class ParallelReviewResult:
    gpt_review: ModelResponse | None
    claude_review: ModelResponse | None
    gpt_error: str | None
    claude_error: str | None
    synthesized: str                    # 종합 요약
    conflicts: list[ReviewConflict]     # 충돌 목록
```

---

## Phase 2: Code (Claude 작성)

### 입력

- `ParallelReviewResult` from Phase 1 (리뷰 피드백)

### Claude 코드 작성

현재 세션의 Claude가 직접 코드 작성:

```python
@dataclass
class CodeChanges:
    files_created: list[str]
    files_modified: list[str]
    diff_summary: str           # git diff 요약
```

**주의**: 이 단계에서는 체크포인트 없음. Claude가 계획과 피드백 기반으로 작성.

---

## Phase 3: Code Review (병렬)

### 입력

- `CodeChanges` from Phase 2

### 계층적 코드 리뷰 프롬프트

```markdown
## Context
{context_str}

## 원래 계획
{plan_content}

## 구현된 코드 (diff)
{diff}

## 리뷰 요청

아래 단계에 따라 코드를 비판적으로 리뷰해줘.
각 단계에서 해당 사항이 없으면 "없음"이라고 명시해줘.

### Step 1: Fatal Flaw Detection (치명적 결함)
- 보안 취약점 (SQL injection, XSS, CSRF 등)
- 데이터 손실 가능성
- 무한 루프 / 데드락

### Step 2: Plan Deviation (계획 이탈)
계획과 다르게 구현된 부분이 있나?
- 누락된 기능
- 과도한 추가 기능 (over-engineering)
- 요구사항 오해

### Step 3: Edge Cases & Error Handling (엣지 케이스, 최대 3개)
- 구체적인 입력 예시
- 현재 코드의 동작
- 권장 수정 방법

### Step 4: Actionable Improvements (즉시 적용 가능한 개선, 최대 3개)
구체적인 코드 수정 예시를 포함해줘.
파일명:라인번호 형식으로 위치를 명시해줘.
```

### 체크포인트: Code Review 확인

```yaml
prompt: "코드 리뷰를 확인하세요"
display:
  - gpt_code_review
  - claude_code_review
  - synthesized_summary
  - conflicts (if any)
options:
  - label: "진행 (리뷰 반영)"
    action: continue_with_feedback
  - label: "수정 요청"
    action: request_modification
    input: user_feedback
  - label: "충돌 해결 필요"
    action: resolve_conflict
    input: selected_opinion
  - label: "리뷰 무시하고 진행"
    action: continue_without_feedback
  - label: "중단"
    action: abort
```

### 출력

```python
@dataclass
class CodeReviewResult:
    code_changes: CodeChanges
    parallel_review: ParallelReviewResult
    user_decision: str
    user_feedback: str | None
    final_code_changes: CodeChanges  # 수정 후
```

---

## Phase 4: Ralph Loop

### 목적

사용자가 만족할 때까지 반복하여 품질 보장.

### 상태 관리

```python
@dataclass
class LoopState:
    iteration: int = 1              # 현재 반복 횟수
    max_iterations: int = 5         # 최대 반복 (무한루프 방지)
    phase: str = "plan_review"      # 현재 phase
    last_conflicts: list[str]       # 마지막 충돌 목록
    resolved: bool = False          # 해결 여부
    history: list[dict]             # 이벤트 히스토리
```

### 저장 위치

```
.cross-critic/loop_state.json
```

### 체크포인트: Ralph Loop

```yaml
prompt: "결과에 만족하시나요?"
options:
  - label: "만족"
    action: finish
  - label: "불만족 (수정 계속)"
    action: continue_iteration
    next: Phase 2
  - label: "테스트 추가"
    action: add_tests
    next: Phase 5
```

### 규칙

- 최대 5회 반복 (무한 루프 방지)
- 반복 시마다 iteration 증가
- 이전 피드백 컨텍스트 유지
- 5회 초과 시 강제 종료 경고

---

## Phase 5: Test Generation (선택)

### 입력

- `CodeReviewResult` from Phase 3/4

### GPT 테스트 작성 프롬프트

```markdown
## Context
{context_str}

## 계획
{plan_content}

## 구현된 코드
{diff}

## 테스트 작성 요청

아래 구조로 pytest 테스트를 작성해줘:

### 1. 정상 케이스 (Happy Path)
기본 동작이 예상대로 작동하는지 검증

### 2. Edge Cases
- 빈 입력
- 경계값 (최소/최대)
- 특수 문자 / 유니코드

### 3. 에러 케이스
- 잘못된 타입 입력
- 권한 오류 시나리오
- 타임아웃 / 연결 실패

### 4. 요구사항 검증
계획에 명시된 각 요구사항을 테스트로 커버

**출력 형식**: pytest 테스트 파일 내용만 출력 (설명 없이 코드만)
```

### 체크포인트: Test 확인

```yaml
prompt: "GPT가 작성한 테스트를 확인하세요"
display: gpt_tests
options:
  - label: "진행 (테스트 저장 및 실행)"
    action: continue_run_tests
  - label: "테스트 수정 요청"
    action: request_modification
    input: user_feedback
  - label: "테스트 없이 종료"
    action: skip_tests
  - label: "중단"
    action: abort
```

### 출력

```python
@dataclass
class TestResult:
    test_files: list[str]
    test_content: str
    execution_result: str | None  # 실행했다면
    passed: bool | None
    failures: list[str] | None
```

---

## 상태 관리

### State File

`.cross_critic_state.json`:

```json
{
  "session_id": "uuid",
  "started_at": "2026-01-18T23:30:00",
  "current_phase": 2,
  "plan_path": "plan.md",
  "context_files": ["specs/agent.md", "src/pipeline.py"],
  "results": {
    "phase_0": { "...": "..." },
    "phase_1": { "...": "..." }
  },
  "checkpoints": [
    {"phase": 0, "decision": "continue", "timestamp": "..."},
    {"phase": 1, "decision": "continue_with_feedback", "timestamp": "..."}
  ]
}
```

### Ralph Loop State File

`.cross-critic/loop_state.json`:

```json
{
  "iteration": 2,
  "max_iterations": 5,
  "phase": "code_review",
  "last_conflicts": ["GPT: 개별 try-except, Claude: 통합 에러 핸들링"],
  "resolved": false,
  "history": [
    {"iteration": 1, "phase": "plan_review", "event": "start", "details": {}},
    {"iteration": 1, "phase": "code_review", "event": "conflict_detected", "details": {...}}
  ]
}
```

---

## CLI Interface

### 병렬 리뷰 CLI

```bash
# 계획 병렬 리뷰
uv run python scripts/parallel_review.py plan /path/to/plan.md

# 코드 병렬 리뷰
uv run python scripts/parallel_review.py code /path/to/plan.md --project-dir /path/to/project

# Context 파일 추가
uv run python scripts/parallel_review.py plan /path/to/plan.md --context specs/agent.md src/core.py

# Claude 모델 선택 (기본: sonnet)
uv run python scripts/parallel_review.py plan /path/to/plan.md --claude-model haiku

# JSON 출력
uv run python scripts/parallel_review.py plan /path/to/plan.md --json
```

### GPT 단독 리뷰 CLI (기존)

```bash
# 계획 리뷰
uv run python scripts/gpt_review.py plan /path/to/plan.md [context_files...]

# 코드 리뷰
uv run python scripts/gpt_review.py code /path/to/plan.md --project-dir /path/to/project

# 테스트 작성
uv run python scripts/gpt_review.py test /path/to/plan.md --project-dir /path/to/project

# Context 추가
uv run python scripts/gpt_review.py code /path/to/plan.md --project-dir /path/to/project --context specs/agent.md
```

---

## 에러 처리

### 병렬 호출 에러

```python
def review(self, prompt: str, context: str) -> ParallelReviewResult:
    gpt_error = None
    claude_error = None

    try:
        gpt_review = gpt_future.result(timeout=timeout)
    except FuturesTimeoutError:
        gpt_error = f"GPT timed out after {timeout}s"
    except CodexError as e:
        gpt_error = str(e)

    try:
        claude_review = claude_future.result(timeout=timeout)
    except FuturesTimeoutError:
        claude_error = f"Claude timed out after {timeout}s"
    except ClaudeError as e:
        claude_error = str(e)

    # 하나라도 성공하면 계속 진행
    return ParallelReviewResult(
        gpt_review=gpt_review,
        claude_review=claude_review,
        gpt_error=gpt_error,
        claude_error=claude_error,
        ...
    )
```

### 복구 전략

| 에러 | 복구 |
|------|------|
| GPT 타임아웃 | Claude 결과만 사용, 경고 표시 |
| Claude 타임아웃 | GPT 결과만 사용, 경고 표시 |
| 양쪽 모두 실패 | 사용자에게 재시도 또는 스킵 선택 |
| 파일 없음 | 사용자에게 경로 확인 요청 |
| Phase 실패 | 상태 저장 후 재개 가능 |

---

## Claude Code Skill 통합

### Skill 위치

```
~/.claude/skills/cross-critic/SKILL.md
```

### Skill 호출

```bash
# 기본 호출
/cross-critic plan.md

# context 추가
/cross-critic plan.md --context specs/agent.md src/core.py
```

### 워크플로우 흐름 (Skill 내)

```
1. 계획 파일 읽기
2. Phase 0: Context 자동 탐지
   → AskUserQuestion으로 확인
3. Phase 1: GPT + Claude 병렬 계획 리뷰 (Python 실행)
   → AskUserQuestion으로 확인
4. Phase 2: Claude가 코드 작성 (Edit/Write 도구)
5. Phase 3: GPT + Claude 병렬 코드 리뷰 (Python 실행)
   → AskUserQuestion으로 확인
   → Claude가 피드백 반영
6. Phase 4: Ralph Loop
   → AskUserQuestion으로 만족/불만족 확인
   → 불만족 시 Phase 2로
7. Phase 5: (선택) GPT 테스트 작성
   → AskUserQuestion으로 확인
   → Claude가 테스트 저장 및 실행
```

---

## 변경 이력

| 날짜 | 내용 |
|------|------|
| 2026-01-18 | M2: 병렬 리뷰, Ralph Loop, 계층적 프롬프트 |
| 2026-01-18 | M1.5: Claude Code Skill 통합, 헬퍼 스크립트 추가 |
| 2026-01-18 | 초안 작성 |
