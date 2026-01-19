#!/usr/bin/env python
"""
GPT 리뷰 헬퍼 스크립트

Skill에서 호출하기 쉽게 분리한 GPT(Codex) 리뷰 함수들.
글로벌 사용을 위해 절대 경로 지원.

Usage:
    # 계획 리뷰 (절대 경로 권장)
    python scripts/gpt_review.py plan /path/to/plan.md /path/to/context1.md

    # 코드 리뷰 (git diff 기반, --project-dir로 프로젝트 위치 지정)
    python scripts/gpt_review.py code /path/to/plan.md --project-dir /path/to/project

    # 테스트 작성
    python scripts/gpt_review.py test /path/to/plan.md --project-dir /path/to/project
"""

import sys
import subprocess
from pathlib import Path

# 프로젝트 루트 추가
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.models import CodexClient
from core.context import ContextCollector


def review_plan(plan_path: str, context_paths: list[str] | None = None) -> str:
    """
    계획 리뷰 (Phase 1)

    계층적 프롬프트로 구조화된 피드백 유도.
    """
    client = CodexClient()

    plan_content = Path(plan_path).read_text()

    context_str = ""
    if context_paths:
        # 절대 경로면 그대로, 상대 경로면 plan 파일 기준
        plan_dir = Path(plan_path).parent
        collector = ContextCollector(plan_dir)
        context_result = collector.collect(plan_content, context_paths)
        context_str = context_result.to_prompt_context()

    prompt = f"""## 계획
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

    response = client.call(prompt, context_str if context_str else None)
    return response.content


def review_code(plan_path: str, project_dir: str | None = None, context_paths: list[str] | None = None) -> str:
    """
    코드 리뷰 (Phase 2)

    계층적 프롬프트 + Context 전달 지원.
    """
    client = CodexClient()

    plan_content = Path(plan_path).read_text()

    # 프로젝트 디렉토리 결정 (계획 파일 위치 또는 명시적 지정)
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

    # Git diff 수집 (프로젝트 디렉토리에서)
    result = subprocess.run(
        ["git", "diff", "--cached"],
        capture_output=True,
        text=True,
        cwd=cwd
    )
    diff = result.stdout

    if not diff:
        result = subprocess.run(
            ["git", "diff"],
            capture_output=True,
            text=True,
            cwd=cwd
        )
        diff = result.stdout

    if not diff:
        return "변경사항이 없습니다."

    prompt = f"""## Context
{context_str if context_str else "(Context 없음)"}

## 원래 계획
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

    response = client.call(prompt, context_str if context_str else None)
    return response.content


def write_tests(plan_path: str, project_dir: str | None = None, context_paths: list[str] | None = None) -> str:
    """
    테스트 작성 (Phase 3)

    Context 전달 지원.
    """
    client = CodexClient()

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

    # Git diff 수집 (프로젝트 디렉토리에서)
    result = subprocess.run(
        ["git", "diff", "HEAD"],
        capture_output=True,
        text=True,
        cwd=cwd
    )
    diff = result.stdout

    prompt = f"""## Context
{context_str if context_str else "(Context 없음)"}

## 계획
{plan_content}

## 구현된 코드
{diff if diff else "(변경사항 없음)"}

## 테스트 작성 요청

아래 구조로 pytest 테스트를 작성해줘:

### 1. 정상 케이스 (Happy Path)
기본 동작이 예상대로 작동하는지 검증

### 2. Edge Cases
- 빈 입력
- 경계값 (최소/최대)
- 특수 문자 / 유니코드

### 3. 에러 케이스
- 잘못된 타입 입력
- 권한 오류 시나리오
- 타임아웃 / 연결 실패

### 4. 요구사항 검증
계획에 명시된 각 요구사항을 테스트로 커버

**출력 형식**: pytest 테스트 파일 내용만 출력 (설명 없이 코드만)"""

    response = client.call(prompt, context_str if context_str else None)
    return response.content


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)

    command = sys.argv[1]
    plan_path = sys.argv[2]

    # 인자 파싱: --project-dir, --context
    project_dir = None
    context_paths = []
    i = 3
    while i < len(sys.argv):
        if sys.argv[i] == "--project-dir" and i + 1 < len(sys.argv):
            project_dir = sys.argv[i + 1]
            i += 2
        elif sys.argv[i] == "--context" and i + 1 < len(sys.argv):
            # --context 뒤의 모든 파일을 context로 수집
            i += 1
            while i < len(sys.argv) and not sys.argv[i].startswith("--"):
                context_paths.append(sys.argv[i])
                i += 1
        else:
            # 플래그 없는 인자는 context 파일로 취급 (하위호환)
            context_paths.append(sys.argv[i])
            i += 1

    context_paths = context_paths if context_paths else None

    if command == "plan":
        result = review_plan(plan_path, context_paths)
    elif command == "code":
        result = review_code(plan_path, project_dir, context_paths)
    elif command == "test":
        result = write_tests(plan_path, project_dir, context_paths)
    else:
        print(f"Unknown command: {command}")
        print(__doc__)
        sys.exit(1)

    print(result)


if __name__ == "__main__":
    main()
