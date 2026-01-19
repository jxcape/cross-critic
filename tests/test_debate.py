"""DebateEngine 테스트"""

import pytest
from unittest.mock import Mock, patch
from core.debate import DebateEngine, DebateResult, DebateRound
from core.parallel_review import ParallelReviewResult
from core.models import ModelResponse


class TestDebateRound:
    """DebateRound 데이터클래스 테스트"""

    def test_round_with_responses(self):
        """정상 응답이 있는 라운드"""
        r = DebateRound(
            round_number=1,
            gpt_response="GPT says",
            claude_response="Claude says",
        )
        assert r.round_number == 1
        assert r.gpt_response == "GPT says"
        assert r.claude_response == "Claude says"
        assert r.gpt_error is None
        assert r.claude_error is None

    def test_round_with_errors(self):
        """에러가 있는 라운드"""
        r = DebateRound(
            round_number=2,
            gpt_response=None,
            claude_response="Claude says",
            gpt_error="GPT timed out",
        )
        assert r.gpt_response is None
        assert r.gpt_error == "GPT timed out"
        assert r.claude_response == "Claude says"


class TestDebateResult:
    """DebateResult 데이터클래스 테스트"""

    def test_empty_result(self):
        """빈 결과"""
        result = DebateResult()
        assert result.round_count == 0
        assert result.latest_round is None

    def test_latest_round(self):
        """latest_round 프로퍼티"""
        result = DebateResult(rounds=[
            DebateRound(round_number=1, gpt_response="1", claude_response="1"),
            DebateRound(round_number=2, gpt_response="2", claude_response="2"),
        ])
        assert result.latest_round.round_number == 2

    def test_round_count(self):
        """round_count 프로퍼티"""
        result = DebateResult(rounds=[
            DebateRound(round_number=1, gpt_response="", claude_response=""),
            DebateRound(round_number=2, gpt_response="", claude_response=""),
            DebateRound(round_number=3, gpt_response="", claude_response=""),
        ])
        assert result.round_count == 3

    def test_format_history(self):
        """format_history()가 올바른 형식 생성하는지"""
        result = DebateResult(rounds=[
            DebateRound(round_number=1, gpt_response="GPT 1", claude_response="Claude 1"),
            DebateRound(round_number=2, gpt_response="GPT 2", claude_response="Claude 2"),
        ])

        history = result.format_history()

        assert "## Round 1" in history
        assert "## Round 2" in history
        assert "### GPT" in history
        assert "### Claude" in history
        assert "GPT 1" in history
        assert "Claude 2" in history

    def test_format_history_with_error(self):
        """에러가 있을 때 format_history()"""
        result = DebateResult(rounds=[
            DebateRound(
                round_number=1,
                gpt_response=None,
                claude_response="Claude works",
                gpt_error="GPT failed",
            ),
        ])

        history = result.format_history()

        assert "*Error: GPT failed*" in history
        assert "Claude works" in history


