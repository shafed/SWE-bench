# /// script
# requires-python = ">=3.11"
# ///
#
# Generates and freezes experiment/execution/run-order-v3.tsv for the v3
# sample (experiment/preregistration/v3/tasks-main.txt).
#
# Per experiment/execution/PROTOCOL.md's "Ordering" section: task order and
# within-pair condition order are randomized before any main inference, with
# exactly half the instances SINGLE-first and half MULTI-first. v1's
# run-order.tsv was produced by hand for 12 instances with no tracked
# generator; this script exists so the v3 order is reproducible and its seed
# is recorded, rather than another untracked one-off.
#
# Must be run, and its output committed, before the first v3 inference run.
# Re-running after any v3 inference has started would defeat the freeze --
# refuse in that case rather than silently overwrite.

import argparse
import pathlib
import random
import sys

ROOT = pathlib.Path(__file__).resolve().parents[3]
TASKS_FILE = pathlib.Path(__file__).resolve().parent / "tasks-main.txt"
RUNS_DIR = ROOT / "experiment" / "runs"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", default="v3-run-order")
    ap.add_argument("--out", default=str(
        ROOT / "experiment" / "execution" / "run-order-v3.tsv"))
    args = ap.parse_args()

    tasks = [l.strip() for l in TASKS_FILE.read_text().splitlines() if l.strip()]
    if len(tasks) != 12:
        sys.exit(f"expected 12 tasks in {TASKS_FILE}, found {len(tasks)}")

    out = pathlib.Path(args.out)
    if out.exists():
        sys.exit(f"{out} already exists -- the order is frozen, not regenerated")
    if RUNS_DIR.exists() and any(
        (RUNS_DIR / d / task).exists()
        for d in ("main-v3",) for task in tasks
    ):
        sys.exit("a v3 main run directory already has data; refusing to "
                  "generate a new order after inference has started")

    rng = random.Random(args.seed)

    order = list(tasks)
    rng.shuffle(order)

    labels = ["single-first"] * 6 + ["multi-first"] * 6
    rng.shuffle(labels)

    lines = ["position\tinstance_id\torder"]
    for position, (iid, label) in enumerate(zip(order, labels), 1):
        lines.append(f"{position}\t{iid}\t{label}")

    out.write_text("\n".join(lines) + "\n")
    print(f"# seed = {args.seed!r}")
    print(f"# single-first = {labels.count('single-first')}, "
          f"multi-first = {labels.count('multi-first')}")
    print("\n".join(lines))
    print(f"\n# wrote {out}")


if __name__ == "__main__":
    main()
