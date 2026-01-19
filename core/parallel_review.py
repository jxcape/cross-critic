"""
Parallel Review Engine

GPT(Codex) + Claude 병렬 호출로 다양한 관점의 리뷰 수집.
"""

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from dataclasses import dataclass, field
from enum import Enum
import json
from pathlib import Path
from typing import Callable

from .models import CodexClient, ClaudeClient, ModelResponse, CodexError, ClaudeError


class ConflictType(Enum):
    """충돌 유형"""
    SECURITY = "security"       # 보안 관련 - 더 보수적인 의견 우선
    PERFORMANCE = "performance" # 성능 관련 - 측정 가능한 제안 우선
    STYLE = "style"             # 스타일 관련 - 사용자 선택
    ARCHITECTURE = "architecture"  # 아키텍처 - 양쪽 제시 후 사용자 결정


@dataclass
class ReviewConflict:
    """리뷰 간 충돌"""
    type: ConflictType
    gpt_opinion: str
    claude_opinion: str
    recommended: str | None = None  # 권장 의견 (있으면)


@dataclass
class ParallelReviewResult:
    """병렬 리뷰 결과"""
    gpt_review: ModelResponse | None
    claude_review: ModelResponse | None
    gpt_error: str | None = None
    claude_error: str | None = None
    synthesized: str = ""
    conflicts: list[ReviewConflict] = field(default_factory=list)

    @property
    def success(self) -> bool:
        """최소 하나의 리뷰가 성공했는지"""
        return self.gpt_review is not None or self.claude_review is not None

    @property
    def both_success(self) -> bool:
        """두 리뷰 모두 성공했는지"""
        return self.gpt_review is not None and self.claude_review is not None

    def to_dict(self) -> dict:
        """딕셔너리로 변환"""
        return {
            "gpt_review": self.gpt_review.content if self.gpt_review else None,
            "claude_review": self.claude_review.content if self.claude_review else None,
            "gpt_error": self.gpt_error,
            "claude_error": self.claude_error,
            "synthesized": self.synthesized,
            "conflicts": [
                {
                    "type": c.type.value,
                    "gpt_opinion": c.gpt_opinion,
                    "claude_opinion": c.claude_opinion,
                    "recommended": c.recommended,
                }
                for c in self.conflicts
            ],
        }


