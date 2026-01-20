"""
Diff Viewer for Code Review

코드 리뷰용 Diff 시각화 컴포넌트.
unified diff를 파싱하고 Streamlit으로 렌더링.
"""

from dataclasses import dataclass, field
from typing import Literal
import re

import streamlit as st
import streamlit.components.v1 as components


@dataclass
class DiffLine:
    """개별 diff 라인"""
    type: Literal["add", "remove", "context"]
    content: str
    old_line: int | None = None
    new_line: int | None = None


@dataclass
class DiffHunk:
    """diff hunk (변경 블록)"""
    file_path: str
    old_start: int
    new_start: int
    lines: list[DiffLine] = field(default_factory=list)


def parse_unified_diff(diff_text: str) -> list[DiffHunk]:
    """
    unified diff 텍스트를 파싱하여 DiffHunk 리스트 반환.

    Args:
        diff_text: git diff 출력 등의 unified diff 형식 텍스트

    Returns:
        파싱된 DiffHunk 리스트
    """
    if not diff_text or not diff_text.strip():
        return []

    hunks: list[DiffHunk] = []
    current_file: str | None = None
    current_hunk: DiffHunk | None = None
    old_line = 0
    new_line = 0

    # diff 헤더 패턴
    file_pattern = re.compile(r'^diff --git a/(.*) b/(.*)$')
    hunk_pattern = re.compile(r'^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@')

    for line in diff_text.split('\n'):
        # 파일 헤더 감지
        file_match = file_pattern.match(line)
        if file_match:
            current_file = file_match.group(2)  # b/ 경로 사용
            continue

        # --- a/path 또는 +++ b/path (파일 경로 백업)
        if line.startswith('--- a/'):
            if not current_file:
                current_file = line[6:]  # "--- a/" 제거
            continue
        if line.startswith('+++ b/'):
            if not current_file:
                current_file = line[6:]  # "+++ b/" 제거
            continue

        # hunk 헤더 감지
        hunk_match = hunk_pattern.match(line)
        if hunk_match:
            old_start = int(hunk_match.group(1))
            new_start = int(hunk_match.group(2))

            current_hunk = DiffHunk(
                file_path=current_file or "unknown",
                old_start=old_start,
                new_start=new_start,
                lines=[]
            )
            hunks.append(current_hunk)
            old_line = old_start
            new_line = new_start
            continue

        # hunk 내부 라인 처리
        if current_hunk is not None:
            if line.startswith('+') and not line.startswith('+++'):
                # 추가 라인
                current_hunk.lines.append(DiffLine(
                    type="add",
                    content=line[1:],  # + 제거
                    old_line=None,
                    new_line=new_line
                ))
                new_line += 1
            elif line.startswith('-') and not line.startswith('---'):
                # 삭제 라인
                current_hunk.lines.append(DiffLine(
                    type="remove",
                    content=line[1:],  # - 제거
                    old_line=old_line,
                    new_line=None
                ))
                old_line += 1
            elif line.startswith(' ') or (line == '' and current_hunk.lines):
                # context 라인 (변경 없음)
                content = line[1:] if line.startswith(' ') else ''
                current_hunk.lines.append(DiffLine(
                    type="context",
                    content=content,
                    old_line=old_line,
                    new_line=new_line
                ))
                old_line += 1
                new_line += 1

    return hunks


