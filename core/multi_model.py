"""
Multi-Model Review Engine

N개 모델 병렬 호출로 다양한 관점의 리뷰 수집.
"""

from collections import Counter
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from dataclasses import dataclass, field
import re
from typing import Sequence

from .models import ModelClient, ModelResponse


@dataclass
class MultiModelReviewResult:
    """다중 모델 리뷰 결과"""
    reviews: list[ModelResponse | None]
    errors: list[str | None]
    synthesized: str = ""
    consensus_score: float = 0.0

    @property
    def success_count(self) -> int:
        """성공한 리뷰 수"""
        return sum(1 for r in self.reviews if r is not None)

    @property
    def total_count(self) -> int:
        """전체 모델 수"""
        return len(self.reviews)

    @property
    def all_success(self) -> bool:
        """모든 리뷰 성공 여부"""
        return all(r is not None for r in self.reviews)

    @property
    def any_success(self) -> bool:
        """최소 하나 이상 성공 여부"""
        return any(r is not None for r in self.reviews)

    def to_dict(self) -> dict:
        """딕셔너리로 변환"""
        return {
            "reviews": [r.content if r else None for r in self.reviews],
            "errors": self.errors,
            "synthesized": self.synthesized,
            "consensus_score": self.consensus_score,
            "success_count": self.success_count,
            "total_count": self.total_count,
        }


