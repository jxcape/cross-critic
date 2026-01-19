"""
병렬 리뷰 모듈 테스트
"""

import json
import pytest
from pathlib import Path
from unittest.mock import Mock, patch

from core.parallel_review import (
    ParallelReviewer,
    ParallelReviewResult,
    ReviewConflict,
    ConflictType,
    LoopManager,
    LoopState,
)
from core.models import ModelResponse


class TestConflictType:
    def test_conflict_types_exist(self):
        assert ConflictType.SECURITY.value == "security"
        assert ConflictType.PERFORMANCE.value == "performance"
        assert ConflictType.STYLE.value == "style"
        assert ConflictType.ARCHITECTURE.value == "architecture"


class TestReviewConflict:
    def test_create_conflict(self):
        conflict = ReviewConflict(
            type=ConflictType.SECURITY,
            gpt_opinion="SQL injection detected",
            claude_opinion="No security concern",
            recommended="Review GPT's concern",
        )
        assert conflict.type == ConflictType.SECURITY
        assert "SQL injection" in conflict.gpt_opinion


class TestParallelReviewResult:
    def test_success_with_both(self):
        result = ParallelReviewResult(
            gpt_review=ModelResponse(content="GPT review", model="gpt"),
            claude_review=ModelResponse(content="Claude review", model="claude"),
        )
        assert result.success is True
        assert result.both_success is True

    def test_success_with_one(self):
        result = ParallelReviewResult(
            gpt_review=ModelResponse(content="GPT review", model="gpt"),
            claude_review=None,
            claude_error="Timeout",
        )
        assert result.success is True
        assert result.both_success is False

    def test_no_success(self):
        result = ParallelReviewResult(
            gpt_review=None,
            claude_review=None,
            gpt_error="Error 1",
            claude_error="Error 2",
        )
        assert result.success is False
        assert result.both_success is False

    def test_to_dict(self):
        result = ParallelReviewResult(
            gpt_review=ModelResponse(content="GPT review", model="gpt"),
            claude_review=ModelResponse(content="Claude review", model="claude"),
            synthesized="Summary",
            conflicts=[
                ReviewConflict(
                    type=ConflictType.SECURITY,
                    gpt_opinion="Opinion 1",
                    claude_opinion="Opinion 2",
                )
            ],
        )
        d = result.to_dict()
        assert d["gpt_review"] == "GPT review"
        assert d["claude_review"] == "Claude review"
        assert d["synthesized"] == "Summary"
        assert len(d["conflicts"]) == 1
        assert d["conflicts"][0]["type"] == "security"


class TestParallelReviewer:
    @patch("core.parallel_review.CodexClient")
    @patch("core.parallel_review.ClaudeClient")
    def test_review_both_success(self, mock_claude_cls, mock_codex_cls):
        # Setup mocks
        mock_codex = Mock()
        mock_codex.call.return_value = ModelResponse(content="GPT says OK", model="gpt")
        mock_codex_cls.return_value = mock_codex

        mock_claude = Mock()
        mock_claude.call.return_value = ModelResponse(content="Claude says OK", model="claude")
        mock_claude_cls.return_value = mock_claude

        reviewer = ParallelReviewer()
        result = reviewer.review("Review this plan", "Context here")

        assert result.success is True
        assert result.both_success is True
        assert "GPT says OK" in result.synthesized
        assert "Claude says OK" in result.synthesized

    @patch("core.parallel_review.CodexClient")
    @patch("core.parallel_review.ClaudeClient")
    def test_review_gpt_fails(self, mock_claude_cls, mock_codex_cls):
        from core.models import CodexError

        mock_codex = Mock()
        mock_codex.call.side_effect = CodexError("API error")
        mock_codex_cls.return_value = mock_codex

        mock_claude = Mock()
        mock_claude.call.return_value = ModelResponse(content="Claude says OK", model="claude")
        mock_claude_cls.return_value = mock_claude

        reviewer = ParallelReviewer()
        result = reviewer.review("Review this plan")

        assert result.success is True  # Claude succeeded
        assert result.both_success is False
        assert result.gpt_error is not None

    def test_extract_common_concerns(self):
        reviewer = ParallelReviewer()
        gpt_content = "There are security issues with this code"
        claude_content = "I also noticed some security vulnerabilities"

        common = reviewer._extract_common_concerns(gpt_content, claude_content)
        assert "security" in common.lower()

    def test_detect_conflicts_security(self):
        reviewer = ParallelReviewer()

        gpt_review = ModelResponse(content="Security vulnerability found", model="gpt")
        claude_review = ModelResponse(content="Code looks good", model="claude")

        conflicts = reviewer._detect_conflicts(gpt_review, claude_review)

        assert len(conflicts) == 1
        assert conflicts[0].type == ConflictType.SECURITY


class TestLoopState:
    def test_default_state(self):
        state = LoopState()
        assert state.iteration == 1
        assert state.max_iterations == 5
        assert state.phase == "plan_review"
        assert state.resolved is False

    def test_to_dict(self):
        state = LoopState(iteration=3, phase="code_review", resolved=True)
        d = state.to_dict()
        assert d["iteration"] == 3
        assert d["phase"] == "code_review"
        assert d["resolved"] is True

    def test_from_dict(self):
        data = {
            "iteration": 2,
            "max_iterations": 10,
            "phase": "test",
            "last_conflicts": ["conflict1"],
            "resolved": False,
            "history": [{"event": "start"}],
        }
        state = LoopState.from_dict(data)
        assert state.iteration == 2
        assert state.max_iterations == 10
        assert state.phase == "test"
        assert len(state.last_conflicts) == 1


class TestLoopManager:
    def test_load_or_create_new(self, tmp_path):
        manager = LoopManager(tmp_path)
        state = manager.load_or_create()
        assert state.iteration == 1

    def test_save_and_load(self, tmp_path):
        manager = LoopManager(tmp_path)
        state = LoopState(iteration=3, phase="code_review")
        manager.save(state)

        loaded = manager.load_or_create()
        assert loaded.iteration == 3
        assert loaded.phase == "code_review"

    def test_reset(self, tmp_path):
        manager = LoopManager(tmp_path)
        state = LoopState(iteration=5)
        manager.save(state)

        manager.reset()
        new_state = manager.load_or_create()
        assert new_state.iteration == 1

    def test_add_to_history(self, tmp_path):
        manager = LoopManager(tmp_path)
        state = LoopState()
        manager.add_to_history(state, "test_event", {"detail": "value"})

        assert len(state.history) == 1
        assert state.history[0]["event"] == "test_event"
        assert state.history[0]["details"]["detail"] == "value"
