"""Test model clients"""

import pytest
from unittest.mock import patch, MagicMock
import subprocess

from core.models import (
    ModelResponse,
    OpenCodeClient,
    ClaudeClient,
    CodexClient,
    OpenCodeError,
    CodexError,
)


class TestModelResponse:
    def test_create_response(self):
        response = ModelResponse(
            content="test content",
            model="test-model",
            tokens_used=100,
        )
        assert response.content == "test content"
        assert response.model == "test-model"
        assert response.tokens_used == 100


class TestOpenCodeClient:
    def test_name(self):
        client = OpenCodeClient()
        assert client.name == "opencode-gpt"

    @patch("shutil.which")
    def test_is_available_no_cli(self, mock_which):
        mock_which.return_value = None
        client = OpenCodeClient()
        assert client.is_available() is False

    @patch("shutil.which")
    @patch("subprocess.run")
    def test_is_available_with_cli(self, mock_run, mock_which):
        mock_which.return_value = "/usr/local/bin/opencode"
        mock_run.return_value = MagicMock(returncode=0)
        client = OpenCodeClient()
        assert client.is_available() is True

    @patch("subprocess.run")
    def test_call_success(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="GPT response content",
            stderr="",
        )
        client = OpenCodeClient()
        response = client.call("test prompt")

        assert response.content == "GPT response content"
        assert response.model == "opencode-gpt"
        mock_run.assert_called_once()

    @patch("subprocess.run")
    def test_call_with_context(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="response",
            stderr="",
        )
        client = OpenCodeClient()
        client.call("prompt", context="some context")

        call_args = mock_run.call_args[0][0]
        # 프롬프트에 context가 포함되어야 함
        assert "some context" in call_args[2]
        assert "prompt" in call_args[2]

    @patch("subprocess.run")
    def test_call_failure_retry(self, mock_run):
        # 처음 2번 실패, 3번째 성공
        mock_run.side_effect = [
            MagicMock(returncode=1, stderr="error 1"),
            MagicMock(returncode=1, stderr="error 2"),
            MagicMock(returncode=0, stdout="success", stderr=""),
        ]
        client = OpenCodeClient(max_retries=3)
        response = client.call("test")

        assert response.content == "success"
        assert mock_run.call_count == 3

    @patch("subprocess.run")
    def test_call_all_retries_fail(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stderr="error")
        client = OpenCodeClient(max_retries=3)

        with pytest.raises(OpenCodeError):
            client.call("test")

        assert mock_run.call_count == 3

    @patch("subprocess.run")
    def test_call_timeout(self, mock_run):
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="opencode", timeout=300)
        client = OpenCodeClient(max_retries=1)

        with pytest.raises(OpenCodeError) as exc_info:
            client.call("test")

        assert "timed out" in str(exc_info.value)


class TestClaudeClient:
    def test_name(self):
        client = ClaudeClient()
        assert client.name == "claude-sonnet"  # 기본 모델: sonnet

    def test_name_with_model(self):
        client = ClaudeClient(model="haiku")
        assert client.name == "claude-haiku"

        client = ClaudeClient(model="opus")
        assert client.name == "claude-opus"

    def test_invalid_model(self):
        import pytest
        with pytest.raises(ValueError):
            ClaudeClient(model="invalid")

    @patch("shutil.which")
    def test_is_available(self, mock_which):
        mock_which.return_value = "/usr/local/bin/claude"
        client = ClaudeClient()
        assert client.is_available() is True

        mock_which.return_value = None
        assert client.is_available() is False


class TestCodexClient:
    def test_name(self):
        client = CodexClient()
        assert client.name == "codex-gpt"

    @patch("shutil.which")
    def test_is_available(self, mock_which):
        mock_which.return_value = "/opt/homebrew/bin/codex"
        client = CodexClient()
        assert client.is_available() is True

        mock_which.return_value = None
        assert client.is_available() is False

    @patch("subprocess.run")
    @patch("builtins.open", create=True)
    @patch("os.unlink")
    @patch("tempfile.NamedTemporaryFile")
    def test_call_success(self, mock_tempfile, mock_unlink, mock_open, mock_run):
        # Setup mocks
        mock_tempfile.return_value.__enter__.return_value.name = "/tmp/test.txt"
        mock_run.return_value = MagicMock(returncode=0, stderr="")
        mock_open.return_value.__enter__.return_value.read.return_value = "GPT response"

        client = CodexClient()
        response = client.call("test prompt")

        assert response.content == "GPT response"
        assert response.model == "codex-gpt"

    @patch("subprocess.run")
    @patch("tempfile.NamedTemporaryFile")
    def test_call_failure(self, mock_tempfile, mock_run):
        mock_tempfile.return_value.__enter__.return_value.name = "/tmp/test.txt"
        mock_run.return_value = MagicMock(returncode=1, stderr="error")

        client = CodexClient(max_retries=1)
        with pytest.raises(CodexError):
            client.call("test")
