#!/usr/bin/env python
"""
토론 CLI

Usage:
    # Round 1 시작
    python scripts/debate.py start plan.md

    # 다음 라운드 진행 (토론 계속)
    python scripts/debate.py continue plan.md

    # 특정 주제에 집중해서 토론
    python scripts/debate.py continue plan.md --focus "에러 처리 방식"

    # 토론 상태 보기
    python scripts/debate.py status plan.md

    # 토론 리셋
    python scripts/debate.py reset plan.md

    # Context 파일 추가
    python scripts/debate.py start plan.md --context specs/agent.md src/core.py

    # Claude 모델 선택
    python scripts/debate.py start plan.md --claude-model haiku

    # 뷰어 실행 (Streamlit 대시보드)
    python scripts/debate.py serve plan.md

    # 뷰어 포트 지정
    python scripts/debate.py serve plan.md --port 8502
"""

import sys
import json
import subprocess
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.debate import DebateEngine, DebateResult, DebateRound


STATE_DIR = ".cross-critic"
STATE_FILE = "debate_state.json"


def get_state_path(plan_path: str) -> Path:
    """계획 파일 기준 상태 파일 경로"""
    plan_dir = Path(plan_path).parent
    if plan_dir == Path("."):
        plan_dir = Path.cwd()
    return plan_dir / STATE_DIR / STATE_FILE


def load_state(plan_path: str) -> DebateResult | None:
    """토론 상태 로드"""
    state_path = get_state_path(plan_path)
    if not state_path.exists():
        return None

    data = json.loads(state_path.read_text())
    rounds = []
    for r in data.get("rounds", []):
        rounds.append(DebateRound(
            round_number=r["round_number"],
            gpt_response=r.get("gpt_response"),
            claude_response=r.get("claude_response"),
            gpt_error=r.get("gpt_error"),
            claude_error=r.get("claude_error"),
        ))
    return DebateResult(rounds=rounds)


def save_state(plan_path: str, result: DebateResult) -> None:
    """토론 상태 저장"""
    state_path = get_state_path(plan_path)
    state_path.parent.mkdir(parents=True, exist_ok=True)

    data = {
        "rounds": [
            {
                "round_number": r.round_number,
                "gpt_response": r.gpt_response,
                "claude_response": r.claude_response,
                "gpt_error": r.gpt_error,
                "claude_error": r.claude_error,
            }
            for r in result.rounds
        ]
    }
    state_path.write_text(json.dumps(data, indent=2, ensure_ascii=False))


def cmd_start(
    plan_path: str,
    context_paths: list[str] | None = None,
    claude_model: str = "sonnet",
    review_type: str = "plan",
) -> None:
    """Round 1 시작"""
    plan_file = Path(plan_path)
    if not plan_file.exists():
        print(f"Error: 파일을 찾을 수 없습니다: {plan_path}")
        sys.exit(1)

    plan_content = plan_file.read_text()

    # Context 수집
    context = None
    if context_paths:
        parts = []
        for cp in context_paths:
            cp_path = Path(cp)
            if not cp_path.exists():
                print(f"Warning: Context 파일을 찾을 수 없습니다: {cp}")
                continue
            parts.append(f"## {cp}\n{cp_path.read_text()}")
        if parts:
            context = "\n\n".join(parts)

    print(f"[Debate] Round 1 시작...")
    print(f"  Plan: {plan_path}")
    print(f"  Claude model: {claude_model}")
    if context_paths:
        print(f"  Context: {', '.join(context_paths)}")
    print()

    engine = DebateEngine(claude_model=claude_model)
    result = engine.start(plan_content, context, review_type=review_type)

    save_state(plan_path, result)
    print_round(result.latest_round)
    print(f"\n[Round 1 완료] 다음 명령어로 토론을 계속하세요:")
    print(f"  uv run python scripts/debate.py continue {plan_path}")


def cmd_continue(
    plan_path: str,
    focus: str | None = None,
    context_paths: list[str] | None = None,
    claude_model: str = "sonnet",
) -> None:
    """다음 라운드 진행"""
    existing = load_state(plan_path)
    if not existing:
        print("토론이 시작되지 않았습니다. 'debate.py start'를 먼저 실행하세요.")
        sys.exit(1)

    if existing.round_count >= DebateEngine.MAX_ROUNDS:
        print(f"최대 라운드({DebateEngine.MAX_ROUNDS})에 도달했습니다.")
        sys.exit(1)

    plan_content = Path(plan_path).read_text()

    # Context 수집
    context = None
    if context_paths:
        parts = []
        for cp in context_paths:
            cp_path = Path(cp)
            if not cp_path.exists():
                print(f"Warning: Context 파일을 찾을 수 없습니다: {cp}")
                continue
            parts.append(f"## {cp}\n{cp_path.read_text()}")
        if parts:
            context = "\n\n".join(parts)

    next_round = existing.round_count + 1
    print(f"[Debate] Round {next_round} 시작...")
    if focus:
        print(f"  Focus: {focus}")
    print()

    engine = DebateEngine(claude_model=claude_model)
    result = engine.continue_debate(existing, plan_content, context, user_focus=focus)

    save_state(plan_path, result)
    print_round(result.latest_round)

    if result.round_count < DebateEngine.MAX_ROUNDS:
        print(f"\n[Round {result.round_count} 완료] 다음 명령어로 토론을 계속하세요:")
        print(f"  uv run python scripts/debate.py continue {plan_path}")
    else:
        print(f"\n[최대 라운드 도달] 토론이 종료되었습니다.")


