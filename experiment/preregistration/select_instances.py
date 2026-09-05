# /// script
# requires-python = ">=3.11"
# dependencies = ["datasets>=2.19"]
# ///

import argparse
import hashlib
import json
import posixpath
import random
import re
from collections import Counter

from datasets import load_dataset


DATASET = "SWE-bench/SWE-bench_Verified"
SPLIT = "test"

EXCLUDE_INSTANCES = {"sympy__sympy-20590"}
EXCLUDE_REPOS = set()

PER_CELL = 2
RESERVE_PER_CELL = 2
MAX_PER_REPO = 2
MAX_SEED = 10000

DISPERSION_LEVELS = ("L", "M", "D")
DIFFICULTY_LEVELS = ("lo", "hi")
CELL_ORDER = [
    (dispersion, difficulty)
    for dispersion in DISPERSION_LEVELS
    for difficulty in DIFFICULTY_LEVELS
]

EASY_LABEL = "<15 min fix"
MEDIUM_LABEL = "15 min - 1 hour"
LONG_LABELS = {"1-4 hours", ">4 hours"}

TEST_PATH = re.compile(
    r"(^|/)(tests?|testing)(/|$)"
    r"|(^|/)test_[^/]*\.py$"
    r"|_test\.py$"
    r"|(^|/)conftest\.py$"
)

DIFF_FILE = re.compile(r"^diff --git a/(\S+) b/\S+", re.M)
HUNK = re.compile(r"^@@ ", re.M)
ADDED = re.compile(r"^\+(?!\+\+\+)", re.M)
DELETED = re.compile(r"^-(?!---)", re.M)


def patched_files(patch):
    return sorted(set(DIFF_FILE.findall(patch or "")))


def features(inst):
    patch = inst["patch"] or ""
    files = patched_files(patch)

    prod = [
        f for f in files
        if f.endswith(".py") and not TEST_PATH.search(f)
    ]

    dirs = sorted({posixpath.dirname(f) for f in prod})

    return {
        "instance_id": inst["instance_id"],
        "repo": inst["repo"],
        "difficulty": inst["difficulty"],
        "n_prod_files": len(prod),
        "n_dirs": len(dirs),
        "n_hunks": len(HUNK.findall(patch)),
        "patch_lines": (
            len(ADDED.findall(patch))
            + len(DELETED.findall(patch))
        ),
        "problem_len": len(inst["problem_statement"] or ""),
        "prod_files": prod,
        "dirs": dirs,
    }


def dispersion(row):
    if row["n_dirs"] >= 2:
        return "D"
    if row["n_prod_files"] >= 2:
        return "M"
    return "L"


def primary_difficulty(label):
    if label in LONG_LABELS:
        return "hi"
    return "lo"


def fallback_difficulty(label):
    return "lo" if label == EASY_LABEL else "hi"


def cell_sizes(rows, fn):
    counts = Counter(
        (dispersion(row), fn(row["difficulty"]))
        for row in rows
    )
    return {
        cell: counts.get(cell, 0)
        for cell in CELL_ORDER
    }


def choose_split(rows):
    primary = cell_sizes(rows, primary_difficulty)
    fallback = cell_sizes(rows, fallback_difficulty)

    if min(primary.values()) >= PER_CELL:
        full_reserves = (
            min(primary.values())
            >= PER_CELL + RESERVE_PER_CELL
        )
        step = "step1" if full_reserves else "step2"
        return (
            "primary",
            primary_difficulty,
            primary,
            fallback,
            step,
        )

    if min(fallback.values()) >= PER_CELL:
        full_reserves = (
            min(fallback.values())
            >= PER_CELL + RESERVE_PER_CELL
        )
        step = "step1-fallback" if full_reserves else "step2-fallback"
        return (
            "fallback",
            fallback_difficulty,
            primary,
            fallback,
            step,
        )

    raise SystemExit(
        "step3 exhausted: no preregistered difficulty split "
        "has >=2 candidates in every cell"
    )


def draw(pools, seed):
    rng = random.Random(seed)
    result = {}

    for cell in CELL_ORDER:
        pool = pools[cell]

        if len(pool) < PER_CELL:
            return None

        k = min(PER_CELL + RESERVE_PER_CELL, len(pool))
        result[cell] = rng.sample(pool, k)

    return result


