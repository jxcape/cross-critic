# Debate Light - M2.5

경량 토론 기능. 자동 판단 없이 수동 트리거로 멀티라운드 토론 지원.

> **Status**: ✅ 완료 (2026-01-19)

## 핵심 원칙

**자동 판단 없음** - 모든 결정은 사용자가 함
- Severity 자동 분류 ❌
- 합의 자동 판단 ❌
- 발산 자동 감지 ❌

## 워크플로우

```
Round 1: 독립 리뷰 (병렬) → Viewer에서 확인 → 🔴 사용자
    ↓
"더 토론해" 선택 시
    ↓
Round 2: 상대 의견 보고 반박/동의 (병렬) → Viewer에서 확인 → 🔴 사용자
    ↓
"더 토론해" 또는 "됐어" 선택
    ↓
(반복 가능, 최대 5라운드)
```

## 구현된 파일

| 파일 | 역할 |
|------|------|
| `core/debate.py` | DebateEngine, DebateRound, DebateResult |
| `scripts/debate.py` | CLI (start/continue/status/reset/serve) |
| `viewer/app.py` | Streamlit 대시보드 |
| `tests/test_debate.py` | 21개 단위 테스트 |

## CLI 사용법

```bash
# Round 1 시작
uv run python scripts/debate.py start plan.md

# 뷰어 실행 (브라우저에서 Side-by-side 비교)
uv run python scripts/debate.py serve plan.md

# 토론 계속
uv run python scripts/debate.py continue plan.md

# 특정 주제에 집중
uv run python scripts/debate.py continue plan.md --focus "에러 처리"

# 상태 확인
uv run python scripts/debate.py status plan.md

# 리셋
uv run python scripts/debate.py reset plan.md
```

## Viewer 기능

```
┌─────────────────────────────────────────────────┐
│  🎭 Cross-Critic Debate Viewer                  │
├────────────────────┬────────────────────────────┤
│  🤖 GPT (Codex)    │  🧠 Claude                 │
├────────────────────┼────────────────────────────┤
│  Step 1: Fatal     │  Step 1: Fatal             │
│  Step 2: Missing   │  Step 2: Missing           │
│  Step 3: Edge      │  Step 3: Edge              │
│  Step 4: Improve   │  Step 4: Improve           │
├────────────────────┴────────────────────────────┤
│  📊 비교 분석                                    │
│  🤝 공통 언급: 에러 처리, JSON, 상태            │
│  🔀 차이점: context (Claude만), race (Claude만) │
├─────────────────────────────────────────────────┤
│  진행: ●○○○○ (1/5)                              │
│  다음 액션: continue / --focus / reset          │
└─────────────────────────────────────────────────┘
```

## 핵심 클래스

### DebateRound

```python
@dataclass
class DebateRound:
    round_number: int
    gpt_response: str | None
    claude_response: str | None
    gpt_error: str | None = None
    claude_error: str | None = None
```

### DebateResult

```python
@dataclass
class DebateResult:
    rounds: list[DebateRound]

    @property
    def latest_round(self) -> DebateRound | None
    @property
    def round_count(self) -> int
    def format_history(self) -> str
```

### DebateEngine

```python
class DebateEngine:
    MAX_ROUNDS = 5

    def start(self, plan_content: str, context: str | None, review_type: str) -> DebateResult
    def continue_debate(self, debate_result: DebateResult, plan_content: str, context: str | None, user_focus: str | None) -> DebateResult
```

## 상태 파일

위치: `.cross-critic/debate_state.json`

```json
{
  "rounds": [
    {
      "round_number": 1,
      "gpt_response": "...",
      "claude_response": "...",
      "gpt_error": null,
      "claude_error": null
    }
  ]
}
```

## 프롬프트 구조

### Round 1 (독립 리뷰)

```
Step 1: Fatal Flaw Detection (치명적 결함)
Step 2: Missing Requirements (누락된 요구사항, 최대 3개)
Step 3: Edge Cases (엣지 케이스, 최대 3개)
Step 4: Actionable Improvements (즉시 적용 가능한 개선, 최대 3개)
```

### Round 2+ (토론)

```
1. 동의하는 부분
2. 반박하는 부분
3. 새로운 관점
4. 현재 입장 요약
```

## TODO (M3: Adaptive Debate)

- [ ] 자동 합의 판단
- [ ] Severity 기반 자동 진행
- [ ] 발산 감지
- [ ] Diff 뷰어 (code review용)