def cmd_status(plan_path: str) -> None:
    """토론 상태 보기"""
    existing = load_state(plan_path)
    if not existing:
        print("진행 중인 토론이 없습니다.")
        return

    print(f"총 {existing.round_count}라운드 진행됨 (최대 {DebateEngine.MAX_ROUNDS})")
    print("\n" + existing.format_history())


def cmd_reset(plan_path: str) -> None:
    """토론 리셋"""
    state_path = get_state_path(plan_path)
    if state_path.exists():
        state_path.unlink()
        print("토론 상태가 초기화되었습니다.")
    else:
        print("초기화할 토론이 없습니다.")


def cmd_serve(plan_path: str, port: int = 8501, background: bool = True) -> subprocess.Popen | None:
    """뷰어 실행 (Streamlit 대시보드)"""
    state_path = get_state_path(plan_path)

    if not state_path.exists():
        print("토론 상태가 없습니다. 먼저 'debate.py start'를 실행하세요.")
        sys.exit(1)

    # viewer/app.py 경로
    project_root = Path(__file__).parent.parent
    viewer_path = project_root / "viewer" / "app.py"

    if not viewer_path.exists():
        print(f"뷰어를 찾을 수 없습니다: {viewer_path}")
        sys.exit(1)

    # 환경 변수로 상태 파일 경로 전달
    env = os.environ.copy()
    env["DEBATE_STATE"] = str(state_path.absolute())

    cmd = [
        sys.executable, "-m", "streamlit", "run",
        str(viewer_path),
        "--server.port", str(port),
        "--server.headless", "true",
        "--browser.gatherUsageStats", "false",
    ]

    print(f"[Debate Viewer] 시작 중...")
    print(f"  State: {state_path}")
    print(f"  Port: {port}")
    print()

    if background:
        # 백그라운드 실행
        process = subprocess.Popen(
            cmd,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        # 잠시 대기 후 링크 출력
        import time
        time.sleep(2)

        url = f"http://localhost:{port}"
        print(f"🎭 Debate Viewer 실행 중!")
        print(f"")
        print(f"   👉 {url}")
        print(f"")
        print(f"   종료: Ctrl+C 또는 프로세스 종료 (PID: {process.pid})")
        print()

        return process
    else:
        # 포그라운드 실행
        try:
            subprocess.run(cmd, env=env, check=True)
        except KeyboardInterrupt:
            print("\n뷰어가 종료되었습니다.")
        return None


def print_round(r: DebateRound) -> None:
    """라운드 결과 출력"""
    print(f"\n{'='*60}")
    print(f"Round {r.round_number}")
    print('='*60)

    print("\n## GPT (Codex)")
    print("-"*40)
    if r.gpt_response:
        print(r.gpt_response)
    else:
        print(f"*Error: {r.gpt_error}*")

    print("\n## Claude")
    print("-"*40)
    if r.claude_response:
        print(r.claude_response)
    else:
        print(f"*Error: {r.claude_error}*")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    command = sys.argv[1]

    # help 명령어
    if command in ["-h", "--help", "help"]:
        print(__doc__)
        sys.exit(0)

    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)

    plan_path = sys.argv[2]

    # 옵션 파싱
    focus = None
    context_paths = []
    claude_model = "sonnet"
    review_type = "plan"
    port = 8501
    serve_foreground = False

    i = 3
    while i < len(sys.argv):
        if sys.argv[i] == "--focus" and i + 1 < len(sys.argv):
            focus = sys.argv[i + 1]
            i += 2
        elif sys.argv[i] == "--claude-model" and i + 1 < len(sys.argv):
            claude_model = sys.argv[i + 1]
            i += 2
        elif sys.argv[i] == "--type" and i + 1 < len(sys.argv):
            review_type = sys.argv[i + 1]
            i += 2
        elif sys.argv[i] == "--port" and i + 1 < len(sys.argv):
            port = int(sys.argv[i + 1])
            i += 2
        elif sys.argv[i] == "--foreground":
            serve_foreground = True
            i += 1
        elif sys.argv[i] == "--context":
            i += 1
            while i < len(sys.argv) and not sys.argv[i].startswith("--"):
                context_paths.append(sys.argv[i])
                i += 1
        elif not sys.argv[i].startswith("--"):
            context_paths.append(sys.argv[i])
            i += 1
        else:
            print(f"Unknown option: {sys.argv[i]}")
            sys.exit(1)

    if command == "start":
        cmd_start(plan_path, context_paths or None, claude_model, review_type)
    elif command == "continue":
        cmd_continue(plan_path, focus, context_paths or None, claude_model)
    elif command == "status":
        cmd_status(plan_path)
    elif command == "reset":
        cmd_reset(plan_path)
    elif command == "serve":
        cmd_serve(plan_path, port, background=not serve_foreground)
    else:
        print(f"Unknown command: {command}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
