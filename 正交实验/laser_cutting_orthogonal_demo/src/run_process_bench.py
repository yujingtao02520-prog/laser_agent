from __future__ import annotations

import argparse

from process_bench import list_benches, run_process_bench


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a laser cutting process experiment bench.")
    parser.add_argument("--bench-id", default="cs30_air_l9")
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--list", action="store_true", help="List available benches and exit.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.list:
        for bench_id, bench in list_benches().items():
            print(f"{bench_id}: {bench['name']}")
        return

    summary = run_process_bench(args.bench_id, args.seed)
    best = summary["best_episode"]
    agent = summary["agent_recommendation"]
    print(f"Bench completed: {summary['bench_id']}")
    print(
        "Best episode: "
        f"{best['episode_id']} score={best['quality_score']} "
        f"failure_case={best['failure_case']}"
    )
    print(
        "Agent recommendation: "
        f"{agent['episode_id']} -> {agent['next_parameters']}"
    )
    print(f"Summary: {summary['artifacts']['bench_summary_md']}")


if __name__ == "__main__":
    main()