class ParallelReviewer:
    """
    GPT + Claude 병렬 호출 리뷰어

    Usage:
        reviewer = ParallelReviewer()
        result = reviewer.review(prompt, context)
        print(result.synthesized)
    """

    # 충돌 감지용 키워드
    SECURITY_KEYWORDS = ["security", "vulnerability", "injection", "xss", "csrf", "auth", "보안", "취약점"]
    PERFORMANCE_KEYWORDS = ["performance", "slow", "memory", "cpu", "optimization", "성능", "최적화"]
    STYLE_KEYWORDS = ["naming", "convention", "format", "style", "네이밍", "스타일", "컨벤션"]

    def __init__(
        self,
        gpt_client: CodexClient | None = None,
        claude_client: ClaudeClient | None = None,
        claude_model: str = "sonnet",
        timeout: int = 300,
    ):
        self.gpt_client = gpt_client or CodexClient(timeout=timeout)
        self.claude_client = claude_client or ClaudeClient(model=claude_model, timeout=timeout)
        self.timeout = timeout

    def review(
        self,
        prompt: str,
        context: str | None = None,
        parallel_timeout: int | None = None,
    ) -> ParallelReviewResult:
        """
        GPT와 Claude에게 병렬로 리뷰 요청

        Args:
            prompt: 리뷰 요청 프롬프트
            context: 추가 컨텍스트
            parallel_timeout: 병렬 호출 전체 타임아웃 (기본: 개별 타임아웃의 1.5배)

        Returns:
            ParallelReviewResult
        """
        timeout = parallel_timeout or int(self.timeout * 1.5)

        gpt_review = None
        claude_review = None
        gpt_error = None
        claude_error = None

        def call_gpt():
            return self.gpt_client.call(prompt, context)

        def call_claude():
            return self.claude_client.call(prompt, context)

        with ThreadPoolExecutor(max_workers=2) as executor:
            gpt_future = executor.submit(call_gpt)
            claude_future = executor.submit(call_claude)

            # GPT 결과 수집
            try:
                gpt_review = gpt_future.result(timeout=timeout)
            except FuturesTimeoutError:
                gpt_error = f"GPT timed out after {timeout}s"
            except CodexError as e:
                gpt_error = str(e)
            except Exception as e:
                gpt_error = f"GPT unexpected error: {e}"

            # Claude 결과 수집
            try:
                claude_review = claude_future.result(timeout=timeout)
            except FuturesTimeoutError:
                claude_error = f"Claude timed out after {timeout}s"
            except ClaudeError as e:
                claude_error = str(e)
            except Exception as e:
                claude_error = f"Claude unexpected error: {e}"

        # 결과 종합
        synthesized = self._synthesize(gpt_review, claude_review, gpt_error, claude_error)
        conflicts = self._detect_conflicts(gpt_review, claude_review)

        return ParallelReviewResult(
            gpt_review=gpt_review,
            claude_review=claude_review,
            gpt_error=gpt_error,
            claude_error=claude_error,
            synthesized=synthesized,
            conflicts=conflicts,
        )

    def _synthesize(
        self,
        gpt_review: ModelResponse | None,
        claude_review: ModelResponse | None,
        gpt_error: str | None,
        claude_error: str | None,
    ) -> str:
        """리뷰 결과 종합"""
        parts = []

        parts.append("# Parallel Review Summary\n")

        # GPT 리뷰
        parts.append("## GPT (Codex) Review\n")
        if gpt_review:
            parts.append(gpt_review.content)
        else:
            parts.append(f"*Error: {gpt_error}*")

        parts.append("\n---\n")

        # Claude 리뷰
        parts.append("## Claude Review\n")
        if claude_review:
            parts.append(claude_review.content)
        else:
            parts.append(f"*Error: {claude_error}*")

        # 공통 피드백 추출 시도
        if gpt_review and claude_review:
            parts.append("\n---\n")
            parts.append("## Common Concerns (Consensus)\n")
            common = self._extract_common_concerns(gpt_review.content, claude_review.content)
            if common:
                parts.append(common)
            else:
                parts.append("*No obvious consensus detected. Review both opinions.*")

        return "\n".join(parts)

    def _extract_common_concerns(self, gpt_content: str, claude_content: str) -> str:
        """두 리뷰에서 공통 우려사항 추출 (간단 휴리스틱)"""
        # 간단한 키워드 기반 공통점 찾기
        common_keywords = []

        all_keywords = self.SECURITY_KEYWORDS + self.PERFORMANCE_KEYWORDS + self.STYLE_KEYWORDS
        gpt_lower = gpt_content.lower()
        claude_lower = claude_content.lower()

        for keyword in all_keywords:
            if keyword in gpt_lower and keyword in claude_lower:
                common_keywords.append(keyword)

        if common_keywords:
            return f"Both reviewers mentioned: {', '.join(set(common_keywords))}"
        return ""

    def _detect_conflicts(
        self,
        gpt_review: ModelResponse | None,
        claude_review: ModelResponse | None,
    ) -> list[ReviewConflict]:
        """리뷰 간 충돌 감지"""
        if not gpt_review or not claude_review:
            return []

        conflicts = []
        gpt_content = gpt_review.content.lower()
        claude_content = claude_review.content.lower()

        # 간단한 충돌 감지: 한쪽에만 있는 중요 키워드
        for keyword in self.SECURITY_KEYWORDS:
            gpt_has = keyword in gpt_content
            claude_has = keyword in claude_content
            if gpt_has != claude_has:
                conflicts.append(ReviewConflict(
                    type=ConflictType.SECURITY,
                    gpt_opinion="Mentioned security concern" if gpt_has else "No security concern mentioned",
                    claude_opinion="Mentioned security concern" if claude_has else "No security concern mentioned",
                    recommended="Review security concern from: " + ("GPT" if gpt_has else "Claude"),
                ))
                break  # 하나만 기록

        return conflicts


@dataclass
class LoopState:
    """Ralph Loop 상태"""
    iteration: int = 1
    max_iterations: int = 5
    phase: str = "plan_review"
    last_conflicts: list[str] = field(default_factory=list)
    resolved: bool = False
    history: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "iteration": self.iteration,
            "max_iterations": self.max_iterations,
            "phase": self.phase,
            "last_conflicts": self.last_conflicts,
            "resolved": self.resolved,
            "history": self.history,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "LoopState":
        return cls(
            iteration=data.get("iteration", 1),
            max_iterations=data.get("max_iterations", 5),
            phase=data.get("phase", "plan_review"),
            last_conflicts=data.get("last_conflicts", []),
            resolved=data.get("resolved", False),
            history=data.get("history", []),
        )


class LoopManager:
    """
    Ralph Loop 상태 관리

    Usage:
        manager = LoopManager(project_dir)
        state = manager.load_or_create()
        state.iteration += 1
        manager.save(state)
    """

    STATE_FILE = ".cross-critic/loop_state.json"

    def __init__(self, project_dir: str | Path):
        self.project_dir = Path(project_dir)
        self.state_path = self.project_dir / self.STATE_FILE

    def load_or_create(self) -> LoopState:
        """상태 로드 또는 새로 생성"""
        if self.state_path.exists():
            try:
                data = json.loads(self.state_path.read_text())
                return LoopState.from_dict(data)
            except (json.JSONDecodeError, KeyError):
                pass
        return LoopState()

    def save(self, state: LoopState) -> None:
        """상태 저장"""
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps(state.to_dict(), indent=2, ensure_ascii=False))

    def reset(self) -> None:
        """상태 초기화"""
        if self.state_path.exists():
            self.state_path.unlink()

    def add_to_history(self, state: LoopState, event: str, details: dict | None = None) -> None:
        """히스토리에 이벤트 추가"""
        state.history.append({
            "iteration": state.iteration,
            "phase": state.phase,
            "event": event,
            "details": details or {},
        })
