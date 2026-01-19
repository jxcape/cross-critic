"""
Workflow Engine

Cross-Critic 워크플로우 실행 엔진.
"""

from dataclasses import dataclass, field, asdict
from pathlib import Path
from enum import Enum
from datetime import datetime
import json
import uuid

from .models import ModelClient, OpenCodeClient, ClaudeClient
from .context import ContextCollector, ContextResult
from .checkpoints import CheckpointManager, CheckpointResult, Decision


class Phase(Enum):
    """워크플로우 Phase"""
    CONTEXT = 0
    PLAN = 1
    CODE = 2
    TEST = 3
    DONE = 4


@dataclass
class WorkflowState:
    """워크플로우 상태"""
    session_id: str = ""
    started_at: str = ""
    current_phase: Phase = Phase.CONTEXT
    plan_path: str | None = None
    context_result: ContextResult | None = None
    checkpoints: list[CheckpointResult] = field(default_factory=list)

    # Phase별 결과
    plan_review: str | None = None
    final_plan: str | None = None
    code_changes: dict | None = None
    code_review: str | None = None
    test_content: str | None = None
    test_result: dict | None = None

    def __post_init__(self):
        if not self.session_id:
            self.session_id = str(uuid.uuid4())[:8]
        if not self.started_at:
            self.started_at = datetime.now().isoformat()

    def to_dict(self) -> dict:
        """직렬화"""
        d = asdict(self)
        d["current_phase"] = self.current_phase.value
        d["checkpoints"] = [
            {
                "phase": c.phase,
                "decision": c.decision.value,
                "user_feedback": c.user_feedback,
                "timestamp": c.timestamp,
            }
            for c in self.checkpoints
        ]
        if self.context_result:
            d["context_result"] = {
                "plan_content": self.context_result.plan_content,
                "context_files": self.context_result.context_files,
            }
        return d

    def save(self, path: Path):
        """상태 저장"""
        path.write_text(json.dumps(self.to_dict(), indent=2, ensure_ascii=False))

    @classmethod
    def load(cls, path: Path) -> "WorkflowState":
        """상태 로드"""
        data = json.loads(path.read_text())
        state = cls(
            session_id=data["session_id"],
            started_at=data["started_at"],
            current_phase=Phase(data["current_phase"]),
            plan_path=data.get("plan_path"),
        )
        # 나머지 필드 복원...
        return state


