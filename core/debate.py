"""
Debate Engine (Light)

멀티라운드 토론 지원. 자동 판단 없이 사용자가 라운드 진행 결정.
"""

from dataclasses import dataclass, field
from .parallel_review import ParallelReviewer, ParallelReviewResult


@dataclass
class DebateRound:
    """토론 라운드 결과"""
    round_number: int
    gpt_response: str | None
    claude_response: str | None
    gpt_error: str | None = None
    claude_error: str | None = None


@dataclass
class DebateResult:
    """전체 토론 결과"""
    rounds: list[DebateRound] = field(default_factory=list)

    @property
    def latest_round(self) -> DebateRound | None:
        return self.rounds[-1] if self.rounds else None

    @property
    def round_count(self) -> int:
        return len(self.rounds)

    def format_history(self) -> str:
        """토론 히스토리를 프롬프트용 문자열로 변환"""
        parts = []
        for r in self.rounds:
            parts.append(f"## Round {r.round_number}")
            parts.append(f"### GPT")
            parts.append(r.gpt_response or f"*Error: {r.gpt_error}*")
            parts.append(f"### Claude")
            parts.append(r.claude_response or f"*Error: {r.claude_error}*")
            parts.append("")
        return "\n".join(parts)


class DebateEngine:
    """
    경량 토론 엔진

    Usage:
        engine = DebateEngine()

        # Round 1: 독립 리뷰
        result = engine.start(plan_content, context)
        print(result.latest_round)  # 사용자에게 보여줌

        # Round 2+: 토론 (사용자가 "더 토론해" 선택 시)
        result = engine.continue_debate(result, plan_content)
        print(result.latest_round)
    """

    MAX_ROUNDS = 5

    def __init__(
        self,
        reviewer: ParallelReviewer | None = None,
        claude_model: str = "sonnet",
    ):
        self.reviewer = reviewer or ParallelReviewer(claude_model=claude_model)

    def start(
        self,
        plan_content: str,
        context: str | None = None,
        review_type: str = "plan",  # "plan" or "code"
    ) -> DebateResult:
        """
        Round 1 시작 (독립 리뷰)

        Args:
            plan_content: 리뷰할 계획 또는 diff
            context: 추가 컨텍스트
            review_type: "plan" (계획 리뷰) 또는 "code" (코드 리뷰)

        Returns:
            DebateResult with Round 1
        """
        prompt = self._build_initial_prompt(plan_content, review_type)

        parallel_result = self.reviewer.review(prompt, context)

        round1 = DebateRound(
            round_number=1,
            gpt_response=parallel_result.gpt_review.content if parallel_result.gpt_review else None,
            claude_response=parallel_result.claude_review.content if parallel_result.claude_review else None,
            gpt_error=parallel_result.gpt_error,
            claude_error=parallel_result.claude_error,
        )

        return DebateResult(rounds=[round1])

    def continue_debate(
        self,
        debate_result: DebateResult,
        plan_content: str,
        context: str | None = None,
        user_focus: str | None = None,  # 사용자가 특정 주제에 집중 요청
    ) -> DebateResult:
        """
        다음 라운드 진행 (상대 의견 보고 반박/동의)

        Args:
            debate_result: 이전까지의 토론 결과
            plan_content: 원본 계획
            context: 추가 컨텍스트
            user_focus: 사용자가 집중하길 원하는 주제 (선택)

        Returns:
            업데이트된 DebateResult

        Raises:
            ValueError: 최대 라운드 초과 시
        """
        if debate_result.round_count >= self.MAX_ROUNDS:
            raise ValueError(f"Maximum rounds ({self.MAX_ROUNDS}) reached")

        next_round = debate_result.round_count + 1
        history = debate_result.format_history()

        prompt = self._build_debate_prompt(
            plan_content=plan_content,
            history=history,
            round_number=next_round,
            user_focus=user_focus,
        )

        parallel_result = self.reviewer.review(prompt, context)

        new_round = DebateRound(
            round_number=next_round,
            gpt_response=parallel_result.gpt_review.content if parallel_result.gpt_review else None,
            claude_response=parallel_result.claude_review.content if parallel_result.claude_review else None,
            gpt_error=parallel_result.gpt_error,
            claude_error=parallel_result.claude_error,
        )

        debate_result.rounds.append(new_round)
        return debate_result

    def _build_initial_prompt(self, plan_content: str, review_type: str) -> str:
        """Round 1 프롬프트 (기존과 동일)"""
        if review_type == "code":
            return self._build_code_review_prompt(plan_content)
        return self._build_plan_review_prompt(plan_content)

    def _build_plan_review_prompt(self, plan_content: str) -> str:
        """계획 리뷰 프롬프트"""
        return f"""## 계획
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
추상적인 조언 대신 코드나 명세 수정 예시를 포함해줘."""

    def _build_code_review_prompt(self, diff: str) -> str:
        """코드 리뷰 프롬프트"""
        return f"""## 구현된 코드 (diff)
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
파일명:라인번호 형식으로 위치를 명시해줘."""

    def _build_debate_prompt(
        self,
        plan_content: str,
        history: str,
        round_number: int,
        user_focus: str | None = None,
    ) -> str:
        """토론 라운드 프롬프트"""
        focus_instruction = ""
        if user_focus:
            focus_instruction = f"\n\n**사용자 요청**: 특히 '{user_focus}'에 대해 집중적으로 논의해줘.\n"

        return f"""## 원본 계획
{plan_content}

## 지금까지의 토론
{history}

## Round {round_number} 요청{focus_instruction}

상대방(다른 모델)의 이전 의견을 읽고 응답해줘.

### 1. 동의하는 부분
상대방 의견 중 타당한 점이 있다면 인정해줘.

### 2. 반박하는 부분
동의하지 않는 점이 있다면:
- 어떤 점이 틀렸거나 과장되었는지
- 왜 그렇게 생각하는지 근거 제시
- 대안이 있다면 제시

### 3. 새로운 관점
이전에 언급되지 않았지만 중요한 점이 있다면 추가해줘.

### 4. 현재 입장 요약
지금 시점에서 이 계획/코드에 대한 전반적인 평가를 한 문장으로."""