class DiffRenderer:
    """Streamlit용 Diff 렌더러"""

    # 색상 정의
    ADD_BG = "#e6ffec"      # 연한 초록
    REMOVE_BG = "#ffebe9"   # 연한 빨강
    ADD_BORDER = "#2da44e"  # 초록
    REMOVE_BORDER = "#cf222e"  # 빨강

    def __init__(self):
        self._inject_styles()

    def _inject_styles(self):
        """CSS 스타일 주입"""
        st.markdown("""
        <style>
            .diff-container {
                font-family: 'SF Mono', 'Monaco', 'Menlo', monospace;
                font-size: 13px;
                line-height: 1.5;
                border: 1px solid #d0d7de;
                border-radius: 6px;
                overflow: hidden;
                margin: 10px 0;
            }
            .diff-file-header {
                background-color: #f6f8fa;
                padding: 8px 12px;
                border-bottom: 1px solid #d0d7de;
                font-weight: 600;
            }
            .diff-line {
                display: flex;
                padding: 0;
                border-bottom: 1px solid #eee;
            }
            .diff-line:last-child {
                border-bottom: none;
            }
            .diff-line-num {
                width: 50px;
                padding: 0 8px;
                text-align: right;
                color: #57606a;
                background-color: #f6f8fa;
                border-right: 1px solid #d0d7de;
                user-select: none;
                flex-shrink: 0;
            }
            .diff-line-content {
                flex: 1;
                padding: 0 8px;
                white-space: pre-wrap;
                word-break: break-all;
            }
            .diff-line-prefix {
                width: 20px;
                padding: 0 4px;
                text-align: center;
                font-weight: bold;
                flex-shrink: 0;
                border-right: 1px solid #d0d7de;
            }
            .diff-add {
                background-color: #e6ffec;
            }
            .diff-add .diff-line-num {
                background-color: #ccffd8;
            }
            .diff-add .diff-line-prefix {
                color: #1a7f37;
                background-color: #ccffd8;
            }
            .diff-remove {
                background-color: #ffebe9;
            }
            .diff-remove .diff-line-num {
                background-color: #ffd7d5;
            }
            .diff-remove .diff-line-prefix {
                color: #cf222e;
                background-color: #ffd7d5;
            }
            .diff-context {
                background-color: white;
            }
            .diff-context .diff-line-prefix {
                color: #57606a;
            }
            .diff-stats {
                display: inline-flex;
                gap: 8px;
                font-size: 12px;
                margin-left: 8px;
            }
            .diff-stats-add {
                color: #1a7f37;
            }
            .diff-stats-remove {
                color: #cf222e;
            }
        </style>
        """, unsafe_allow_html=True)

    def render_diff(self, diff_text: str) -> None:
        """
        diff 텍스트를 Streamlit으로 렌더링.

        Args:
            diff_text: unified diff 형식 텍스트
        """
        hunks = parse_unified_diff(diff_text)

        if not hunks:
            st.info("변경사항이 없습니다.")
            return

        # 파일별로 그룹화
        files: dict[str, list[DiffHunk]] = {}
        for hunk in hunks:
            if hunk.file_path not in files:
                files[hunk.file_path] = []
            files[hunk.file_path].append(hunk)

        # 파일별 렌더링
        for file_path, file_hunks in files.items():
            self._render_file(file_path, file_hunks)

    def _render_file(self, file_path: str, hunks: list[DiffHunk]) -> None:
        """단일 파일의 diff 렌더링"""
        # 통계 계산
        adds = sum(1 for h in hunks for l in h.lines if l.type == "add")
        removes = sum(1 for h in hunks for l in h.lines if l.type == "remove")

        # 파일 헤더
        st.markdown(f"**📄 {file_path}** <span style='color:#1a7f37'>+{adds}</span> <span style='color:#cf222e'>-{removes}</span>", unsafe_allow_html=True)

        # Diff HTML 생성
        html_lines = []
        for hunk in hunks:
            for line in hunk.lines:
                old_num = str(line.old_line) if line.old_line else ""
                new_num = str(line.new_line) if line.new_line else ""

                # 타입별 스타일 (inline)
                if line.type == "add":
                    prefix = "+"
                    bg_color = "#e6ffec"
                    prefix_color = "#1a7f37"
                    num_bg = "#ccffd8"
                elif line.type == "remove":
                    prefix = "-"
                    bg_color = "#ffebe9"
                    prefix_color = "#cf222e"
                    num_bg = "#ffd7d5"
                else:
                    prefix = " "
                    bg_color = "#ffffff"
                    prefix_color = "#57606a"
                    num_bg = "#f6f8fa"

                # HTML 이스케이프
                content = self._escape_html(line.content)

                html_lines.append(f'''<div style="display:flex; border-bottom:1px solid #eee; background-color:{bg_color}; font-family:'SF Mono',Monaco,monospace; font-size:13px; line-height:1.5;">
<div style="min-width:45px; padding:0 8px; text-align:right; color:#57606a; background-color:{num_bg}; border-right:1px solid #d0d7de;">{old_num}</div>
<div style="min-width:45px; padding:0 8px; text-align:right; color:#57606a; background-color:{num_bg}; border-right:1px solid #d0d7de;">{new_num}</div>
<div style="min-width:20px; padding:0 4px; text-align:center; font-weight:bold; color:{prefix_color}; background-color:{num_bg}; border-right:1px solid #d0d7de;">{prefix}</div>
<div style="flex:1; padding:0 8px; white-space:pre;">{content}</div>
</div>''')

        # 전체 HTML (iframe으로 렌더링)
        full_html = f'''
        <div style="border:1px solid #d0d7de; border-radius:6px; overflow:hidden; margin:10px 0;">
            {''.join(html_lines)}
        </div>
        '''

        # 높이 계산 (라인 수 * 줄높이)
        height = max(100, len(html_lines) * 22 + 20)
        components.html(full_html, height=height, scrolling=True)

    def _escape_html(self, text: str) -> str:
        """HTML 특수문자 이스케이프"""
        return (text
                .replace('&', '&amp;')
                .replace('<', '&lt;')
                .replace('>', '&gt;')
                .replace('"', '&quot;')
                .replace("'", '&#39;'))
