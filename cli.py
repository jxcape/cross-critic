#!/usr/bin/env python3
"""
Cross-Critic CLI

Usage:
    python cli.py --plan plan.md
    python cli.py --plan plan.md --context specs/agent.md src/pipeline.py
    python cli.py --resume
"""

import argparse
import sys
from pathlib import Path

from core import WorkflowEngine, CheckpointManager
from core.workflow import Phase


def main():
    parser = argparse.ArgumentParser(
        description="Cross-Critic: Cross-model critic 워크플로우"
    )

    parser.add_argument(
        "--plan",
        type=str,
        help="계획 파일 경로"
    )
    parser.add_argument(
        "--context",
        type=str,
        nargs="*",
        help="추가 context 파일들"
    )
    parser.add_argument(
        "--phase",
        type=int,
        choices=[0, 1, 2, 3],
        help="시작 Phase (0=Context, 1=Plan, 2=Code, 3=Test)"
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="중단된 세션 재개"
    )
    parser.add_argument(
        "--auto",
        action="store_true",
        help="자동 모드 (체크포인트 스킵) - 주의!"
    )
    parser.add_argument(
        "--project-root",
        type=str,
        default=".",
        help="프로젝트 루트 경로 (기본: 현재 디렉토리)"
    )

    args = parser.parse_args()

    # 프로젝트 루트
    project_root = Path(args.project_root).resolve()

    # 체크포인트 매니저
    checkpoint_manager = CheckpointManager(auto_mode=args.auto)

    # 엔진 생성
    engine = WorkflowEngine(
        project_root=project_root,
        checkpoint_manager=checkpoint_manager,
    )

    try:
        if args.resume:
            # 재개
            state = engine.resume()
        elif args.plan:
            # 새 워크플로우
            start_phase = Phase(args.phase) if args.phase is not None else Phase.CONTEXT
            state = engine.run(
                plan_path=args.plan,
                context_paths=args.context,
                start_phase=start_phase,
            )
        else:
            parser.print_help()
            sys.exit(1)

        # 결과 출력
        print(f"\n{'='*60}")
        print(f"세션 ID: {state.session_id}")
        print(f"최종 Phase: {state.current_phase.name}")
        print(f"체크포인트: {len(state.checkpoints)}개")
        print(f"{'='*60}")

    except FileNotFoundError as e:
        print(f"❌ 파일을 찾을 수 없습니다: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n\n⚠️ 중단됨")
        sys.exit(130)
    except Exception as e:
        print(f"❌ 오류 발생: {e}")
        raise


if __name__ == "__main__":
    main()
