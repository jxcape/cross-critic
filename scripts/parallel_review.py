#!/usr/bin/env python
"""
병렬 리뷰 CLI

GPT(Codex) + Claude 병렬 호출로 다양한 관점의 리뷰 수집.

Usage:
    # 계획 병렬 리뷰
    python scripts/parallel_review.py plan /path/to/plan.md

    # 코드 병렬 리뷰
    python scripts/parallel_review.py code /path/to/plan.md --project-dir /path/to/project

    # Context 파일 추가
    python scripts/parallel_review.py plan /path/to/plan.md --context specs/agent.md src/core.py

    # Claude 모델 선택 (기본: sonnet)
    python scripts/parallel_review.py plan /path/to/plan.md --claude-model haiku

    # 결과를 JSON으로 출력
    python scripts/parallel_review.py plan /path/to/plan.md --json
"""

import sys
import subprocess
import json
from pathlib import Path

# 프로젝트 루트 추가
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.parallel_review import ParallelReviewer, LoopManager
from core.context import ContextCollector


def build_plan_review_prompt(plan_content: str) -> str:
    """계획 리뷰 프롬프트 생성"""
    return f"""## 계획
{plan_content}

## 리뷰 요청

아래 단계에 따라 계획을 비판적으로 리뷰해줘.
각 단계에서 해당 사항이 없으면 "없음"이라고 명시해줘.

### Step 1: Fatal Flaw Detection (치명적 결함)
이 계획에 구현을 막거나 큰 문제를 야기할 치명적 결함이 있나?
- 기술적 불가능성
- 심각한 보안 취약점
- 근본적인 설계 오류

### Step 2: Missing Requirements (누락된 요구사항, 최대 3개)
빠진 요구사항이 있다면, **왜** 누락되면 안 되는지 근거와 함께 설명해줘.

### Step 3: Edge Cases (엣지 케이스, 최대 3개)
고려하지 않은 엣지 케이스가 있다면:
- 구체적인 입력 예시
- 예상되는 문제
- 권장 처리 방법

### Step 4: Actionable Improvements (즉시 적용 가능한 개선, 최대 3개)
바로 반영할 수 있는 구체적인 개선 제안.
추상적인 조언 대신 코드나 명세 수정 예시를 포함해줘."""


def build_code_review_prompt(plan_content: str, diff: str) -> str:
    """코드 리뷰 프롬프트 생성"""
    return f"""## 원래 계획
{plan_content}

## 구현된 코드 (diff)
{diff}

## 리뷰 요청

아래 단계에 따라 코드를 비판적으로 리뷰해줘.
각 단계에서 해당 사항이 없으면 "없음"이라고 명시해줘.

### Step 1: Fatal Flaw Detection (치명적 결함)
- 보안 취약점 (SQL injection, XSS, CSRF 등)
- 데이터 손실 가능성
- 무한 루프 / 데드락

### Step 2: Plan Deviation (계획 이탈)
계획과 다르게 구현된 부분이 있나?
- 누락된 기능
- 과도한 추가 기능 (over-engineering)
- 요구사항 오해

### Step 3: Edge Cases & Error Handling (엣지 케이스, 최대 3개)
- 구체적인 입력 예시
- 현재 코드의 동작
- 권장 수정 방법

### Step 4: Actionable Improvements (즉시 적용 가능한 개선, 최대 3개)
구체적인 코드 수정 예시를 포함해줘.
파일명:라인번호 형식으로 위치를 명시해줘."""


def get_git_diff(project_dir: str) -> str:
    """Git diff 수집"""
    result = subprocess.run(
        ["git", "diff", "--cached"],
        capture_output=True,
        text=True,
        cwd=project_dir
    )
    diff = result.stdout

    if not diff:
        result = subprocess.run(
            ["git", "diff"],
            capture_output=True,
            text=True,
            cwd=project_dir
        )
        diff = result.stdout

    return diff


def parallel_review_plan(
    plan_path: str,
    context_paths: list[str] | None = None,
    claude_model: str = "sonnet",
    output_json: bool = False,
) -> str:
    """계획 병렬 리뷰"""
    plan_content = Path(plan_path).read_text()

    # Context 수집
    context_str = ""
    if context_paths:
        plan_dir = Path(plan_path).parent
        collector = ContextCollector(plan_dir)
        context_result = collector.collect(plan_content, context_paths)
        context_str = context_result.to_prompt_context()

    prompt = build_plan_review_prompt(plan_content)

    reviewer = ParallelReviewer(claude_model=claude_model)
    result = reviewer.review(prompt, context_str if context_str else None)

    if output_json:
        return json.dumps(result.to_dict(), indent=2, ensure_ascii=False)
    return result.synthesized


def parallel_review_code(
    plan_path: str,
    project_dir: str | None = None,
    context_paths: list[str] | None = None,
    claude_model: str = "sonnet",
    output_json: bool = False,
) -> str:
    """코드 병렬 리뷰"""
    plan_content = Path(plan_path).read_text()

    # 프로젝트 디렉토리 결정
    if project_dir:
        cwd = project_dir
    else:
        cwd = str(Path(plan_path).parent)

    # Context 수집
    context_str = ""
    if context_paths:
        collector = ContextCollector(cwd)
        context_result = collector.collect(plan_content, context_paths)
        context_str = context_result.to_prompt_context()

    # Git diff 수집
    diff = get_git_diff(cwd)
    if not diff:
        return "변경사항이 없습니다."

    prompt = build_code_review_prompt(plan_content, diff)

    reviewer = ParallelReviewer(claude_model=claude_model)
    result = reviewer.review(prompt, context_str if context_str else None)

    if output_json:
        return json.dumps(result.to_dict(), indent=2, ensure_ascii=False)
    return result.synthesized


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)

    command = sys.argv[1]
    plan_path = sys.argv[2]

    # 인자 파싱
    project_dir = None
    context_paths = []
    claude_model = "sonnet"
    output_json = False

    i = 3
    while i < len(sys.argv):
        if sys.argv[i] == "--project-dir" and i + 1 < len(sys.argv):
            project_dir = sys.argv[i + 1]
            i += 2
        elif sys.argv[i] == "--context" and i + 1 < len(sys.argv):
            i += 1
            while i < len(sys.argv) and not sys.argv[i].startswith("--"):
                context_paths.append(sys.argv[i])
                i += 1
        elif sys.argv[i] == "--claude-model" and i + 1 < len(sys.argv):
            claude_model = sys.argv[i + 1]
            i += 2
        elif sys.argv[i] == "--json":
            output_json = True
            i += 1
        else:
            # 플래그 없는 인자는 context 파일로 취급
            context_paths.append(sys.argv[i])
            i += 1

    context_paths = context_paths if context_paths else None

    if command == "plan":
        result = parallel_review_plan(plan_path, context_paths, claude_model, output_json)
    elif command == "code":
        result = parallel_review_code(plan_path, project_dir, context_paths, claude_model, output_json)
    else:
        print(f"Unknown command: {command}")
        print(__doc__)
        sys.exit(1)

    print(result)


if __name__ == "__main__":
    main()
