"""
History Viewer Component

Streamlit 컴포넌트로 세션 히스토리 표시.
"""

import sys
from datetime import datetime
from pathlib import Path

import streamlit as st

# 프로젝트 루트를 path에 추가
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.history import HistoryManager, SessionRecord, IndexEntry


class HistoryViewer:
    """
    세션 히스토리 뷰어 (Streamlit 컴포넌트)

    Usage:
        viewer = HistoryViewer(project_dir)
        viewer.render()  # Streamlit 페이지에 렌더링
    """

    def __init__(self, project_dir: str | Path):
        self.project_dir = Path(project_dir)
        self.manager = HistoryManager(project_dir)

    def render(self) -> None:
        """메인 뷰 렌더링"""
        st.header("Session History")

        # 필터 사이드바
        col1, col2, col3 = st.columns([2, 2, 1])

        with col1:
            review_type_filter = st.selectbox(
                "Review Type",
                options=["All", "plan", "code"],
                index=0,
            )

        with col2:
            date_range = st.date_input(
                "Date Range",
                value=[],
                max_value=datetime.now().date(),
            )

        with col3:
            limit = st.number_input("Max Results", min_value=5, max_value=100, value=20)

        # 필터 적용
        filter_type = None if review_type_filter == "All" else review_type_filter

        start_date = None
        end_date = None
        if date_range:
            if len(date_range) == 1:
                start_date = date_range[0].isoformat()
                end_date = date_range[0].isoformat()
            elif len(date_range) == 2:
                start_date = date_range[0].isoformat()
                end_date = date_range[1].isoformat()

        # 세션 목록 가져오기
        if start_date or end_date:
            entries = self.manager.search(
                start_date=start_date,
                end_date=end_date,
                review_type=filter_type,
            )
        else:
            entries = self.manager.list_sessions(review_type=filter_type, limit=limit)

        # 세션 목록 렌더링
        self._render_session_list(entries)

    def _render_session_list(self, entries: list[IndexEntry]) -> None:
        """세션 목록 렌더링"""
        if not entries:
            st.info("No sessions found.")
            return

        st.markdown(f"**{len(entries)} sessions found**")

        for entry in entries:
            self._render_session_card(entry)

    def _render_session_card(self, entry: IndexEntry) -> None:
        """개별 세션 카드 렌더링"""
        # 타임스탬프 포맷팅
        try:
            dt = datetime.fromisoformat(entry.timestamp)
            formatted_time = dt.strftime("%Y-%m-%d %H:%M")
        except ValueError:
            formatted_time = entry.timestamp[:16]

        # 리뷰 타입 아이콘
        type_icon = "plan" if entry.review_type == "plan" else "code"

        # 상태 배지
        status_badge = ""
        if entry.final_decision:
            if entry.final_decision == "satisfied":
                status_badge = " :green[Satisfied]"
            elif entry.final_decision == "aborted":
                status_badge = " :red[Aborted]"
            else:
                status_badge = f" :gray[{entry.final_decision}]"

        # 카드 컨테이너
        with st.expander(
            f"**{formatted_time}** | `{type_icon}` | {entry.round_count} rounds{status_badge}",
            expanded=False,
        ):
            self._render_session_detail(entry)

    def _render_session_detail(self, entry: IndexEntry) -> None:
        """세션 상세 정보 렌더링"""
        col1, col2 = st.columns(2)

        with col1:
            st.markdown(f"**Session ID:** `{entry.session_id}`")
            st.markdown(f"**Plan Path:** `{entry.plan_path}`")

        with col2:
            st.markdown(f"**Review Type:** `{entry.review_type}`")
            st.markdown(f"**Rounds:** {entry.round_count}")

        # 상세 보기 버튼
        if st.button("View Details", key=f"view_{entry.session_id}"):
            session = self.manager.get(entry.session_id)
            if session:
                self._render_full_session(session)
            else:
                st.error("Failed to load session details.")

    def _render_full_session(self, session: SessionRecord) -> None:
        """전체 세션 상세 렌더링"""
        st.divider()
        st.subheader(f"Session: {session.session_id}")

        # 메타데이터
        st.markdown(f"**Timestamp:** {session.timestamp}")
        st.markdown(f"**Plan:** `{session.plan_path}`")
        st.markdown(f"**Type:** `{session.review_type}`")

        if session.final_decision:
            st.markdown(f"**Final Decision:** `{session.final_decision}`")

        # 라운드별 결과
        st.divider()
        st.markdown("### Rounds")

        for i, round_data in enumerate(session.rounds):
            with st.expander(f"Round {i + 1}", expanded=(i == len(session.rounds) - 1)):
                self._render_round(round_data)

    def _render_round(self, round_data: dict) -> None:
        """라운드 결과 렌더링"""
        col1, col2 = st.columns(2)

        with col1:
            st.markdown("**GPT Response:**")
            gpt_response = round_data.get("gpt_response")
            gpt_error = round_data.get("gpt_error")

            if gpt_error:
                st.error(f"Error: {gpt_error}")
            elif gpt_response:
                st.markdown(gpt_response)
            else:
                st.info("No response")

        with col2:
            st.markdown("**Claude Response:**")
            claude_response = round_data.get("claude_response")
            claude_error = round_data.get("claude_error")

            if claude_error:
                st.error(f"Error: {claude_error}")
            elif claude_response:
                st.markdown(claude_response)
            else:
                st.info("No response")

    def render_sidebar(self) -> str | None:
        """사이드바에 세션 목록 렌더링 (선택용)

        Returns:
            선택된 session_id 또는 None
        """
        st.sidebar.header("History")

        entries = self.manager.list_sessions(limit=10)

        if not entries:
            st.sidebar.info("No history yet.")
            return None

        selected = None

        for entry in entries:
            try:
                dt = datetime.fromisoformat(entry.timestamp)
                label = dt.strftime("%m-%d %H:%M")
            except ValueError:
                label = entry.session_id[:10]

            type_label = "P" if entry.review_type == "plan" else "C"

            if st.sidebar.button(
                f"{label} [{type_label}]",
                key=f"sidebar_{entry.session_id}",
                use_container_width=True,
            ):
                selected = entry.session_id

        return selected


def render_history_page(project_dir: str | Path) -> None:
    """독립 히스토리 페이지 렌더링"""
    st.set_page_config(
        page_title="Cross-Critic History",
        page_icon="history",
        layout="wide",
    )

    st.title("Cross-Critic Session History")

    viewer = HistoryViewer(project_dir)
    viewer.render()


# 독립 실행 시
if __name__ == "__main__":
    import os

    # 프로젝트 디렉토리 결정
    project_dir = os.environ.get("PROJECT_DIR", Path.cwd())
    render_history_page(project_dir)
