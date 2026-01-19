"""Test context collector"""

import pytest
from pathlib import Path
import tempfile
import os

from core.context import ContextCollector, ContextResult


class TestContextResult:
    def test_to_prompt_context(self):
        result = ContextResult(
            plan_content="test plan",
            context_files=["file1.py", "file2.md"],
            context_contents={
                "file1.py": "print('hello')",
                "file2.md": "# Title",
            }
        )
        prompt_ctx = result.to_prompt_context()

        assert "file1.py" in prompt_ctx
        assert "file2.md" in prompt_ctx
        assert "print('hello')" in prompt_ctx
        assert "# Title" in prompt_ctx


class TestContextCollector:
    @pytest.fixture
    def temp_project(self):
        """임시 프로젝트 디렉토리 생성"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # 디렉토리 구조 생성
            os.makedirs(os.path.join(tmpdir, "specs"))
            os.makedirs(os.path.join(tmpdir, "src"))

            # 파일 생성
            Path(os.path.join(tmpdir, "specs", "agent.md")).write_text("# Agent Spec")
            Path(os.path.join(tmpdir, "specs", "tasks.md")).write_text("# Tasks Spec")
            Path(os.path.join(tmpdir, "src", "pipeline.py")).write_text(
                "def process_data():\n    pass"
            )
            Path(os.path.join(tmpdir, "src", "utils.py")).write_text(
                "class Helper:\n    pass"
            )

            yield tmpdir

    def test_auto_detect_specs(self, temp_project):
        collector = ContextCollector(temp_project)
        detected = collector.auto_detect("some plan content")

        # specs/ 디렉토리는 항상 포함
        assert any("specs/agent.md" in f for f in detected)
        assert any("specs/tasks.md" in f for f in detected)

    def test_auto_detect_file_paths(self, temp_project):
        collector = ContextCollector(temp_project)
        plan = "이 계획에서 src/pipeline.py 파일을 수정한다"
        detected = collector.auto_detect(plan)

        assert any("pipeline.py" in f for f in detected)

    def test_auto_detect_code_refs(self, temp_project):
        collector = ContextCollector(temp_project)
        plan = "계획에서 `process_data` 함수를 사용한다"
        detected = collector.auto_detect(plan)

        # process_data가 정의된 파일이 탐지되어야 함
        assert any("pipeline.py" in f for f in detected)

    def test_collect(self, temp_project):
        collector = ContextCollector(temp_project)
        result = collector.collect(
            plan_content="test plan",
            context_files=["specs/agent.md", "src/pipeline.py"]
        )

        assert result.plan_content == "test plan"
        assert len(result.context_files) == 2
        assert "specs/agent.md" in result.context_files
        assert "# Agent Spec" in result.context_contents["specs/agent.md"]

    def test_collect_nonexistent_file(self, temp_project):
        collector = ContextCollector(temp_project)
        result = collector.collect(
            plan_content="test plan",
            context_files=["nonexistent.py", "specs/agent.md"]
        )

        # 존재하지 않는 파일은 제외
        assert len(result.context_files) == 1
        assert "specs/agent.md" in result.context_files

    def test_add_files(self, temp_project):
        collector = ContextCollector(temp_project)
        result = collector.collect(
            plan_content="test plan",
            context_files=["specs/agent.md"]
        )

        new_result = collector.add_files(result, ["src/pipeline.py"])

        assert len(new_result.context_files) == 2
        assert "src/pipeline.py" in new_result.context_files

    def test_remove_files(self, temp_project):
        collector = ContextCollector(temp_project)
        result = collector.collect(
            plan_content="test plan",
            context_files=["specs/agent.md", "src/pipeline.py"]
        )

        new_result = collector.remove_files(result, ["specs/agent.md"])

        assert len(new_result.context_files) == 1
        assert "src/pipeline.py" in new_result.context_files
        assert "specs/agent.md" not in new_result.context_files
