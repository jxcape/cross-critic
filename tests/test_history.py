"""
Tests for core/history.py
"""

import json
import tempfile
from pathlib import Path

import pytest

from core.history import HistoryManager, SessionRecord, IndexEntry


class TestSessionRecord:
    """SessionRecord 테스트"""

    def test_create_generates_session_id(self):
        """SessionRecord.create()가 session_id를 생성하는지 확인"""
        record = SessionRecord.create("plan.md", "plan")

        assert record.session_id is not None
        assert "plan" in record.session_id
        assert len(record.session_id) > 10

    def test_create_sets_timestamp(self):
        """SessionRecord.create()가 timestamp를 설정하는지 확인"""
        record = SessionRecord.create("plan.md", "plan")

        assert record.timestamp is not None
        # ISO format 확인
        assert "T" in record.timestamp

    def test_create_with_rounds(self):
        """rounds 파라미터가 제대로 설정되는지 확인"""
        rounds = [
            {"round_number": 1, "gpt_response": "GPT says...", "claude_response": "Claude says..."}
        ]
        record = SessionRecord.create("plan.md", "plan", rounds=rounds)

        assert len(record.rounds) == 1
        assert record.rounds[0]["gpt_response"] == "GPT says..."

    def test_to_dict_serialization(self):
        """to_dict()가 올바른 딕셔너리를 반환하는지 확인"""
        record = SessionRecord.create(
            "plan.md",
            "plan",
            rounds=[{"round_number": 1}],
            final_decision="satisfied",
        )

        data = record.to_dict()

        assert data["session_id"] == record.session_id
        assert data["timestamp"] == record.timestamp
        assert data["review_type"] == "plan"
        assert data["plan_path"] == "plan.md"
        assert data["rounds"] == [{"round_number": 1}]
        assert data["final_decision"] == "satisfied"

    def test_from_dict_deserialization(self):
        """from_dict()가 SessionRecord를 복원하는지 확인"""
        data = {
            "session_id": "20260119_143000_plan",
            "timestamp": "2026-01-19T14:30:00",
            "review_type": "plan",
            "plan_path": "plan.md",
            "rounds": [{"round_number": 1}],
            "final_decision": "aborted",
        }

        record = SessionRecord.from_dict(data)

        assert record.session_id == "20260119_143000_plan"
        assert record.timestamp == "2026-01-19T14:30:00"
        assert record.review_type == "plan"
        assert record.plan_path == "plan.md"
        assert len(record.rounds) == 1
        assert record.final_decision == "aborted"

    def test_roundtrip_serialization(self):
        """to_dict() -> from_dict() 왕복 변환 테스트"""
        original = SessionRecord.create(
            "code.md",
            "code",
            rounds=[{"round_number": 1}, {"round_number": 2}],
            final_decision="satisfied",
        )

        data = original.to_dict()
        restored = SessionRecord.from_dict(data)

        assert restored.session_id == original.session_id
        assert restored.timestamp == original.timestamp
        assert restored.review_type == original.review_type
        assert restored.plan_path == original.plan_path
        assert restored.rounds == original.rounds
        assert restored.final_decision == original.final_decision


