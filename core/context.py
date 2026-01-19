"""
Context Collector

계획에서 관련 파일을 자동 탐지하고 Context를 수집.
"""

from dataclasses import dataclass, field
from pathlib import Path
import re
from glob import glob


@dataclass
class ContextResult:
    """Context 수집 결과"""
    plan_content: str
    context_files: list[str] = field(default_factory=list)
    context_contents: dict[str, str] = field(default_factory=dict)

    def to_prompt_context(self) -> str:
        """GPT에게 전달할 context 문자열 생성"""
        parts = []
        for path, content in self.context_contents.items():
            parts.append(f"## File: {path}\n```\n{content}\n```")
        return "\n\n".join(parts)


class ContextCollector:
    """
    Context 자동 탐지 및 수집

    Usage:
        collector = ContextCollector(project_root="/path/to/project")
        detected = collector.auto_detect(plan_content)
        result = collector.collect(plan_content, detected)
    """

    # 파일 경로 패턴 (예: src/pipeline.py, ./core/models.py)
    FILE_PATTERN = re.compile(r'[`"\']?([./\w]+\.(py|ts|js|md|yaml|json))[`"\']?')

    # 함수/클래스 참조 패턴 (예: `process_data`, `ContextCollector`)
    CODE_REF_PATTERN = re.compile(r'`(\w+(?:\.\w+)*)`')

    def __init__(self, project_root: str | Path):
        self.project_root = Path(project_root)

    def auto_detect(self, plan_content: str) -> list[str]:
        """
        계획에서 관련 파일 자동 탐지

        탐지 순서:
        1. specs/ 디렉토리 전체
        2. 계획에서 언급된 파일 경로
        3. 코드 참조로 grep

        Returns:
            탐지된 파일 경로 리스트
        """
        detected = set()

        # 1. specs/ 전체
        specs_dir = self.project_root / "specs"
        if specs_dir.exists():
            for md_file in specs_dir.glob("**/*.md"):
                detected.add(str(md_file.relative_to(self.project_root)))

        # 2. 파일 경로 추출
        file_matches = self.FILE_PATTERN.findall(plan_content)
        for match in file_matches:
            file_path = match[0] if isinstance(match, tuple) else match
            # 상대 경로 정규화
            if file_path.startswith("./"):
                file_path = file_path[2:]

            full_path = self.project_root / file_path
            if full_path.exists():
                detected.add(file_path)
            else:
                # glob 패턴으로 시도
                matches = glob(str(self.project_root / file_path))
                for m in matches:
                    rel_path = str(Path(m).relative_to(self.project_root))
                    detected.add(rel_path)

        # 3. 코드 참조로 grep (간단 구현)
        code_refs = self.CODE_REF_PATTERN.findall(plan_content)
        for ref in code_refs:
            # 함수/클래스 이름으로 파일 찾기
            found = self._find_definition(ref)
            detected.update(found)

        return sorted(detected)

    def _find_definition(self, name: str) -> list[str]:
        """함수/클래스 정의가 있는 파일 찾기"""
        found = []
        patterns = [
            f"def {name}",
            f"class {name}",
            f"async def {name}",
        ]

        for py_file in self.project_root.glob("**/*.py"):
            if "__pycache__" in str(py_file):
                continue
            try:
                content = py_file.read_text()
                for pattern in patterns:
                    if pattern in content:
                        found.append(str(py_file.relative_to(self.project_root)))
                        break
            except Exception:
                continue

        return found

    def collect(
        self,
        plan_content: str,
        context_files: list[str]
    ) -> ContextResult:
        """
        Context 수집

        Args:
            plan_content: 계획 내용
            context_files: 포함할 파일 경로들

        Returns:
            ContextResult
        """
        contents = {}
        valid_files = []

        for file_path in context_files:
            full_path = self.project_root / file_path
            if full_path.exists():
                try:
                    contents[file_path] = full_path.read_text()
                    valid_files.append(file_path)
                except Exception:
                    continue

        return ContextResult(
            plan_content=plan_content,
            context_files=valid_files,
            context_contents=contents,
        )

    def add_files(
        self,
        result: ContextResult,
        additional_files: list[str]
    ) -> ContextResult:
        """기존 결과에 파일 추가"""
        new_files = result.context_files.copy()
        new_contents = result.context_contents.copy()

        for file_path in additional_files:
            if file_path not in new_files:
                full_path = self.project_root / file_path
                if full_path.exists():
                    try:
                        new_contents[file_path] = full_path.read_text()
                        new_files.append(file_path)
                    except Exception:
                        continue

        return ContextResult(
            plan_content=result.plan_content,
            context_files=new_files,
            context_contents=new_contents,
        )

    def remove_files(
        self,
        result: ContextResult,
        files_to_remove: list[str]
    ) -> ContextResult:
        """기존 결과에서 파일 제거"""
        new_files = [f for f in result.context_files if f not in files_to_remove]
        new_contents = {k: v for k, v in result.context_contents.items() if k not in files_to_remove}

        return ContextResult(
            plan_content=result.plan_content,
            context_files=new_files,
            context_contents=new_contents,
        )
