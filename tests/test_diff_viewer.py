"""
DiffRenderer 테스트

viewer/diff.py의 parse_unified_diff 및 DiffRenderer 테스트.
"""

import pytest
from viewer.diff import DiffLine, DiffHunk, parse_unified_diff, DiffRenderer


# --- 테스트 데이터 ---

SINGLE_FILE_DIFF = """diff --git a/core/debate.py b/core/debate.py
index abc1234..def5678 100644
--- a/core/debate.py
+++ b/core/debate.py
@@ -10,6 +10,8 @@ class DebateRound:
     round_number: int
     gpt_response: str | None
     claude_response: str | None
+    consensus_score: float | None = None
+    divergence_detected: bool = False
     gpt_error: str | None = None
     claude_error: str | None = None
"""

MULTI_FILE_DIFF = """diff --git a/core/models.py b/core/models.py
index 111111..222222 100644
--- a/core/models.py
+++ b/core/models.py
@@ -1,5 +1,6 @@
 from dataclasses import dataclass
 from typing import Literal
+import asyncio

 @dataclass
 class Model:
diff --git a/core/workflow.py b/core/workflow.py
index 333333..444444 100644
--- a/core/workflow.py
+++ b/core/workflow.py
@@ -20,7 +20,6 @@ class Workflow:
     def run(self):
-        print("Starting workflow")
         self.execute()
         self.cleanup()
"""

EMPTY_DIFF = ""

WHITESPACE_DIFF = """
"""


# --- 테스트 케이스 ---

def test_parse_unified_diff_single_file():
    """단일 파일 diff 파싱"""
    hunks = parse_unified_diff(SINGLE_FILE_DIFF)

    assert len(hunks) == 1

    hunk = hunks[0]
    assert hunk.file_path == "core/debate.py"
    assert hunk.old_start == 10
    assert hunk.new_start == 10

    # 라인 수 확인 (context 3 + add 2 + context 2 + trailing empty = 8)
    assert len(hunk.lines) == 8

    # 추가 라인 확인
    add_lines = [l for l in hunk.lines if l.type == "add"]
    assert len(add_lines) == 2
    assert "consensus_score" in add_lines[0].content
    assert "divergence_detected" in add_lines[1].content


def test_parse_unified_diff_multiple_files():
    """여러 파일 diff 파싱"""
    hunks = parse_unified_diff(MULTI_FILE_DIFF)

    assert len(hunks) == 2

    # 첫 번째 파일
    assert hunks[0].file_path == "core/models.py"
    assert hunks[0].old_start == 1
    assert hunks[0].new_start == 1

    # 두 번째 파일
    assert hunks[1].file_path == "core/workflow.py"
    assert hunks[1].old_start == 20
    assert hunks[1].new_start == 20


def test_diff_line_types():
    """add/remove/context 라인 타입 구분"""
    hunks = parse_unified_diff(MULTI_FILE_DIFF)

    # 첫 번째 hunk: add 1개 (import asyncio)
    models_hunk = hunks[0]
    add_lines = [l for l in models_hunk.lines if l.type == "add"]
    assert len(add_lines) == 1
    assert "asyncio" in add_lines[0].content

    # 두 번째 hunk: remove 1개 (print 문)
    workflow_hunk = hunks[1]
    remove_lines = [l for l in workflow_hunk.lines if l.type == "remove"]
    assert len(remove_lines) == 1
    assert "print" in remove_lines[0].content

    # context 라인 확인
    context_lines = [l for l in workflow_hunk.lines if l.type == "context"]
    assert len(context_lines) >= 2


def test_empty_diff():
    """빈 diff 처리"""
    hunks = parse_unified_diff(EMPTY_DIFF)
    assert hunks == []

    hunks = parse_unified_diff(WHITESPACE_DIFF)
    assert hunks == []


def test_diff_line_numbers():
    """라인 번호 추적 확인"""
    hunks = parse_unified_diff(SINGLE_FILE_DIFF)
    hunk = hunks[0]

    # context 라인은 old_line과 new_line 모두 있음
    context_lines = [l for l in hunk.lines if l.type == "context"]
    for line in context_lines:
        assert line.old_line is not None
        assert line.new_line is not None

    # add 라인은 new_line만 있음
    add_lines = [l for l in hunk.lines if l.type == "add"]
    for line in add_lines:
        assert line.old_line is None
        assert line.new_line is not None

    # remove 라인은 old_line만 있음 (MULTI_FILE_DIFF에서 확인)
    multi_hunks = parse_unified_diff(MULTI_FILE_DIFF)
    workflow_hunk = multi_hunks[1]
    remove_lines = [l for l in workflow_hunk.lines if l.type == "remove"]
    for line in remove_lines:
        assert line.old_line is not None
        assert line.new_line is None


def test_diff_hunk_dataclass():
    """DiffHunk 데이터클래스 기본 동작"""
    hunk = DiffHunk(
        file_path="test.py",
        old_start=1,
        new_start=1,
        lines=[]
    )
    assert hunk.file_path == "test.py"
    assert hunk.old_start == 1
    assert hunk.new_start == 1
    assert hunk.lines == []


def test_diff_line_dataclass():
    """DiffLine 데이터클래스 기본 동작"""
    line = DiffLine(
        type="add",
        content="new line",
        old_line=None,
        new_line=5
    )
    assert line.type == "add"
    assert line.content == "new line"
    assert line.old_line is None
    assert line.new_line == 5


def test_html_escape():
    """HTML 특수문자 이스케이프"""
    renderer = DiffRenderer.__new__(DiffRenderer)  # __init__ 호출 안함 (Streamlit 의존성 회피)

    # 테스트
    assert renderer._escape_html("<script>") == "&lt;script&gt;"
    assert renderer._escape_html('a="b"') == 'a=&quot;b&quot;'
    assert renderer._escape_html("x & y") == "x &amp; y"
    assert renderer._escape_html("it's") == "it&#39;s"


def test_parse_hunk_header_variants():
    """다양한 hunk 헤더 형식 파싱"""
    # 단일 라인 변경
    diff_single = """diff --git a/test.py b/test.py
--- a/test.py
+++ b/test.py
@@ -5 +5 @@ def foo():
-    old_line
+    new_line
"""
    hunks = parse_unified_diff(diff_single)
    assert len(hunks) == 1
    assert hunks[0].old_start == 5
    assert hunks[0].new_start == 5


def test_multiple_hunks_same_file():
    """같은 파일에 여러 hunk"""
    diff_multi_hunk = """diff --git a/test.py b/test.py
--- a/test.py
+++ b/test.py
@@ -1,3 +1,4 @@
 line1
+added_at_top
 line2
 line3
@@ -10,3 +11,4 @@
 line10
+added_at_bottom
 line11
 line12
"""
    hunks = parse_unified_diff(diff_multi_hunk)
    assert len(hunks) == 2
    assert hunks[0].file_path == "test.py"
    assert hunks[1].file_path == "test.py"
    assert hunks[0].old_start == 1
    assert hunks[1].old_start == 10
