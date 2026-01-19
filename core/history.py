"""
Session History Manager

Cross-Critic 세션 히스토리 저장 및 조회.
"""

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Iterator


@dataclass
class SessionRecord:
    """세션 기록"""
    session_id: str
    timestamp: str  # ISO format
    review_type: str  # "plan" or "code"
    plan_path: str
    rounds: list[dict] = field(default_factory=list)
    final_decision: str | None = None  # "satisfied", "aborted", etc.

    def to_dict(self) -> dict:
        """딕셔너리로 변환"""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "SessionRecord":
        """딕셔너리에서 생성"""
        return cls(
            session_id=data["session_id"],
            timestamp=data["timestamp"],
            review_type=data.get("review_type", "plan"),
            plan_path=data["plan_path"],
            rounds=data.get("rounds", []),
            final_decision=data.get("final_decision"),
        )

    @classmethod
    def create(
        cls,
        plan_path: str,
        review_type: str = "plan",
        rounds: list[dict] | None = None,
        final_decision: str | None = None,
    ) -> "SessionRecord":
        """새 세션 레코드 생성"""
        now = datetime.now()
        # 마이크로초 포함하여 고유성 보장
        session_id = f"{now.strftime('%Y%m%d_%H%M%S_%f')}_{review_type}"
        timestamp = now.isoformat()

        return cls(
            session_id=session_id,
            timestamp=timestamp,
            review_type=review_type,
            plan_path=plan_path,
            rounds=rounds or [],
            final_decision=final_decision,
        )


@dataclass
class IndexEntry:
    """인덱스 엔트리"""
    session_id: str
    timestamp: str
    review_type: str
    plan_path: str
    round_count: int
    final_decision: str | None


class HistoryManager:
    """
    세션 히스토리 관리

    Usage:
        manager = HistoryManager(project_dir)

        # 세션 저장
        record = SessionRecord.create("plan.md", "plan", rounds=[...])
        manager.save(record)

        # 세션 목록 조회
        for entry in manager.list_sessions():
            print(entry.session_id)

        # 특정 세션 조회
        session = manager.get("20260119_143000_plan")
    """

    HISTORY_DIR = ".cross-critic/history"
    INDEX_FILE = "index.json"

    def __init__(self, project_dir: str | Path):
        self.project_dir = Path(project_dir)
        self.history_dir = self.project_dir / self.HISTORY_DIR
        self.index_path = self.history_dir / self.INDEX_FILE

    def save(self, record: SessionRecord) -> Path:
        """
        세션 히스토리 저장

        Args:
            record: 저장할 세션 레코드

        Returns:
            저장된 파일 경로
        """
        self.history_dir.mkdir(parents=True, exist_ok=True)

        # 세션 파일 저장
        filename = f"{record.session_id}.json"
        session_path = self.history_dir / filename
        session_path.write_text(
            json.dumps(record.to_dict(), indent=2, ensure_ascii=False)
        )

        # 인덱스 업데이트
        self._update_index(record)

        return session_path

    def list_sessions(
        self,
        review_type: str | None = None,
        limit: int | None = None,
    ) -> list[IndexEntry]:
        """
        세션 목록 조회

        Args:
            review_type: 필터링할 리뷰 타입 ("plan" or "code")
            limit: 최대 반환 개수

        Returns:
            IndexEntry 목록 (최신순)
        """
        if not self.index_path.exists():
            return []

        try:
            data = json.loads(self.index_path.read_text())
        except (json.JSONDecodeError, FileNotFoundError):
            return []

        entries = []
        for item in data.get("sessions", []):
            if review_type and item.get("review_type") != review_type:
                continue
            entries.append(IndexEntry(
                session_id=item["session_id"],
                timestamp=item["timestamp"],
                review_type=item.get("review_type", "plan"),
                plan_path=item["plan_path"],
                round_count=item.get("round_count", 0),
                final_decision=item.get("final_decision"),
            ))

        # 최신순 정렬
        entries.sort(key=lambda e: e.timestamp, reverse=True)

        if limit:
            entries = entries[:limit]

        return entries

    def get(self, session_id: str) -> SessionRecord | None:
        """
        특정 세션 조회

        Args:
            session_id: 세션 ID

        Returns:
            SessionRecord 또는 None
        """
        session_path = self.history_dir / f"{session_id}.json"
        if not session_path.exists():
            return None

        try:
            data = json.loads(session_path.read_text())
            return SessionRecord.from_dict(data)
        except (json.JSONDecodeError, KeyError):
            return None

    def delete(self, session_id: str) -> bool:
        """
        세션 삭제

        Args:
            session_id: 삭제할 세션 ID

        Returns:
            삭제 성공 여부
        """
        session_path = self.history_dir / f"{session_id}.json"
        if not session_path.exists():
            return False

        session_path.unlink()
        self._remove_from_index(session_id)
        return True

    def search(
        self,
        start_date: str | None = None,
        end_date: str | None = None,
        review_type: str | None = None,
    ) -> list[IndexEntry]:
        """
        세션 검색

        Args:
            start_date: 시작 날짜 (YYYY-MM-DD)
            end_date: 종료 날짜 (YYYY-MM-DD)
            review_type: 리뷰 타입

        Returns:
            필터링된 IndexEntry 목록
        """
        entries = self.list_sessions(review_type=review_type)

        if start_date:
            entries = [e for e in entries if e.timestamp[:10] >= start_date]
        if end_date:
            entries = [e for e in entries if e.timestamp[:10] <= end_date]

        return entries

    def _update_index(self, record: SessionRecord) -> None:
        """인덱스 파일 업데이트"""
        # 기존 인덱스 로드
        if self.index_path.exists():
            try:
                data = json.loads(self.index_path.read_text())
            except json.JSONDecodeError:
                data = {"sessions": []}
        else:
            data = {"sessions": []}

        # 중복 제거 (같은 session_id가 있으면 업데이트)
        sessions = [s for s in data["sessions"] if s["session_id"] != record.session_id]

        # 새 엔트리 추가
        sessions.append({
            "session_id": record.session_id,
            "timestamp": record.timestamp,
            "review_type": record.review_type,
            "plan_path": record.plan_path,
            "round_count": len(record.rounds),
            "final_decision": record.final_decision,
        })

        # 최신순 정렬
        sessions.sort(key=lambda s: s["timestamp"], reverse=True)

        data["sessions"] = sessions
        self.index_path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False)
        )

    def _remove_from_index(self, session_id: str) -> None:
        """인덱스에서 세션 제거"""
        if not self.index_path.exists():
            return

        try:
            data = json.loads(self.index_path.read_text())
        except json.JSONDecodeError:
            return

        data["sessions"] = [
            s for s in data["sessions"] if s["session_id"] != session_id
        ]

        self.index_path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False)
        )
