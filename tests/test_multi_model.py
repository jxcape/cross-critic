"""
다중 모델 리뷰 모듈 테스트
"""

import pytest
from unittest.mock import Mock

from core.multi_model import MultiModelReviewer, MultiModelReviewResult
from core.models import ModelResponse, ModelClient


class MockClient(ModelClient):
    """테스트용 Mock 클라이언트"""

    def __init__(self, name: str = "mock", response: str = "Mock response", should_fail: bool = False):
        self._name = name
        self._response = response
        self._should_fail = should_fail

    @property
    def name(self) -> str:
        return self._name

    def is_available(self) -> bool:
        return True

    def call(self, prompt: str, context: str | None = None) -> ModelResponse:
        if self._should_fail:
            raise RuntimeError("Mock failure")
        return ModelResponse(content=self._response, model=self._name)


class TestMultiModelReviewResult:
    def test_success_count(self):
        result = MultiModelReviewResult(
            reviews=[
                ModelResponse(content="Review 1", model="m1"),
                None,
                ModelResponse(content="Review 3", model="m3"),
            ],
            errors=[None, "Error 2", None],
        )
        assert result.success_count == 2
        assert result.total_count == 3
        assert result.any_success is True
        assert result.all_success is False

    def test_all_success(self):
        result = MultiModelReviewResult(
            reviews=[
                ModelResponse(content="Review 1", model="m1"),
                ModelResponse(content="Review 2", model="m2"),
            ],
            errors=[None, None],
        )
        assert result.success_count == 2
        assert result.all_success is True
        assert result.any_success is True

    def test_no_success(self):
        result = MultiModelReviewResult(
            reviews=[None, None],
            errors=["Error 1", "Error 2"],
        )
        assert result.success_count == 0
        assert result.any_success is False
        assert result.all_success is False

    def test_to_dict(self):
        result = MultiModelReviewResult(
            reviews=[
                ModelResponse(content="Review 1", model="m1"),
                None,
            ],
            errors=[None, "Error"],
            synthesized="Summary",
            consensus_score=0.75,
        )
        d = result.to_dict()
        assert d["reviews"] == ["Review 1", None]
        assert d["errors"] == [None, "Error"]
        assert d["synthesized"] == "Summary"
        assert d["consensus_score"] == 0.75
        assert d["success_count"] == 1
        assert d["total_count"] == 2


