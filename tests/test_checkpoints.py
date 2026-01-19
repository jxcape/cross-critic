"""Test checkpoint manager"""

import pytest
from datetime import datetime

from core.checkpoints import (
    Decision,
    CheckpointResult,
    Checkpoint,
    CheckpointManager,
)


class TestDecision:
    def test_decision_values(self):
        assert Decision.CONTINUE.value == "continue"
        assert Decision.ABORT.value == "abort"
        assert Decision.REQUEST_MODIFICATION.value == "request_modification"


class TestCheckpointResult:
    def test_create_result(self):
        result = CheckpointResult(
            phase=1,
            decision=Decision.CONTINUE,
            user_feedback="looks good"
        )
        assert result.phase == 1
        assert result.decision == Decision.CONTINUE
        assert result.user_feedback == "looks good"
        assert result.timestamp  # auto-generated

    def test_auto_timestamp(self):
        result = CheckpointResult(phase=0, decision=Decision.ABORT)
        # timestamp가 ISO format인지 확인
        datetime.fromisoformat(result.timestamp)


class TestCheckpointManager:
    def test_default_checkpoints_exist(self):
        assert "context" in CheckpointManager.CHECKPOINTS
        assert "plan_review" in CheckpointManager.CHECKPOINTS
        assert "code_review" in CheckpointManager.CHECKPOINTS
        assert "test_review" in CheckpointManager.CHECKPOINTS

    def test_auto_mode(self):
        manager = CheckpointManager(auto_mode=True)
        result = manager.run_checkpoint("context", "test display")

        assert result.decision == Decision.CONTINUE
        assert len(manager.history) == 1

    def test_custom_input_handler(self):
        def mock_handler(prompt, options):
            return Decision.ABORT, "cancelled by user"

        manager = CheckpointManager(input_handler=mock_handler)
        result = manager.run_checkpoint("context", "test display")

        assert result.decision == Decision.ABORT
        assert result.user_feedback == "cancelled by user"

    def test_history_tracking(self):
        manager = CheckpointManager(auto_mode=True)

        manager.run_checkpoint("context", "display 1")
        manager.run_checkpoint("plan_review", "display 2")

        history = manager.get_history()
        assert len(history) == 2
        assert history[0].phase == 0
        assert history[1].phase == 1

    def test_clear_history(self):
        manager = CheckpointManager(auto_mode=True)
        manager.run_checkpoint("context", "display")

        manager.clear_history()
        assert len(manager.history) == 0

    def test_checkpoint_phases(self):
        """체크포인트별 phase 번호 확인"""
        checkpoints = CheckpointManager.CHECKPOINTS

        assert checkpoints["context"].phase == 0
        assert checkpoints["plan_review"].phase == 1
        assert checkpoints["code_review"].phase == 2
        assert checkpoints["test_review"].phase == 3