class TestDebateEngine:
    """DebateEngine 테스트"""

    def test_start_creates_round_1(self):
        """start()가 Round 1을 생성하는지"""
        mock_reviewer = Mock()
        mock_reviewer.review.return_value = ParallelReviewResult(
            gpt_review=ModelResponse(content="GPT opinion", model="gpt"),
            claude_review=ModelResponse(content="Claude opinion", model="claude"),
        )

        engine = DebateEngine(reviewer=mock_reviewer)
        result = engine.start("Test plan", review_type="plan")

        assert result.round_count == 1
        assert result.latest_round.round_number == 1
        assert result.latest_round.gpt_response == "GPT opinion"
        assert result.latest_round.claude_response == "Claude opinion"

    def test_start_with_context(self):
        """start()가 context를 전달하는지"""
        mock_reviewer = Mock()
        mock_reviewer.review.return_value = ParallelReviewResult(
            gpt_review=ModelResponse(content="GPT", model="gpt"),
            claude_review=ModelResponse(content="Claude", model="claude"),
        )

        engine = DebateEngine(reviewer=mock_reviewer)
        engine.start("Test plan", context="Some context", review_type="plan")

        # review()가 context와 함께 호출되었는지 확인
        call_args = mock_reviewer.review.call_args
        assert call_args[0][1] == "Some context"

    def test_start_code_review(self):
        """start()가 code review 타입을 처리하는지"""
        mock_reviewer = Mock()
        mock_reviewer.review.return_value = ParallelReviewResult(
            gpt_review=ModelResponse(content="GPT code review", model="gpt"),
            claude_review=ModelResponse(content="Claude code review", model="claude"),
        )

        engine = DebateEngine(reviewer=mock_reviewer)
        result = engine.start("diff content", review_type="code")

        # 프롬프트에 코드 리뷰 관련 내용이 있는지 확인
        call_args = mock_reviewer.review.call_args
        prompt = call_args[0][0]
        assert "구현된 코드" in prompt or "diff" in prompt.lower()

    def test_continue_adds_round(self):
        """continue_debate()가 라운드를 추가하는지"""
        mock_reviewer = Mock()
        mock_reviewer.review.return_value = ParallelReviewResult(
            gpt_review=ModelResponse(content="GPT round 2", model="gpt"),
            claude_review=ModelResponse(content="Claude round 2", model="claude"),
        )

        engine = DebateEngine(reviewer=mock_reviewer)

        # 기존 Round 1
        existing = DebateResult(rounds=[
            DebateRound(round_number=1, gpt_response="GPT r1", claude_response="Claude r1")
        ])

        result = engine.continue_debate(existing, "Test plan")

        assert result.round_count == 2
        assert result.latest_round.round_number == 2
        assert result.latest_round.gpt_response == "GPT round 2"

    def test_continue_includes_history(self):
        """continue_debate()가 히스토리를 프롬프트에 포함하는지"""
        mock_reviewer = Mock()
        mock_reviewer.review.return_value = ParallelReviewResult(
            gpt_review=ModelResponse(content="", model="gpt"),
            claude_review=ModelResponse(content="", model="claude"),
        )

        engine = DebateEngine(reviewer=mock_reviewer)
        existing = DebateResult(rounds=[
            DebateRound(round_number=1, gpt_response="Previous GPT", claude_response="Previous Claude")
        ])

        engine.continue_debate(existing, "Test plan")

        call_args = mock_reviewer.review.call_args
        prompt = call_args[0][0]
        assert "Previous GPT" in prompt
        assert "Previous Claude" in prompt

    def test_max_rounds_enforced(self):
        """최대 라운드 제한이 작동하는지"""
        engine = DebateEngine()

        # 5라운드 채운 상태
        existing = DebateResult(rounds=[
            DebateRound(round_number=i, gpt_response="", claude_response="")
            for i in range(1, 6)
        ])

        with pytest.raises(ValueError, match="Maximum rounds"):
            engine.continue_debate(existing, "Test plan")

    def test_handles_partial_failure_gpt(self):
        """GPT 실패 시에도 동작하는지"""
        mock_reviewer = Mock()
        mock_reviewer.review.return_value = ParallelReviewResult(
            gpt_review=None,
            claude_review=ModelResponse(content="Claude works", model="claude"),
            gpt_error="GPT timed out",
        )

        engine = DebateEngine(reviewer=mock_reviewer)
        result = engine.start("Test plan")

        assert result.latest_round.gpt_response is None
        assert result.latest_round.gpt_error == "GPT timed out"
        assert result.latest_round.claude_response == "Claude works"

    def test_handles_partial_failure_claude(self):
        """Claude 실패 시에도 동작하는지"""
        mock_reviewer = Mock()
        mock_reviewer.review.return_value = ParallelReviewResult(
            gpt_review=ModelResponse(content="GPT works", model="gpt"),
            claude_review=None,
            claude_error="Claude timed out",
        )

        engine = DebateEngine(reviewer=mock_reviewer)
        result = engine.start("Test plan")

        assert result.latest_round.gpt_response == "GPT works"
        assert result.latest_round.claude_response is None
        assert result.latest_round.claude_error == "Claude timed out"

    def test_user_focus_included_in_prompt(self):
        """user_focus가 프롬프트에 포함되는지"""
        mock_reviewer = Mock()
        mock_reviewer.review.return_value = ParallelReviewResult(
            gpt_review=ModelResponse(content="", model="gpt"),
            claude_review=ModelResponse(content="", model="claude"),
        )

        engine = DebateEngine(reviewer=mock_reviewer)
        existing = DebateResult(rounds=[
            DebateRound(round_number=1, gpt_response="", claude_response="")
        ])

        engine.continue_debate(existing, "Test plan", user_focus="에러 처리")

        # review() 호출 시 전달된 prompt 확인
        call_args = mock_reviewer.review.call_args
        prompt = call_args[0][0]
        assert "에러 처리" in prompt

    def test_default_claude_model(self):
        """기본 claude_model이 설정되는지"""
        with patch('core.debate.ParallelReviewer') as mock_class:
            DebateEngine()
            mock_class.assert_called_once_with(claude_model="sonnet")

    def test_custom_claude_model(self):
        """커스텀 claude_model이 전달되는지"""
        with patch('core.debate.ParallelReviewer') as mock_class:
            DebateEngine(claude_model="haiku")
            mock_class.assert_called_once_with(claude_model="haiku")

    def test_plan_review_prompt_structure(self):
        """계획 리뷰 프롬프트 구조"""
        engine = DebateEngine(reviewer=Mock())
        prompt = engine._build_plan_review_prompt("My plan")

        assert "## 계획" in prompt
        assert "My plan" in prompt
        assert "Step 1: Fatal Flaw" in prompt
        assert "Step 2: Missing Requirements" in prompt
        assert "Step 3: Edge Cases" in prompt
        assert "Step 4: Actionable Improvements" in prompt

    def test_code_review_prompt_structure(self):
        """코드 리뷰 프롬프트 구조"""
        engine = DebateEngine(reviewer=Mock())
        prompt = engine._build_code_review_prompt("diff content")

        assert "구현된 코드" in prompt
        assert "diff content" in prompt
        assert "Fatal Flaw" in prompt
        assert "Plan Deviation" in prompt

    def test_debate_prompt_structure(self):
        """토론 프롬프트 구조"""
        engine = DebateEngine(reviewer=Mock())
        prompt = engine._build_debate_prompt(
            plan_content="My plan",
            history="Previous history",
            round_number=2,
        )

        assert "원본 계획" in prompt
        assert "My plan" in prompt
        assert "지금까지의 토론" in prompt
        assert "Previous history" in prompt
        assert "Round 2" in prompt
        assert "동의하는 부분" in prompt
        assert "반박하는 부분" in prompt
        assert "새로운 관점" in prompt
        assert "현재 입장 요약" in prompt
