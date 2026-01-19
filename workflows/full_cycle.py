"""
Full Cycle Workflow

Plan → Code → Test 전체 사이클 워크플로우.
"""

from pathlib import Path

from core import WorkflowEngine, CheckpointManager
from core.models import CodexClient
from core.workflow import Phase, WorkflowState


class FullCycleWorkflow:
    """
    Full Cycle Cross-Critic 워크플로우

    Phase 0: Context 수집 (자동탐지 + 사용자 조정)
    Phase 1: Plan (GPT 리뷰 → 사람 확인 → 반영)
    Phase 2: Code (GPT 리뷰 → 사람 확인 → 반영)
    Phase 3: Test (GPT 작성 → 사람 확인 → 실행)

    Usage:
        workflow = FullCycleWorkflow(project_root="/path/to/project")
        result = workflow.run(plan_path="plan.md")
    """

    def __init__(
        self,
        project_root: str | Path,
        auto_mode: bool = False,
    ):
        self.project_root = Path(project_root)
        self.auto_mode = auto_mode

        # 컴포넌트 초기화
        self.critic_client = CodexClient()
        self.checkpoint_manager = CheckpointManager(auto_mode=auto_mode)
        self.engine = WorkflowEngine(
            project_root=project_root,
            critic_client=self.critic_client,
            checkpoint_manager=self.checkpoint_manager,
        )

    def run(
        self,
        plan_path: str | None = None,
        plan_content: str | None = None,
        context_paths: list[str] | None = None,
    ) -> WorkflowState:
        """
        워크플로우 실행

        Args:
            plan_path: 계획 파일 경로
            plan_content: 계획 내용 (plan_path보다 우선)
            context_paths: 추가 context 파일들

        Returns:
            WorkflowState
        """
        # 사전 검증
        if not self.critic_client.is_available():
            raise RuntimeError(
                "OpenCode CLI가 설치되지 않았거나 인증되지 않았습니다.\n"
                "설치: https://opencode.ai/docs/cli/\n"
                "인증: opencode auth login"
            )

        return self.engine.run(
            plan_path=plan_path,
            plan_content=plan_content,
            context_paths=context_paths,
        )

    def resume(self) -> WorkflowState:
        """중단된 워크플로우 재개"""
        return self.engine.resume()

    def get_state(self) -> WorkflowState:
        """현재 상태 반환"""
        return self.engine.state