class TestMultiModelReviewer:
    def test_multi_model_reviewer_basic(self):
        """3개 모델 병렬 호출"""
        clients = [
            MockClient("model-1", "Good code with security checks"),
            MockClient("model-2", "I found some security issues here"),
            MockClient("model-3", "The security implementation looks solid"),
        ]
        reviewer = MultiModelReviewer(clients)
        result = reviewer.review("Review this code", "def foo(): pass")

        assert result.success_count == 3
        assert result.all_success is True
        assert all(r is not None for r in result.reviews)
        assert all(e is None for e in result.errors)
        # consensus_score > 0 because all mention "security"
        assert result.consensus_score > 0

    def test_multi_model_partial_failure(self):
        """일부 모델 실패해도 결과 반환"""
        clients = [
            MockClient("model-1", "Good review"),
            MockClient("model-2", "Error", should_fail=True),
            MockClient("model-3", "Another good review"),
        ]
        reviewer = MultiModelReviewer(clients)
        result = reviewer.review("Review this")

        assert result.success_count == 2
        assert result.any_success is True
        assert result.all_success is False
        assert result.reviews[0] is not None
        assert result.reviews[1] is None
        assert result.reviews[2] is not None
        assert result.errors[1] is not None
        assert "Mock failure" in result.errors[1]

    def test_consensus_score_calculation(self):
        """합의도 점수 계산"""
        # 3개 모델 중 모두 "security" 언급 → 높은 합의도
        clients = [
            MockClient("m1", "security vulnerability found"),
            MockClient("m2", "security is a concern here"),
            MockClient("m3", "security issue detected"),
        ]
        reviewer = MultiModelReviewer(clients)
        result = reviewer.review("Review")

        # security 키워드가 3/3 모델에서 언급 → 과반수 충족
        assert result.consensus_score > 0

    def test_consensus_score_zero_no_keywords(self):
        """키워드가 없으면 합의도 0"""
        clients = [
            MockClient("m1", "looks good"),
            MockClient("m2", "nice work"),
            MockClient("m3", "approved"),
        ]
        reviewer = MultiModelReviewer(clients)
        result = reviewer.review("Review")

        assert result.consensus_score == 0.0

    def test_consensus_score_partial_agreement(self):
        """부분 동의 시 합의도"""
        # 3개 모델: 2개가 security 언급, 1개는 performance + slow 언급
        clients = [
            MockClient("m1", "security issue found"),
            MockClient("m2", "security concern here"),
            MockClient("m3", "performance is slow"),
        ]
        reviewer = MultiModelReviewer(clients)
        result = reviewer.review("Review")

        # security: 2/3 > 1.5 (과반) → 충족
        # performance: 1/3 < 1.5 → 미충족
        # slow: 1/3 < 1.5 → 미충족
        # 총 3개 키워드 언급, 1개만 과반 충족 → 1/3 ≈ 0.33
        assert 0.3 <= result.consensus_score <= 0.4

    def test_consensus_score_single_model(self):
        """단일 모델은 합의도 1.0"""
        clients = [MockClient("m1", "security review")]
        reviewer = MultiModelReviewer(clients)
        result = reviewer.review("Review")

        assert result.consensus_score == 1.0

    def test_multi_model_empty_list(self):
        """빈 리스트 에러 처리"""
        with pytest.raises(ValueError, match="At least one model client is required"):
            MultiModelReviewer([])

    def test_synthesized_output_format(self):
        """종합 출력 형식 확인"""
        clients = [
            MockClient("model-alpha", "Alpha review content"),
            MockClient("model-beta", "Beta review content"),
        ]
        reviewer = MultiModelReviewer(clients)
        result = reviewer.review("Review this")

        assert "# Multi-Model Review Summary" in result.synthesized
        assert "model-alpha" in result.synthesized
        assert "model-beta" in result.synthesized
        assert "Alpha review content" in result.synthesized
        assert "Beta review content" in result.synthesized
        assert "Consensus Score:" in result.synthesized

    def test_synthesized_with_errors(self):
        """에러 있을 때 종합 출력"""
        clients = [
            MockClient("model-ok", "Good review"),
            MockClient("model-fail", should_fail=True),
        ]
        reviewer = MultiModelReviewer(clients)
        result = reviewer.review("Review")

        assert "model-ok" in result.synthesized
        assert "Good review" in result.synthesized
        assert "*Error:" in result.synthesized

    def test_extract_common_keywords(self):
        """공통 키워드 추출"""
        clients = [
            MockClient("m1", "security and performance issues"),
            MockClient("m2", "security is important, check the auth"),
            MockClient("m3", "performance optimization needed"),
        ]
        reviewer = MultiModelReviewer(clients)
        result = reviewer.review("Review")

        # security: 2/3, performance: 2/3 → 둘 다 common
        assert "Common Concerns" in result.synthesized

    def test_with_context(self):
        """컨텍스트 전달 확인"""
        call_args = []

        class TrackingClient(ModelClient):
            @property
            def name(self) -> str:
                return "tracking"

            def is_available(self) -> bool:
                return True

            def call(self, prompt: str, context: str | None = None) -> ModelResponse:
                call_args.append((prompt, context))
                return ModelResponse(content="OK", model="tracking")

        reviewer = MultiModelReviewer([TrackingClient()])
        reviewer.review("Test prompt", context="Test context")

        assert len(call_args) == 1
        assert call_args[0][0] == "Test prompt"
        assert call_args[0][1] == "Test context"

    def test_multiple_models_same_type(self):
        """같은 종류 모델 여러 개"""
        clients = [
            MockClient("claude-sonnet", "Sonnet review"),
            MockClient("claude-haiku", "Haiku review"),
            MockClient("claude-opus", "Opus review"),
        ]
        reviewer = MultiModelReviewer(clients)
        result = reviewer.review("Review")

        assert result.success_count == 3
        assert "claude-sonnet" in result.synthesized
        assert "claude-haiku" in result.synthesized
        assert "claude-opus" in result.synthesized