class WorkflowEngine:
    """
    Cross-Critic 워크플로우 엔진

    Usage:
        engine = WorkflowEngine(project_root="/path/to/project")
        engine.run(plan_path="plan.md")
    """

    STATE_FILE = ".cross_critic_state.json"

    def __init__(
        self,
        project_root: str | Path,
        critic_client: ModelClient | None = None,
        checkpoint_manager: CheckpointManager | None = None,
    ):
        self.project_root = Path(project_root)
        self.critic_client = critic_client or OpenCodeClient()
        self.checkpoint_manager = checkpoint_manager or CheckpointManager()
        self.context_collector = ContextCollector(project_root)
        self.state = WorkflowState()

    def run(
        self,
        plan_path: str | None = None,
        plan_content: str | None = None,
        context_paths: list[str] | None = None,
        start_phase: Phase = Phase.CONTEXT,
    ) -> WorkflowState:
        """
        워크플로우 실행

        Args:
            plan_path: 계획 파일 경로
            plan_content: 계획 내용 (plan_path보다 우선)
            context_paths: 추가 context 파일들
            start_phase: 시작 Phase (재개 시 사용)

        Returns:
            최종 WorkflowState
        """
        # 계획 로드
        if plan_content:
            self.state.final_plan = plan_content
        elif plan_path:
            self.state.plan_path = plan_path
            self.state.final_plan = (self.project_root / plan_path).read_text()
        else:
            raise ValueError("plan_path 또는 plan_content 필요")

        self.state.current_phase = start_phase

        try:
            # Phase 0: Context 수집
            if self.state.current_phase == Phase.CONTEXT:
                if not self._phase_0_context(context_paths):
                    return self.state
                self.state.current_phase = Phase.PLAN
                self._save_state()

            # Phase 1: Plan Review
            if self.state.current_phase == Phase.PLAN:
                if not self._phase_1_plan():
                    return self.state
                self.state.current_phase = Phase.CODE
                self._save_state()

            # Phase 2: Code Review
            if self.state.current_phase == Phase.CODE:
                if not self._phase_2_code():
                    return self.state
                self.state.current_phase = Phase.TEST
                self._save_state()

            # Phase 3: Test
            if self.state.current_phase == Phase.TEST:
                if not self._phase_3_test():
                    return self.state
                self.state.current_phase = Phase.DONE
                self._save_state()

            print("\n✅ 워크플로우 완료!")
            return self.state

        except KeyboardInterrupt:
            print("\n\n⚠️ 중단됨. 상태가 저장되었습니다.")
            self._save_state()
            return self.state

    def _phase_0_context(self, additional_paths: list[str] | None) -> bool:
        """Phase 0: Context 수집"""
        print("\n📁 Phase 0: Context 수집")

        # 자동 탐지
        detected = self.context_collector.auto_detect(self.state.final_plan)
        if additional_paths:
            detected = list(set(detected + additional_paths))

        # Context 수집
        self.state.context_result = self.context_collector.collect(
            self.state.final_plan,
            detected
        )

        # 체크포인트
        display = "탐지된 파일:\n" + "\n".join(
            f"  - {f}" for f in self.state.context_result.context_files
        )
        result = self.checkpoint_manager.run_checkpoint("context", display)
        self.state.checkpoints.append(result)

        if result.decision == Decision.ABORT:
            print("❌ 중단됨")
            return False

        if result.decision == Decision.REQUEST_MODIFICATION and result.user_feedback:
            # 파일 추가/제거 처리
            # TODO: 파싱 로직 개선 필요
            pass

        return True

    def _phase_1_plan(self) -> bool:
        """Phase 1: Plan Review"""
        print("\n📋 Phase 1: Plan Review")

        # GPT에게 계획 리뷰 요청
        prompt = self._build_plan_review_prompt()
        context = self.state.context_result.to_prompt_context()

        print("  GPT에게 계획 리뷰 요청 중...")
        response = self.critic_client.call(prompt, context)
        self.state.plan_review = response.content

        # 체크포인트
        result = self.checkpoint_manager.run_checkpoint("plan_review", self.state.plan_review)
        self.state.checkpoints.append(result)

        if result.decision == Decision.ABORT:
            print("❌ 중단됨")
            return False

        if result.decision == Decision.CONTINUE_WITHOUT_FEEDBACK:
            print("  리뷰 무시하고 진행")
        elif result.decision in (Decision.CONTINUE, Decision.CONTINUE_WITH_FEEDBACK):
            # 리뷰 반영은 Claude가 처리할 예정
            print("  리뷰 반영 예정")

        return True

    def _phase_2_code(self) -> bool:
        """Phase 2: Code Review"""
        print("\n💻 Phase 2: Code Review")

        # 이 단계에서는 Claude가 코드를 작성한 후 호출됨
        # 현재는 placeholder
        print("  [Claude가 코드 작성 중...]")
        print("  [코드 작성 후 GPT 리뷰 진행 예정]")

        # GPT 코드 리뷰는 코드 변경 후 호출
        # self.state.code_review = self.critic_client.call(...)

        # 임시 체크포인트
        result = self.checkpoint_manager.run_checkpoint(
            "code_review",
            "[코드 리뷰 내용이 여기 표시됨]"
        )
        self.state.checkpoints.append(result)

        if result.decision == Decision.ABORT:
            print("❌ 중단됨")
            return False

        return True

    def _phase_3_test(self) -> bool:
        """Phase 3: Test Generation"""
        print("\n🧪 Phase 3: Test Generation")

        # GPT에게 테스트 작성 요청
        prompt = self._build_test_prompt()
        context = self.state.context_result.to_prompt_context()

        print("  GPT에게 테스트 작성 요청 중...")
        response = self.critic_client.call(prompt, context)
        self.state.test_content = response.content

        # 체크포인트
        result = self.checkpoint_manager.run_checkpoint("test_review", self.state.test_content)
        self.state.checkpoints.append(result)

        if result.decision == Decision.ABORT:
            print("❌ 중단됨")
            return False

        if result.decision == Decision.SKIP:
            print("  테스트 스킵")
            return True

        # 테스트 실행은 Claude가 처리
        print("  [테스트 실행 예정]")

        return True

    def _build_plan_review_prompt(self) -> str:
        """Plan review 프롬프트 생성"""
        return f"""## 계획
{self.state.final_plan}

## 요청
위 계획을 비판적으로 리뷰해줘:

1. **요구사항 누락**: 빠진 요구사항이나 edge case는?
2. **해석 오류**: 모호하거나 잘못 해석된 부분은?
3. **대안 제시**: 더 나은 접근법이 있다면?
4. **잠재적 문제**: 구현 시 예상되는 문제점은?
5. **테스트 가능성**: 이 계획으로 테스트 작성이 가능한가?

구체적인 피드백과 함께 개선 제안을 해줘."""

    def _build_test_prompt(self) -> str:
        """Test 작성 프롬프트 생성"""
        return f"""## 계획
{self.state.final_plan}

## 요청
이 계획에 대한 테스트 코드를 작성해줘:

1. **정상 케이스**: 기본 동작 검증
2. **Edge case**: 경계값, 빈 입력, 최대값 등
3. **에러 케이스**: 예외 상황 처리 검증
4. **요구사항 검증**: 계획에 명시된 요구사항 충족 확인

pytest 형식으로 작성해줘."""

    def _save_state(self):
        """상태 저장"""
        state_path = self.project_root / self.STATE_FILE
        self.state.save(state_path)
        print(f"  💾 상태 저장됨: {state_path}")

    def resume(self) -> WorkflowState:
        """중단된 워크플로우 재개"""
        state_path = self.project_root / self.STATE_FILE
        if not state_path.exists():
            raise FileNotFoundError("저장된 상태가 없습니다")

        self.state = WorkflowState.load(state_path)
        print(f"📂 세션 {self.state.session_id} 재개 (Phase {self.state.current_phase.value})")

        return self.run(
            plan_content=self.state.final_plan,
            start_phase=self.state.current_phase,
        )
