"""
Cross-Critic Viewer

Streamlit 기반 다기능 뷰어:
- Debate: GPT/Claude 토론 결과 비교
- Diff: 코드 리뷰용 diff 시각화
- History: 세션 히스토리 관리

Usage:
    streamlit run viewer/app.py -- --state /path/to/.cross-critic/debate_state.json

    # 또는 환경변수로
    DEBATE_STATE=/path/to/state.json streamlit run viewer/app.py
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import streamlit as st

from viewer.diff import DiffRenderer
from viewer.history import HistoryViewer

# 페이지 설정
st.set_page_config(
    page_title="Cross-Critic",
    page_icon="🎭",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# CSS 스타일
st.markdown("""
<style>
    .stApp {
        max-width: 1400px;
        margin: 0 auto;
    }
    .model-header {
        font-size: 1.2em;
        font-weight: bold;
        padding: 10px;
        border-radius: 5px;
        margin-bottom: 10px;
    }
    .gpt-header {
        background-color: #10a37f20;
        border-left: 4px solid #10a37f;
    }
    .claude-header {
        background-color: #d4a57420;
        border-left: 4px solid #d4a574;
    }
    .step-section {
        background-color: #f8f9fa;
        padding: 15px;
        border-radius: 8px;
        margin-bottom: 10px;
    }
    .error-box {
        background-color: #ffebee;
        border-left: 4px solid #f44336;
        padding: 15px;
        border-radius: 5px;
    }
    .common-section {
        background-color: #e8f5e9;
        padding: 15px;
        border-radius: 8px;
        margin: 20px 0;
    }
    .diff-section {
        background-color: #fff3e0;
        padding: 15px;
        border-radius: 8px;
        margin: 20px 0;
    }