class TestHistoryManager:
    """HistoryManager 테스트"""

    @pytest.fixture
    def temp_project(self):
        """임시 프로젝트 디렉토리"""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def manager(self, temp_project):
        """HistoryManager 인스턴스"""
        return HistoryManager(temp_project)

    def test_save_creates_history_dir(self, manager, temp_project):
        """save()가 history 디렉토리를 생성하는지 확인"""
        record = SessionRecord.create("plan.md", "plan")
        manager.save(record)

        history_dir = temp_project / ".cross-critic" / "history"
        assert history_dir.exists()

    def test_save_creates_session_file(self, manager, temp_project):
        """save()가 세션 파일을 생성하는지 확인"""
        record = SessionRecord.create("plan.md", "plan")
        saved_path = manager.save(record)

        assert saved_path.exists()
        assert saved_path.name == f"{record.session_id}.json"

    def test_save_creates_index_file(self, manager, temp_project):
        """save()가 인덱스 파일을 생성/업데이트하는지 확인"""
        record = SessionRecord.create("plan.md", "plan")
        manager.save(record)

        index_path = temp_project / ".cross-critic" / "history" / "index.json"
        assert index_path.exists()

        data = json.loads(index_path.read_text())
        assert "sessions" in data
        assert len(data["sessions"]) == 1
        assert data["sessions"][0]["session_id"] == record.session_id

    def test_list_sessions_empty(self, manager):
        """빈 히스토리에서 list_sessions() 테스트"""
        entries = manager.list_sessions()
        assert entries == []

    def test_list_sessions_returns_entries(self, manager):
        """list_sessions()가 저장된 세션을 반환하는지 확인"""
        # 세션 2개 저장
        record1 = SessionRecord.create("plan1.md", "plan")
        record2 = SessionRecord.create("plan2.md", "code")
        manager.save(record1)
        manager.save(record2)

        entries = manager.list_sessions()

        assert len(entries) == 2
        # 최신순 정렬 확인 (record2가 먼저)
        assert entries[0].session_id == record2.session_id

    def test_list_sessions_filter_by_type(self, manager):
        """review_type 필터링 테스트"""
        record_plan = SessionRecord.create("plan.md", "plan")
        record_code = SessionRecord.create("code.md", "code")
        manager.save(record_plan)
        manager.save(record_code)

        plan_entries = manager.list_sessions(review_type="plan")
        code_entries = manager.list_sessions(review_type="code")

        assert len(plan_entries) == 1
        assert plan_entries[0].review_type == "plan"

        assert len(code_entries) == 1
        assert code_entries[0].review_type == "code"

    def test_list_sessions_with_limit(self, manager):
        """limit 파라미터 테스트"""
        for i in range(5):
            record = SessionRecord.create(f"plan{i}.md", "plan")
            manager.save(record)

        entries = manager.list_sessions(limit=3)
        assert len(entries) == 3

    def test_get_existing_session(self, manager):
        """get()으로 기존 세션 조회 테스트"""
        record = SessionRecord.create(
            "plan.md",
            "plan",
            rounds=[{"round_number": 1, "gpt_response": "test"}],
        )
        manager.save(record)

        retrieved = manager.get(record.session_id)

        assert retrieved is not None
        assert retrieved.session_id == record.session_id
        assert len(retrieved.rounds) == 1

    def test_get_nonexistent_session(self, manager):
        """get()으로 존재하지 않는 세션 조회 테스트"""
        retrieved = manager.get("nonexistent_session_id")
        assert retrieved is None

    def test_delete_existing_session(self, manager):
        """delete()로 기존 세션 삭제 테스트"""
        record = SessionRecord.create("plan.md", "plan")
        manager.save(record)

        result = manager.delete(record.session_id)

        assert result is True
        assert manager.get(record.session_id) is None
        # 인덱스에서도 제거 확인
        entries = manager.list_sessions()
        assert len(entries) == 0

    def test_delete_nonexistent_session(self, manager):
        """delete()로 존재하지 않는 세션 삭제 시도 테스트"""
        result = manager.delete("nonexistent_session_id")
        assert result is False

    def test_search_by_date_range(self, manager):
        """날짜 범위로 검색 테스트"""
        # 세션 저장
        record = SessionRecord.create("plan.md", "plan")
        manager.save(record)

        # 오늘 날짜로 검색
        from datetime import datetime
        today = datetime.now().strftime("%Y-%m-%d")

        entries = manager.search(start_date=today, end_date=today)
        assert len(entries) == 1

        # 미래 날짜로 검색 (결과 없음)
        entries = manager.search(start_date="2099-01-01")
        assert len(entries) == 0

    def test_search_by_type_and_date(self, manager):
        """타입과 날짜 복합 검색 테스트"""
        record_plan = SessionRecord.create("plan.md", "plan")
        record_code = SessionRecord.create("code.md", "code")
        manager.save(record_plan)
        manager.save(record_code)

        from datetime import datetime
        today = datetime.now().strftime("%Y-%m-%d")

        entries = manager.search(start_date=today, review_type="plan")
        assert len(entries) == 1
        assert entries[0].review_type == "plan"

    def test_index_update_on_multiple_saves(self, manager):
        """여러 번 저장 시 인덱스 업데이트 확인"""
        record = SessionRecord.create("plan.md", "plan")
        manager.save(record)

        # 같은 session_id로 다시 저장 (업데이트)
        record.final_decision = "satisfied"
        manager.save(record)

        entries = manager.list_sessions()
        assert len(entries) == 1
        assert entries[0].final_decision == "satisfied"


class TestHistoryIntegration:
    """통합 테스트"""

    @pytest.fixture
    def temp_project(self):
        """임시 프로젝트 디렉토리"""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    def test_full_workflow(self, temp_project):
        """전체 워크플로우 테스트"""
        manager = HistoryManager(temp_project)

        # 1. 세션 생성 및 저장
        record = SessionRecord.create(
            "specs/plan.md",
            "plan",
            rounds=[
                {
                    "round_number": 1,
                    "gpt_response": "GPT says this looks good.",
                    "claude_response": "Claude agrees.",
                },
                {
                    "round_number": 2,
                    "gpt_response": "GPT concurs with Claude.",
                    "claude_response": "Claude has no further comments.",
                },
            ],
        )
        manager.save(record)

        # 2. 목록 조회
        entries = manager.list_sessions()
        assert len(entries) == 1
        assert entries[0].round_count == 2

        # 3. 상세 조회
        retrieved = manager.get(record.session_id)
        assert retrieved is not None
        assert len(retrieved.rounds) == 2
        assert retrieved.rounds[0]["gpt_response"] == "GPT says this looks good."

        # 4. 세션 완료 업데이트
        retrieved.final_decision = "satisfied"
        manager.save(retrieved)

        # 5. 업데이트 확인
        entries = manager.list_sessions()
        assert entries[0].final_decision == "satisfied"

        # 6. 삭제
        manager.delete(record.session_id)
        assert manager.get(record.session_id) is None
        assert manager.list_sessions() == []