class MultiModelReviewer:
    """
    N개 모델 병렬 호출 리뷰어

    Usage:
        from core.models import ClaudeClient, CodexClient

        clients = [
            CodexClient(),
            ClaudeClient(model="sonnet"),
            ClaudeClient(model="haiku"),
        ]
        reviewer = MultiModelReviewer(clients)
        result = reviewer.review("이 코드를 리뷰해줘", context="def foo(): pass")
        print(result.consensus_score)
        print(result.synthesized)
    """

    # 합의도 계산용 키워드
    CONSENSUS_KEYWORDS = [
        # 보안
        "security", "vulnerability", "injection", "xss", "csrf", "auth",
        "보안", "취약점", "인증",
        # 성능
        "performance", "slow", "memory", "cpu", "optimization",
        "성능", "최적화", "메모리",
        # 코드 품질
        "error", "exception", "bug", "fix",
        "에러", "버그", "오류",
        # 아키텍처
        "architecture", "design", "pattern", "structure",
        "아키텍처", "설계", "패턴", "구조",
        # 스타일
        "naming", "convention", "format", "style", "readable",
        "네이밍", "컨벤션", "가독성", "스타일",
    ]

    def __init__(
        self,
        clients: Sequence[ModelClient],
        timeout: int = 300,
    ):
        """
        Args:
            clients: 모델 클라이언트 리스트 (최소 1개)
            timeout: 개별 모델 호출 타임아웃 (초)

        Raises:
            ValueError: clients가 비어있는 경우
        """
        if not clients:
            raise ValueError("At least one model client is required")
        self.clients = list(clients)
        self.timeout = timeout

    def review(
        self,
        prompt: str,
        context: str | None = None,
        parallel_timeout: int | None = None,
    ) -> MultiModelReviewResult:
        """
        모든 모델에게 병렬로 리뷰 요청

        Args:
            prompt: 리뷰 요청 프롬프트
            context: 추가 컨텍스트
            parallel_timeout: 병렬 호출 전체 타임아웃 (기본: 개별 타임아웃의 1.5배)

        Returns:
            MultiModelReviewResult
        """
        timeout = parallel_timeout or int(self.timeout * 1.5)

        reviews: list[ModelResponse | None] = [None] * len(self.clients)
        errors: list[str | None] = [None] * len(self.clients)

        def call_model(idx: int, client: ModelClient) -> tuple[int, ModelResponse | None, str | None]:
            try:
                response = client.call(prompt, context)
                return idx, response, None
            except Exception as e:
                return idx, None, f"{client.name}: {e}"

        with ThreadPoolExecutor(max_workers=len(self.clients)) as executor:
            futures = [
                executor.submit(call_model, idx, client)
                for idx, client in enumerate(self.clients)
            ]

            for future in futures:
                try:
                    idx, response, error = future.result(timeout=timeout)
                    reviews[idx] = response
                    errors[idx] = error
                except FuturesTimeoutError:
                    # 타임아웃 시 모든 미완료 작업에 에러 기록
                    for i, r in enumerate(reviews):
                        if r is None and errors[i] is None:
                            errors[i] = f"{self.clients[i].name}: Timed out after {timeout}s"
                    break
                except Exception as e:
                    # 예상치 못한 에러
                    for i, r in enumerate(reviews):
                        if r is None and errors[i] is None:
                            errors[i] = f"{self.clients[i].name}: Unexpected error: {e}"
                    break

        # 결과 종합
        successful_reviews = [r for r in reviews if r is not None]
        consensus_score = self._calculate_consensus(successful_reviews)
        synthesized = self._synthesize(reviews, errors, consensus_score)

        return MultiModelReviewResult(
            reviews=reviews,
            errors=errors,
            synthesized=synthesized,
            consensus_score=consensus_score,
        )

    def _calculate_consensus(self, reviews: list[ModelResponse]) -> float:
        """
        합의도 점수 계산 (0.0 ~ 1.0)

        키워드 일치도 기반 휴리스틱:
        - 각 키워드가 몇 개의 리뷰에서 언급되었는지 계산
        - 과반수(50% 이상) 이상의 리뷰에서 언급된 키워드 비율

        예: 3개 모델, 키워드 10개
        - 키워드 A: 3개 모델 모두 언급 → 과반수 충족
        - 키워드 B: 2개 모델 언급 → 과반수 충족
        - 키워드 C: 1개 모델 언급 → 과반수 미충족
        - 합의도 = (충족 키워드 수) / (언급된 총 키워드 수)
        """
        if len(reviews) < 2:
            # 리뷰가 1개 이하면 합의도 계산 불가
            return 0.0 if len(reviews) == 0 else 1.0

        # 각 리뷰에서 키워드 추출
        keyword_counts: Counter[str] = Counter()
        for review in reviews:
            content_lower = review.content.lower()
            for keyword in self.CONSENSUS_KEYWORDS:
                if keyword.lower() in content_lower:
                    keyword_counts[keyword] += 1

        if not keyword_counts:
            # 키워드가 하나도 없으면 합의도 0
            return 0.0

        # 과반수 기준 계산
        threshold = len(reviews) / 2
        consensus_keywords = sum(1 for count in keyword_counts.values() if count > threshold)
        total_keywords = len(keyword_counts)

        return consensus_keywords / total_keywords

    def _synthesize(
        self,
        reviews: list[ModelResponse | None],
        errors: list[str | None],
        consensus_score: float,
    ) -> str:
        """리뷰 결과 종합"""
        parts = []
        parts.append("# Multi-Model Review Summary\n")
        parts.append(f"**Consensus Score: {consensus_score:.2f}**\n")

        # 각 모델 리뷰
        for i, (review, error) in enumerate(zip(reviews, errors)):
            model_name = self.clients[i].name if i < len(self.clients) else f"Model {i}"
            parts.append(f"## {model_name}\n")
            if review:
                parts.append(review.content)
            else:
                parts.append(f"*Error: {error}*")
            parts.append("\n---\n")

        # 공통 키워드 추출
        successful_reviews = [r for r in reviews if r is not None]
        if len(successful_reviews) >= 2:
            parts.append("## Common Concerns\n")
            common = self._extract_common_keywords(successful_reviews)
            if common:
                parts.append(f"Keywords mentioned by multiple models: {', '.join(common)}")
            else:
                parts.append("*No common keywords detected.*")

        return "\n".join(parts)

    def _extract_common_keywords(self, reviews: list[ModelResponse]) -> list[str]:
        """여러 리뷰에서 공통으로 언급된 키워드 추출"""
        if len(reviews) < 2:
            return []

        keyword_counts: Counter[str] = Counter()
        for review in reviews:
            content_lower = review.content.lower()
            for keyword in self.CONSENSUS_KEYWORDS:
                if keyword.lower() in content_lower:
                    keyword_counts[keyword] += 1

        # 2개 이상의 리뷰에서 언급된 키워드만 반환
        return [kw for kw, count in keyword_counts.items() if count >= 2]
