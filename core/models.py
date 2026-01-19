"""
Model Clients

다양한 LLM 모델과 통신하는 클라이언트.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
import subprocess
import shutil


@dataclass
class ModelResponse:
    """모델 응답"""
    content: str
    model: str
    tokens_used: int | None = None
    raw_response: dict | None = None


class ModelClient(ABC):
    """모델 클라이언트 추상 클래스"""

    @abstractmethod
    def call(self, prompt: str, context: str | None = None) -> ModelResponse:
        """모델 호출"""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """모델 사용 가능 여부"""
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """모델 이름"""
        pass


class OpenCodeClient(ModelClient):
    """
    OpenCode CLI 클라이언트 (GPT 모델)

    Usage:
        client = OpenCodeClient()
        if client.is_available():
            response = client.call("리뷰해줘", context="코드 내용")
    """

    def __init__(self, timeout: int = 300, max_retries: int = 3):
        self.timeout = timeout
        self.max_retries = max_retries

    @property
    def name(self) -> str:
        return "opencode-gpt"

    def is_available(self) -> bool:
        """OpenCode CLI 설치 및 인증 확인"""
        if not shutil.which("opencode"):
            return False

        # 간단한 테스트 호출
        try:
            result = subprocess.run(
                ["opencode", "-p", "hello", "-q"],
                capture_output=True,
                timeout=30,
                text=True
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False

    def call(self, prompt: str, context: str | None = None) -> ModelResponse:
        """
        OpenCode CLI로 GPT 호출

        Args:
            prompt: 프롬프트
            context: 추가 컨텍스트 (프롬프트 앞에 추가됨)

        Returns:
            ModelResponse

        Raises:
            OpenCodeError: 호출 실패 시
        """
        full_prompt = prompt
        if context:
            full_prompt = f"{context}\n\n---\n\n{prompt}"

        last_error = None
        for attempt in range(self.max_retries):
            try:
                result = subprocess.run(
                    ["opencode", "-p", full_prompt, "-q"],
                    capture_output=True,
                    timeout=self.timeout,
                    text=True
                )

                if result.returncode != 0:
                    last_error = OpenCodeError(f"OpenCode failed: {result.stderr}")
                    continue

                return ModelResponse(
                    content=result.stdout.strip(),
                    model=self.name,
                )

            except subprocess.TimeoutExpired:
                last_error = OpenCodeError(f"OpenCode timed out after {self.timeout}s")
                continue

        raise last_error or OpenCodeError("Unknown error")


class ClaudeClient(ModelClient):
    """
    Claude CLI 서브에이전트

    현재 세션과 다른 새 세션으로 리뷰 수행.
    claude -p "프롬프트" --model sonnet

    현재 세션과 별개의 독립적 관점을 제공:
    - 기존 Claude Code 구독으로 커버 (추가 비용 없음)
    - GPT와 동일한 CLI 기반 인터페이스

    Usage:
        client = ClaudeClient(model="sonnet")
        if client.is_available():
            response = client.call("리뷰해줘", context="코드 내용")
    """

    AVAILABLE_MODELS = ["sonnet", "opus", "haiku"]

    def __init__(self, model: str = "sonnet", timeout: int = 300, max_retries: int = 3):
        if model not in self.AVAILABLE_MODELS:
            raise ValueError(f"Unknown model: {model}. Available: {self.AVAILABLE_MODELS}")
        self.model = model
        self.timeout = timeout
        self.max_retries = max_retries

    @property
    def name(self) -> str:
        return f"claude-{self.model}"

    def is_available(self) -> bool:
        """Claude CLI 설치 확인"""
        return shutil.which("claude") is not None

    def call(self, prompt: str, context: str | None = None) -> ModelResponse:
        """
        Claude CLI 호출 (독립 세션)

        Args:
            prompt: 프롬프트
            context: 추가 컨텍스트 (프롬프트 앞에 추가됨)

        Returns:
            ModelResponse

        Raises:
            ClaudeError: 호출 실패 시
        """
        full_prompt = prompt
        if context:
            full_prompt = f"{context}\n\n---\n\n{prompt}"

        last_error = None
        for attempt in range(self.max_retries):
            try:
                result = subprocess.run(
                    ["claude", "-p", full_prompt, "--model", self.model, "--output-format", "text"],
                    capture_output=True,
                    timeout=self.timeout,
                    text=True
                )

                if result.returncode != 0:
                    last_error = ClaudeError(f"Claude failed: {result.stderr}")
                    continue

                return ModelResponse(
                    content=result.stdout.strip(),
                    model=self.name,
                )

            except subprocess.TimeoutExpired:
                last_error = ClaudeError(f"Claude timed out after {self.timeout}s")
                continue

        raise last_error or ClaudeError("Unknown error")


class CodexClient(ModelClient):
    """
    OpenAI Codex CLI 클라이언트

    Usage:
        client = CodexClient()
        if client.is_available():
            response = client.call("리뷰해줘", context="코드 내용")
    """

    def __init__(self, timeout: int = 300, max_retries: int = 3):
        self.timeout = timeout
        self.max_retries = max_retries

    @property
    def name(self) -> str:
        return "codex-gpt"

    def is_available(self) -> bool:
        """Codex CLI 설치 확인"""
        return shutil.which("codex") is not None

    def call(self, prompt: str, context: str | None = None) -> ModelResponse:
        """
        Codex CLI로 GPT 호출

        Args:
            prompt: 프롬프트
            context: 추가 컨텍스트 (프롬프트 앞에 추가됨)

        Returns:
            ModelResponse

        Raises:
            CodexError: 호출 실패 시
        """
        import tempfile
        import os

        full_prompt = prompt
        if context:
            full_prompt = f"{context}\n\n---\n\n{prompt}"

        last_error = None
        for attempt in range(self.max_retries):
            try:
                # 임시 파일로 출력 저장
                with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
                    output_file = f.name

                result = subprocess.run(
                    ["codex", "exec", full_prompt, "-o", output_file],
                    capture_output=True,
                    timeout=self.timeout,
                    text=True
                )

                if result.returncode != 0:
                    last_error = CodexError(f"Codex failed: {result.stderr}")
                    continue

                # 출력 파일에서 응답 읽기
                try:
                    with open(output_file, 'r') as f:
                        content = f.read().strip()
                finally:
                    os.unlink(output_file)

                return ModelResponse(
                    content=content,
                    model=self.name,
                )

            except subprocess.TimeoutExpired:
                last_error = CodexError(f"Codex timed out after {self.timeout}s")
                continue

        raise last_error or CodexError("Unknown error")


class OpenCodeError(Exception):
    """OpenCode CLI 에러"""
    pass


class ClaudeError(Exception):
    """Claude CLI 에러"""
    pass


class CodexError(Exception):
    """Codex CLI 에러"""
    pass