</style>
""", unsafe_allow_html=True)


def get_state_path() -> Path | None:
    """상태 파일 경로 가져오기"""
    # 1. 환경변수
    env_path = os.environ.get("DEBATE_STATE")
    if env_path:
        return Path(env_path)

    # 2. 커맨드라인 인자
    if "--state" in sys.argv:
        idx = sys.argv.index("--state")
        if idx + 1 < len(sys.argv):
            return Path(sys.argv[idx + 1])

    # 3. 현재 디렉토리에서 찾기
    cwd = Path.cwd()
    default_path = cwd / ".cross-critic" / "debate_state.json"
    if default_path.exists():
        return default_path

    # 4. specs/ 디렉토리 체크 (cross-critic 프로젝트 내부)
    specs_path = cwd / "specs" / ".cross-critic" / "debate_state.json"
    if specs_path.exists():
        return specs_path

    return None


def load_state(state_path: Path) -> dict | None:
    """상태 파일 로드"""
    if not state_path.exists():
        return None

    try:
        return json.loads(state_path.read_text())
    except json.JSONDecodeError:
        return None


def parse_steps(content: str) -> dict[str, str]:
    """응답에서 Step 1-4 파싱"""
    steps = {}
    current_step = None
    current_content = []

    for line in content.split("\n"):
        # Step 헤더 감지
        if "Step 1" in line or "Fatal Flaw" in line:
            if current_step:
                steps[current_step] = "\n".join(current_content).strip()
            current_step = "fatal_flaw"
            current_content = []
        elif "Step 2" in line or "Missing" in line:
            if current_step:
                steps[current_step] = "\n".join(current_content).strip()
            current_step = "missing"
            current_content = []
        elif "Step 3" in line or "Edge Case" in line:
            if current_step:
                steps[current_step] = "\n".join(current_content).strip()
            current_step = "edge_cases"
            current_content = []
        elif "Step 4" in line or "Improvement" in line or "Actionable" in line:
            if current_step:
                steps[current_step] = "\n".join(current_content).strip()
            current_step = "improvements"
            current_content = []
        elif current_step:
            current_content.append(line)

    # 마지막 섹션
    if current_step:
        steps[current_step] = "\n".join(current_content).strip()

    return steps


def render_round(round_data: dict, round_num: int):
    """라운드 결과 렌더링"""
    st.header(f"Round {round_num}")

    gpt_response = round_data.get("gpt_response")
    claude_response = round_data.get("claude_response")
    gpt_error = round_data.get("gpt_error")
    claude_error = round_data.get("claude_error")

    # Side-by-side 컬럼
    col1, col2 = st.columns(2)

    with col1:
        st.markdown('<div class="model-header gpt-header">🤖 GPT (Codex)</div>', unsafe_allow_html=True)

        if gpt_error:
            st.markdown(f'<div class="error-box">❌ Error: {gpt_error}</div>', unsafe_allow_html=True)
        elif gpt_response:
            gpt_steps = parse_steps(gpt_response)
            render_steps(gpt_steps, gpt_response)
        else:
            st.info("응답 없음")

    with col2:
        st.markdown('<div class="model-header claude-header">🧠 Claude</div>', unsafe_allow_html=True)

        if claude_error:
            st.markdown(f'<div class="error-box">❌ Error: {claude_error}</div>', unsafe_allow_html=True)
        elif claude_response:
            claude_steps = parse_steps(claude_response)
            render_steps(claude_steps, claude_response)
        else:
            st.info("응답 없음")

    # 공통점/차이점 분석 (둘 다 응답 있을 때만)
    if gpt_response and claude_response:
        render_comparison(gpt_response, claude_response)


def render_steps(steps: dict, full_response: str):
    """Step별 렌더링"""
    step_labels = {
        "fatal_flaw": ("🚨 치명적 결함", "Step 1"),
        "missing": ("📋 누락된 요구사항", "Step 2"),
        "edge_cases": ("⚠️ 엣지 케이스", "Step 3"),
        "improvements": ("💡 개선 제안", "Step 4"),
    }

    if not steps:
        # 파싱 실패 시 전체 표시
        with st.expander("전체 응답", expanded=True):
            st.markdown(full_response)
        return

    for key, (label, step_num) in step_labels.items():
        content = steps.get(key, "")

        # 없음 체크
        is_empty = not content or content.strip().lower() in ["없음", "none", "-"]

        with st.expander(f"{label}", expanded=not is_empty):
            if is_empty:
                st.success("✅ 없음")
            else:
                st.markdown(content)


def render_comparison(gpt_response: str, claude_response: str):
    """공통점/차이점 분석"""
    st.divider()
    st.subheader("📊 비교 분석")

    # 간단한 키워드 기반 분석
    gpt_lower = gpt_response.lower()
    claude_lower = claude_response.lower()

    # 공통 키워드
    common_keywords = []
    diff_keywords = []

    check_keywords = [
        ("에러 처리", "error"),
        ("파일 읽기", "file"),
        ("JSON", "json"),
        ("상태", "state"),
        ("동시", "concurr"),
        ("context", "context"),
        ("timeout", "timeout"),
        ("race condition", "race"),
    ]

    for kr, en in check_keywords:
        in_gpt = kr in gpt_lower or en in gpt_lower
        in_claude = kr in claude_lower or en in claude_lower

        if in_gpt and in_claude:
            common_keywords.append(kr)
        elif in_gpt or in_claude:
            diff_keywords.append((kr, "GPT" if in_gpt else "Claude"))

    col1, col2 = st.columns(2)

    with col1:
        st.markdown('<div class="common-section">', unsafe_allow_html=True)
        st.markdown("**🤝 공통 언급**")
        if common_keywords:
            for kw in common_keywords:
                st.markdown(f"- {kw}")
        else:
            st.markdown("_분석된 공통점 없음_")
        st.markdown('</div>', unsafe_allow_html=True)

    with col2:
        st.markdown('<div class="diff-section">', unsafe_allow_html=True)
        st.markdown("**🔀 차이점**")
        if diff_keywords:
            for kw, model in diff_keywords:
                st.markdown(f"- {kw} ({model}만 언급)")
        else:
            st.markdown("_분석된 차이점 없음_")
        st.markdown('</div>', unsafe_allow_html=True)


def render_actions(state: dict, state_path: Path):
    """다음 액션 버튼"""
    st.divider()
    st.subheader("🎯 다음 액션")

    rounds = state.get("rounds", [])
    round_count = len(rounds)
    max_rounds = 5

    # 진행 상태
    progress = round_count / max_rounds
    st.progress(progress, text=f"Round {round_count}/{max_rounds}")

    col1, col2, col3, col4 = st.columns(4)

    plan_path = state_path.parent.parent  # .cross-critic의 부모

    with col1:
        st.markdown("**토론 계속**")
        st.code(f"debate.py continue {plan_path}", language="bash")

    with col2:
        st.markdown("**주제 집중**")
        st.code(f"debate.py continue {plan_path} --focus '주제'", language="bash")

    with col3:
        st.markdown("**상태 확인**")
        st.code(f"debate.py status {plan_path}", language="bash")

    with col4:
        st.markdown("**토론 리셋**")
        st.code(f"debate.py reset {plan_path}", language="bash")

    # 자동 새로고침 (파일 변경 감지용)
    if st.button("🔄 새로고침"):
        st.rerun()


def render_debate_tab():
    """Debate 탭 렌더링"""
    # 상태 파일 찾기
    state_path = get_state_path()

    if not state_path:
        st.warning("토론 상태 파일을 찾을 수 없습니다.")
        st.markdown("""
        **사용법:**
        ```bash
        # 환경변수로 지정
        DEBATE_STATE=/path/to/.cross-critic/debate_state.json streamlit run viewer/app.py

        # 또는 인자로 지정
        streamlit run viewer/app.py -- --state /path/to/debate_state.json
        ```
        """)

        # 수동 입력
        manual_path = st.text_input("상태 파일 경로 직접 입력:")
        if manual_path:
            state_path = Path(manual_path)
            if not state_path.exists():
                st.error(f"파일이 존재하지 않습니다: {manual_path}")
                return
        else:
            return

    # 상태 로드
    state = load_state(state_path)

    if not state:
        st.error(f"상태 파일을 읽을 수 없습니다: {state_path}")
        return

    # 파일 경로 표시
    st.caption(f"📁 {state_path}")

    rounds = state.get("rounds", [])

    if not rounds:
        st.info("아직 토론이 시작되지 않았습니다.")
        return

    # 라운드 탭
    if len(rounds) == 1:
        render_round(rounds[0], 1)
    else:
        round_tabs = st.tabs([f"Round {i+1}" for i in range(len(rounds))])
        for i, tab in enumerate(round_tabs):
            with tab:
                render_round(rounds[i], i + 1)

    # 액션 버튼
    render_actions(state, state_path)


def get_project_dir() -> Path:
    """프로젝트 디렉토리 가져오기"""
    env_dir = os.environ.get("PROJECT_DIR")
    if env_dir:
        return Path(env_dir)

    state_path = get_state_path()
    if state_path:
        # .cross-critic/debate_state.json -> 프로젝트 루트
        return state_path.parent.parent

    return Path.cwd()


def render_diff_tab():
    """Diff 탭 렌더링"""
    st.subheader("Code Diff Viewer")

    project_dir = get_project_dir()
    st.caption(f"📁 Project: {project_dir}")

    # Diff 소스 선택
    diff_source = st.radio(
        "Diff Source",
        options=["Git (staged)", "Git (unstaged)", "Custom"],
        horizontal=True,
    )

    diff_text = ""

    if diff_source == "Git (staged)":
        try:
            result = subprocess.run(
                ["git", "diff", "--cached"],
                capture_output=True,
                text=True,
                cwd=project_dir,
            )
            diff_text = result.stdout
        except Exception as e:
            st.error(f"Git diff failed: {e}")

    elif diff_source == "Git (unstaged)":
        try:
            result = subprocess.run(
                ["git", "diff"],
                capture_output=True,
                text=True,
                cwd=project_dir,
            )
            diff_text = result.stdout
        except Exception as e:
            st.error(f"Git diff failed: {e}")

    elif diff_source == "Custom":
        diff_text = st.text_area(
            "Paste unified diff here:",
            height=200,
            placeholder="diff --git a/file.py b/file.py\n...",
        )

    # Diff 렌더링
    if diff_text:
        renderer = DiffRenderer()
        renderer.render_diff(diff_text)
    else:
        st.info("No changes to display.")


def render_history_tab():
    """History 탭 렌더링"""
    project_dir = get_project_dir()
    st.caption(f"📁 Project: {project_dir}")

    viewer = HistoryViewer(project_dir)
    viewer.render()


def main():
    st.title("🎭 Cross-Critic")

    # 메인 탭
    tab_debate, tab_diff, tab_history = st.tabs(["Debate", "Diff", "History"])

    with tab_debate:
        render_debate_tab()

    with tab_diff:
        render_diff_tab()

    with tab_history:
        render_history_tab()


if __name__ == "__main__":
    main()
