"""Test workflow engine"""

import pytest
from pathlib import Path
import tempfile
import os
import json

from core.workflow import (
    Phase,
    WorkflowState,
    WorkflowEngine,
)
from core.checkpoints import CheckpointManager, Decision
from core.models import ModelResponse


class TestPhase:
    def test_phase_values(self):
        assert Phase.CONTEXT.value == 0
        assert Phase.PLAN.value == 1
        assert Phase.CODE.value == 2
        assert Phase.TEST.value == 3
        assert Phase.DONE.value == 4


class TestWorkflowState:
    def test_create_state(self):
        state = WorkflowState()
        assert state.session_id  # auto-generated
        assert state.started_at  # auto-generated
        assert state.current_phase == Phase.CONTEXT

    def test_to_dict(self):
        state = WorkflowState(
            session_id="test-123",
            current_phase=Phase.PLAN,
            plan_path="plan.md",
        )
        d = state.to_dict()

        assert d["session_id"] == "test-123"
        assert d["current_phase"] == 1  # Phase.PLAN.value
        assert d["plan_path"] == "plan.md"

    def test_save_and_load(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / "state.json"

            state = WorkflowState(
                session_id="test-456",
                current_phase=Phase.CODE,
            )
            state.save(state_path)

            loaded = WorkflowState.load(state_path)
            assert loaded.session_id == "test-456"
            assert loaded.current_phase == Phase.CODE


class TestWorkflowEngine:
    @pytest.fixture
    def temp_project(self):
        """임시 프로젝트 디렉토리"""
        with tempfile.TemporaryDirectory() as tmpdir:
            os.makedirs(os.path.join(tmpdir, "specs"))
            Path(os.path.join(tmpdir, "specs", "test.md")).write_text("# Test Spec")
            Path(os.path.join(tmpdir, "plan.md")).write_text("# Test Plan\n\n구현 계획")
            yield tmpdir

    @pytest.fixture
    def mock_critic_client(self):
        """Mock critic client"""
        class MockClient:
            name = "mock"

            def is_available(self):
                return True

            def call(self, prompt, context=None):
                return ModelResponse(
                    content="Mock GPT review response",
                    model="mock",
                )

        return MockClient()

    @pytest.fixture
    def auto_checkpoint_manager(self):
        """자동 통과 체크포인트 매니저"""
        return CheckpointManager(auto_mode=True)

    def test_engine_init(self, temp_project, mock_critic_client):
        engine = WorkflowEngine(
            project_root=temp_project,
            critic_client=mock_critic_client,
        )
        assert engine.project_root == Path(temp_project)

    def test_run_requires_plan(self, temp_project, mock_critic_client, auto_checkpoint_manager):
        engine = WorkflowEngine(
            project_root=temp_project,
            critic_client=mock_critic_client,
            checkpoint_manager=auto_checkpoint_manager,
        )

        with pytest.raises(ValueError):
            engine.run()  # plan_path도 plan_content도 없음

    def test_run_with_plan_path(self, temp_project, mock_critic_client, auto_checkpoint_manager):
        engine = WorkflowEngine(
            project_root=temp_project,
            critic_client=mock_critic_client,
            checkpoint_manager=auto_checkpoint_manager,
        )

        state = engine.run(plan_path="plan.md")

        assert state.plan_path == "plan.md"
        assert state.final_plan is not None
        assert "Test Plan" in state.final_plan

    def test_run_with_plan_content(self, temp_project, mock_critic_client, auto_checkpoint_manager):
        engine = WorkflowEngine(
            project_root=temp_project,
            critic_client=mock_critic_client,
            checkpoint_manager=auto_checkpoint_manager,
        )

        state = engine.run(plan_content="Direct plan content")

        assert state.final_plan == "Direct plan content"

    def test_state_saved_on_phase_change(self, temp_project, mock_critic_client, auto_checkpoint_manager):
        engine = WorkflowEngine(
            project_root=temp_project,
            critic_client=mock_critic_client,
            checkpoint_manager=auto_checkpoint_manager,
        )

        engine.run(plan_path="plan.md")

        state_file = Path(temp_project) / ".cross_critic_state.json"
        assert state_file.exists()

    def test_abort_stops_workflow(self, temp_project, mock_critic_client):
        def abort_handler(prompt, options):
            return Decision.ABORT, None

        checkpoint_manager = CheckpointManager(input_handler=abort_handler)
        engine = WorkflowEngine(
            project_root=temp_project,
            critic_client=mock_critic_client,
            checkpoint_manager=checkpoint_manager,
        )

        state = engine.run(plan_path="plan.md")

        # Phase 0에서 abort했으므로 여전히 CONTEXT
        assert state.current_phase == Phase.CONTEXT
