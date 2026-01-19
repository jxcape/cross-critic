"""
Checkpoint Manager

사용자 체크포인트 관리. 각 Phase에서 사람의 확인을 받는다.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Callable
from datetime import datetime


class Decision(Enum):
    """체크포인트 결정"""
    CONTINUE = "continue"                       # 진행
    CONTINUE_WITH_FEEDBACK = "continue_with_feedback"  # 피드백 반영 후 진행
    CONTINUE_WITHOUT_FEEDBACK = "continue_without_feedback"  # 피드백 무시하고 진행
    REQUEST_MODIFICATION = "request_modification"  # 수정 요청
    SKIP = "skip"                               # 스킵 (예: 테스트 없이 종료)
    ABORT = "abort"                             # 중단


@dataclass
class CheckpointResult:
    """체크포인트 결과"""
    phase: int
    decision: Decision
    user_feedback: str | None = None
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()


@dataclass
class Checkpoint:
    """체크포인트 정의"""
    phase: int
    name: str
    prompt: str
    display_content_key: str  # 표시할 내용의 키
    options: list[tuple[str, Decision]]  # (label, decision) 쌍


class CheckpointManager:
    """
    체크포인트 관리자

    Usage:
        manager = CheckpointManager(input_handler=my_input_fn)
        result = manager.run_checkpoint(checkpoint, display_content)
    """

    # 기본 체크포인트 정의
    CHECKPOINTS = {
        "context": Checkpoint(
            phase=0,
            name="Context 확인",
            prompt="이 파일들을 GPT에게 전달할까요?",
            display_content_key="context_files",
            options=[
                ("진행", Decision.CONTINUE),
                ("파일 추가", Decision.REQUEST_MODIFICATION),
                ("파일 제거", Decision.REQUEST_MODIFICATION),
                ("중단", Decision.ABORT),
            ]
        ),
        "plan_review": Checkpoint(
            phase=1,
            name="Plan Review 확인",
            prompt="GPT 계획 리뷰를 확인하세요",
            display_content_key="gpt_review",
            options=[
                ("진행 (리뷰 반영)", Decision.CONTINUE_WITH_FEEDBACK),
                ("수정 요청", Decision.REQUEST_MODIFICATION),
                ("리뷰 무시하고 진행", Decision.CONTINUE_WITHOUT_FEEDBACK),
                ("중단", Decision.ABORT),
            ]
        ),
        "code_review": Checkpoint(
            phase=2,
            name="Code Review 확인",
            prompt="GPT 코드 리뷰를 확인하세요",
            display_content_key="gpt_code_review",
            options=[
                ("진행 (리뷰 반영)", Decision.CONTINUE_WITH_FEEDBACK),
                ("수정 요청", Decision.REQUEST_MODIFICATION),
                ("리뷰 무시하고 진행", Decision.CONTINUE_WITHOUT_FEEDBACK),
                ("중단", Decision.ABORT),
            ]
        ),
        "test_review": Checkpoint(
            phase=3,
            name="Test 확인",
            prompt="GPT가 작성한 테스트를 확인하세요",
            display_content_key="gpt_tests",
            options=[
                ("진행 (테스트 실행)", Decision.CONTINUE),
                ("테스트 수정 요청", Decision.REQUEST_MODIFICATION),
                ("테스트 없이 종료", Decision.SKIP),
                ("중단", Decision.ABORT),
            ]
        ),
    }

    def __init__(
        self,
        input_handler: Callable[[str, list[tuple[str, Decision]]], tuple[Decision, str | None]] | None = None,
        auto_mode: bool = False
    ):
        """
        Args:
            input_handler: 사용자 입력을 받는 함수
                - 인자: (prompt, options)
                - 반환: (decision, user_feedback)
            auto_mode: True면 모든 체크포인트 자동 통과 (위험!)
        """
        self.input_handler = input_handler or self._default_input_handler
        self.auto_mode = auto_mode
        self.history: list[CheckpointResult] = []

    def _default_input_handler(
        self,
        prompt: str,
        options: list[tuple[str, Decision]]
    ) -> tuple[Decision, str | None]:
        """기본 입력 핸들러 (CLI)"""
        print(f"\n{'='*60}")
        print(f"🔴 CHECKPOINT: {prompt}")
        print(f"{'='*60}\n")

        for i, (label, _) in enumerate(options, 1):
            print(f"  [{i}] {label}")

        print()
        while True:
            try:
                choice = input("선택 (번호): ").strip()
                idx = int(choice) - 1
                if 0 <= idx < len(options):
                    decision = options[idx][1]

                    # 피드백이 필요한 경우
                    feedback = None
                    if decision in (Decision.REQUEST_MODIFICATION, Decision.CONTINUE_WITH_FEEDBACK):
                        feedback = input("피드백 (Enter로 스킵): ").strip() or None

                    return decision, feedback
            except (ValueError, IndexError):
                print("올바른 번호를 입력하세요")

    def run_checkpoint(
        self,
        checkpoint_name: str,
        display_content: str
    ) -> CheckpointResult:
        """
        체크포인트 실행

        Args:
            checkpoint_name: 체크포인트 이름 (CHECKPOINTS 키)
            display_content: 사용자에게 보여줄 내용

        Returns:
            CheckpointResult
        """
        checkpoint = self.CHECKPOINTS[checkpoint_name]

        # Auto mode면 자동 통과
        if self.auto_mode:
            result = CheckpointResult(
                phase=checkpoint.phase,
                decision=Decision.CONTINUE,
            )
            self.history.append(result)
            return result

        # 내용 표시
        print(f"\n{'-'*60}")
        print(display_content)
        print(f"{'-'*60}\n")

        # 사용자 입력
        decision, feedback = self.input_handler(checkpoint.prompt, checkpoint.options)

        result = CheckpointResult(
            phase=checkpoint.phase,
            decision=decision,
            user_feedback=feedback,
        )
        self.history.append(result)

        return result

    def get_history(self) -> list[CheckpointResult]:
        """체크포인트 히스토리 반환"""
        return self.history.copy()

    def clear_history(self):
        """히스토리 초기화"""
        self.history.clear()