def repo_feasible(selection, feat_by_id):
    main = [
        iid
        for cell in CELL_ORDER
        for iid in selection[cell][:PER_CELL]
    ]

    counts = Counter(
        feat_by_id[iid]["repo"]
        for iid in main
    )

    return all(count <= MAX_PER_REPO for count in counts.values())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--audit", action="store_true")
    args = parser.parse_args()

    script_sha = hashlib.sha256(
        open(__file__, "rb").read()
    ).hexdigest()

    ds = load_dataset(DATASET, split=SPLIT)

    if "difficulty" not in ds.column_names:
        raise SystemExit("Dataset has no difficulty column")

    rows = []
    dropped_no_prod = 0

    for inst in ds:
        if inst["instance_id"] in EXCLUDE_INSTANCES:
            continue

        if inst["repo"] in EXCLUDE_REPOS:
            continue

        row = features(inst)

        if row["n_prod_files"] == 0:
            dropped_no_prod += 1
            continue

        rows.append(row)

    (
        split_name,
        split_fn,
        primary_sizes,
        fallback_sizes,
        ladder_step,
    ) = choose_split(rows)

    print(f"# script_sha256 = {script_sha}")
    print(f"# dataset = {DATASET}")
    print(f"# total dataset rows = {len(ds)}")
    print(f"# eligible rows = {len(rows)}")
    print(f"# dropped without production .py = {dropped_no_prod}")

    print(
        "# raw difficulty counts =",
        dict(Counter(row["difficulty"] for row in rows)),
    )

    def show_sizes(name, sizes):
        text = ", ".join(
            f"{d}/{f}={sizes[(d, f)]}"
            for d, f in CELL_ORDER
        )
        print(f"# sizes split={name}: {text}")

    show_sizes("primary", primary_sizes)
    show_sizes("fallback", fallback_sizes)

    print(f"# ladder step = {ladder_step}")
    print(f"# active split = {split_name}")

    if args.audit:
        return

    feat_by_id = {
        row["instance_id"]: row
        for row in rows
    }

    pools = {cell: [] for cell in CELL_ORDER}

    for row in rows:
        cell = (
            dispersion(row),
            split_fn(row["difficulty"]),
        )
        pools[cell].append(row["instance_id"])

    for cell in CELL_ORDER:
        pools[cell].sort()

    chosen = None
    used_seed = None

    for seed in range(MAX_SEED):
        candidate = draw(pools, seed)

        if candidate is None:
            continue

        if repo_feasible(candidate, feat_by_id):
            chosen = candidate
            used_seed = seed
            break

    if chosen is None:
        raise SystemExit(
            f"No feasible seed below {MAX_SEED}"
        )

    print(f"# selected seed = {used_seed}")
    print()

    records = []

    for cell in CELL_ORDER:
        for rank, iid in enumerate(chosen[cell]):
            record = dict(feat_by_id[iid])
            record["cell"] = f"{cell[0]}/{cell[1]}"
            record["role"] = (
                "main"
                if rank < PER_CELL
                else f"reserve{rank - PER_CELL + 1}"
            )
            records.append(record)

    fields = [
        "instance_id",
        "repo",
        "difficulty",
        "n_prod_files",
        "n_dirs",
        "n_hunks",
        "patch_lines",
        "cell",
        "role",
    ]

    print("\t".join(fields))

    for record in records:
        print(
            "\t".join(str(record[field]) for field in fields)
        )

    output = {
        "dataset": DATASET,
        "script_sha256": script_sha,
        "active_split": split_name,
        "ladder_step": ladder_step,
        "seed": used_seed,
        "config": {
            "exclude_instances": sorted(EXCLUDE_INSTANCES),
            "exclude_repos": sorted(EXCLUDE_REPOS),
            "per_cell": PER_CELL,
            "reserve_per_cell": RESERVE_PER_CELL,
            "max_per_repo": MAX_PER_REPO,
        },
        "records": records,
    }

    with open(
        "experiment/preregistration/selection.json",
        "w",
    ) as f:
        json.dump(output, f, indent=2)

    print(
        "\n# wrote "
        "experiment/preregistration/selection.json"
    )


if __name__ == "__main__":
    main()
