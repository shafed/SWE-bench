# /// script
# requires-python = ">=3.11"
# dependencies = ["datasets>=2.19"]
# ///
#
# v3 candidate pool for the SINGLE vs MULTI subagent study.
#
# v1/v2 selected instances by *structural* proxies computed from the gold
# patch (files touched, directories spanned, identifier overlap) and treated
# "dispersion" as a stand-in for "decomposable". The main v1 run showed that
# proxy does not hold: a multi-file fix with one central cause gives an agent
# nothing independent to delegate, so MULTI collapsed into "solve it, then
# hand the test run to a subagent".
#
# v3 therefore does NOT try to decide orchestration suitability mechanically.
# This script only builds a CANDIDATE POOL: it applies technical exclusions
# (section 7 of the selection plan) and draws a stratified random sample over
# repository x rough difficulty (section 8). Orchestration suitability is
# assigned afterwards, by blind two-pass annotation against a fixed rubric
# (RUBRIC.md), and the final 12 are chosen by mechanical matching (match.py).
#
# Determinism: the draw is a single deterministic ordering per difficulty
# bucket. Pool size N takes the first N entries of a fixed interleaving of
# those orderings, so "add another block of 10 by the same method" is
# literally `--size 50` -- no re-draw, and the first 40 are unchanged.

import argparse
import hashlib
import json
import pathlib
import posixpath
import random
import re
import sys

from datasets import load_dataset

DATASET = "SWE-bench/SWE-bench_Verified"
SPLIT = "test"

# ---------------------------------------------------------------- exclusions

# Used to debug the experimental pipeline; never an experimental subject.
DEV_INSTANCES = {"sympy__sympy-20590"}

# The v1 main sample. SINGLE and MULTI outcomes for these instances are
# already known to the experimenters, so keeping them in the v3 pool would let
# observed results leak into the selection of the v3 sample. Excluded as
# outcome-contaminated, not as bad tasks.
V1_RUN_INSTANCES = {
    "sympy__sympy-15017",
    "sphinx-doc__sphinx-7757",
    "django__django-13449",
    "pytest-dev__pytest-5787",
    "pydata__xarray-6938",
    "django__django-16938",
    "pydata__xarray-6992",
    "pylint-dev__pylint-4551",
    "sphinx-doc__sphinx-8551",
    "matplotlib__matplotlib-25775",
    "pylint-dev__pylint-8898",
    "scikit-learn__scikit-learn-25102",
}

# Technical size guards (plan section 7). Deliberately loose: they remove
# degenerate tasks, they do NOT rank tasks by decomposability.
# Triviality guard. A small patch is not by itself trivial: many Verified
# tasks are a two-line fix that takes an hour to locate, and those are exactly
# the local-but-hard tasks the single-friendly arm needs. So size alone only
# removes degenerate diffs; "trivial" additionally requires the annotated
# difficulty to be the easiest bucket.
MIN_PROD_CODE_LINES = 2        # below this the diff is degenerate
EASY_MIN_PROD_CODE_LINES = 5   # easy-bucket tasks below this are trivial
MAX_PROD_CODE_LINES = 250  # above this: outside the harness time budget
MAX_PROD_FILES = 10
MECHANICAL_MIN_FILES = 6   # >= this many production files ...
MECHANICAL_MAX_PER_FILE = 3.0  # ... with this few code lines each = a sweep

ROUGH_DIFFICULTY = {
    "<15 min fix": "easy",
    "15 min - 1 hour": "medium",
    "1-4 hours": "hard",
    ">4 hours": "hard",
}

# Bucket shares of the pool, as an 8-slot repeating pattern:
# easy:medium:hard = 2:3:3, so a 40-task pool is 10 / 15 / 15 and every
# further block of 10 keeps the same proportions.
BUCKET_CYCLE = ("medium", "hard", "easy", "medium", "hard", "medium", "hard", "easy")

FILE_HEADER = re.compile(r"^diff --git a/(\S+) b/\S+", re.M)
HUNK = re.compile(r"^@@ ", re.M)
TEST_PATH = re.compile(
    r"(^|/)(tests?|testing)(/|$)"
    r"|(^|/)test_[^/]*\.py$"
    r"|_test\.py$"
    r"|(^|/)conftest\.py$"
)
GENERATED_PATH = re.compile(r"(^|/)(_?vendor|third_party|node_modules|\.tox)(/|$)")


def split_patch(patch):
    heads = list(FILE_HEADER.finditer(patch or ""))
    blocks = {}
    for i, m in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(patch)
        blocks[m.group(1)] = patch[m.end():end]
    return blocks


def code_lines(block):
    """Changed lines that are neither blank nor a whole-line comment.

    Docstring bodies are not detected; this is a triviality guard, not a
    semantic measure.
    """
    n = 0
    for line in block.splitlines():
        if not line or line[0] not in "+-":
            continue
        if line.startswith("+++") or line.startswith("---"):
            continue
        body = line[1:].strip()
        if not body or body.startswith("#"):
            continue
        n += 1
    return n


def features(inst):
    patch = inst.get("patch") or ""
    blocks = split_patch(patch)
    prod = {
        f: b
        for f, b in blocks.items()
        if f.endswith(".py") and not TEST_PATH.search(f) and not GENERATED_PATH.search(f)
    }
    other = sorted(set(blocks) - set(prod))
    prod_lines = sum(code_lines(b) for b in prod.values())
    f2p = inst.get("FAIL_TO_PASS") or []
    if isinstance(f2p, str):
        try:
            f2p = json.loads(f2p)
        except ValueError:
            f2p = []
    return {
        "instance_id": inst["instance_id"],
        "repo": inst["repo"],
        "base_commit": inst["base_commit"],
        "difficulty": inst["difficulty"],
        "rough_difficulty": ROUGH_DIFFICULTY[inst["difficulty"]],
        "n_prod_files": len(prod),
        "prod_files": sorted(prod),
        "non_prod_files": other,
        "prod_code_lines": prod_lines,
        "n_dirs": len({posixpath.dirname(f) for f in prod}),
        "n_hunks": len(HUNK.findall(patch)),
        "problem_len": len(inst.get("problem_statement") or ""),
        "n_fail_to_pass": len(f2p),
    }


def exclusion_reason(row):
    """Return None if the instance is eligible, else a short reason string."""
    iid = row["instance_id"]
    if iid in DEV_INSTANCES:
        return "dev-instance"
    if iid in V1_RUN_INSTANCES:
        return "v1-outcome-known"
    if row["n_prod_files"] == 0:
        return "no-production-python"
    if row["prod_code_lines"] < MIN_PROD_CODE_LINES:
        return "degenerate-diff"
    if (
        row["rough_difficulty"] == "easy"
        and row["prod_code_lines"] < EASY_MIN_PROD_CODE_LINES
    ):
        return "trivial"
    if row["prod_code_lines"] > MAX_PROD_CODE_LINES:
        return "oversized"
    if row["n_prod_files"] > MAX_PROD_FILES:
        return "oversized"
    if (
        row["n_prod_files"] >= MECHANICAL_MIN_FILES
        and row["prod_code_lines"] / row["n_prod_files"] <= MECHANICAL_MAX_PER_FILE
    ):
        return "mechanical-sweep"
    return None


def bucket_order(rows, bucket, seed):
    """Deterministic repo-balanced ordering of one difficulty bucket.

    Repositories are visited round-robin in a shuffled order, each taking the
    next instance from its own shuffled queue. This stratifies by
    repository x rough difficulty without letting django (46% of Verified)
    dominate the pool.
    """
    rng = random.Random(f"{seed}:{bucket}")
    by_repo = {}
    for row in rows:
        if row["rough_difficulty"] == bucket:
            by_repo.setdefault(row["repo"], []).append(row["instance_id"])

    repos = sorted(by_repo)
    rng.shuffle(repos)
    for repo in repos:
        by_repo[repo].sort()
        rng.shuffle(by_repo[repo])

    order, cursor = [], {repo: 0 for repo in repos}
    while len(order) < sum(len(v) for v in by_repo.values()):
        for repo in repos:
            i = cursor[repo]
            if i < len(by_repo[repo]):
                order.append(by_repo[repo][i])
                cursor[repo] = i + 1
    return order


def draw(rows, seed, size):
    orders = {b: bucket_order(rows, b, seed) for b in ("easy", "medium", "hard")}
    cursor = {b: 0 for b in orders}
    picked, slot = [], 0
    while len(picked) < size:
        exhausted = all(cursor[b] >= len(orders[b]) for b in orders)
        if exhausted:
            break
        bucket = BUCKET_CYCLE[slot % len(BUCKET_CYCLE)]
        slot += 1
        i = cursor[bucket]
        if i >= len(orders[bucket]):
            continue  # bucket drained; the cycle keeps drawing from the rest
        picked.append(orders[bucket][i])
        cursor[bucket] = i + 1
    return picked


def dataset_revision():
    ref = (
        pathlib.Path.home()
        / ".cache/huggingface/hub"
        / f"datasets--{DATASET.replace('/', '--')}"
        / "refs/main"
    )
    return ref.read_text().strip() if ref.exists() else "unknown"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", default="v3", help="draw seed (string)")
    ap.add_argument("--size", type=int, default=40,
                    help="pool size; enlarge in blocks of 10 to extend the "
                         "pool without redrawing the earlier candidates")
    ap.add_argument("--audit", action="store_true",
                    help="print eligibility counts only, draw nothing")
    ap.add_argument("--extend-bucket", choices=("easy", "medium", "hard"),
                    help="AMENDMENT 1: after the base draw, append every "
                         "remaining eligible instance of this difficulty "
                         "bucket, in the same seeded order the base draw "
                         "used. Exhausts a stratum instead of sampling it. "
                         "Used when a category cannot be filled and the base "
                         "block showed the category concentrated in one "
                         "bucket -- it changes which instances are annotated, "
                         "never the rubric or the classification rules.")
    ap.add_argument("--out", default="experiment/preregistration/v3/candidates.json")
    args = ap.parse_args()

    script_sha = hashlib.sha256(open(__file__, "rb").read()).hexdigest()
    ds = load_dataset(DATASET, split=SPLIT)

    rows, excluded = [], {}
    for inst in ds:
        row = features(inst)
        reason = exclusion_reason(row)
        if reason:
            excluded[row["instance_id"]] = reason
        else:
            rows.append(row)

    by_id = {row["instance_id"]: row for row in rows}

    print(f"# script_sha256   = {script_sha}")
    print(f"# dataset         = {DATASET} ({SPLIT})")
    print(f"# dataset_revision= {dataset_revision()}")
    print(f"# rows total      = {len(ds)}")
    print(f"# eligible        = {len(rows)}")
    from collections import Counter
    for reason, n in sorted(Counter(excluded.values()).items()):
        print(f"# excluded {reason:20} = {n}")

    grid = Counter((r["repo"], r["rough_difficulty"]) for r in rows)
    repos = sorted({r["repo"] for r in rows})
    print(f"#\n# eligible grid  {'repo':28} easy medium hard")
    for repo in repos:
        print(f"#               {repo:28} "
              f"{grid[(repo,'easy')]:4} {grid[(repo,'medium')]:6} {grid[(repo,'hard')]:4}")

    if args.audit:
        return

    picked = draw(rows, args.seed, args.size)
    if len(picked) < args.size:
        sys.exit(f"pool exhausted: only {len(picked)} eligible instances")

    base_size = len(picked)
    if args.extend_bucket:
        taken = set(picked)
        extra = [i for i in bucket_order(rows, args.extend_bucket, args.seed)
                 if i not in taken]
        picked += extra
        print(f"# amendment 1: exhausting the {args.extend_bucket!r} bucket, "
              f"+{len(extra)} candidates")

    records = []
    for rank, iid in enumerate(picked, 1):
        rec = dict(by_id[iid])
        rec["pool_rank"] = rank
        rec["block"] = (rank - 1) // 10 + 1 if rank <= base_size else "extend"
        records.append(rec)

    print(f"#\n# drawn = {len(records)}  seed = {args.seed!r}")
    print(f"# pool mix: "
          + ", ".join(f"{b}={sum(1 for r in records if r['rough_difficulty']==b)}"
                      for b in ("easy", "medium", "hard")))
    print("# pool repos: "
          + ", ".join(f"{k}={v}" for k, v in
                      sorted(Counter(r["repo"] for r in records).items())))
    print()

    fields = ["pool_rank", "block", "instance_id", "repo", "difficulty",
              "rough_difficulty", "n_prod_files", "prod_code_lines", "n_dirs",
              "n_hunks", "n_fail_to_pass", "problem_len"]
    print("\t".join(fields))
    for rec in records:
        print("\t".join(str(rec[f]) for f in fields))

    out = {
        "dataset": DATASET,
        "split": SPLIT,
        "dataset_revision": dataset_revision(),
        "script_sha256": script_sha,
        "seed": args.seed,
        "size": len(records),
        "base_size": base_size,
        "extend_bucket": args.extend_bucket,
        "config": {
            "dev_instances": sorted(DEV_INSTANCES),
            "v1_run_instances": sorted(V1_RUN_INSTANCES),
            "min_prod_code_lines": MIN_PROD_CODE_LINES,
            "easy_min_prod_code_lines": EASY_MIN_PROD_CODE_LINES,
            "max_prod_code_lines": MAX_PROD_CODE_LINES,
            "max_prod_files": MAX_PROD_FILES,
            "mechanical_min_files": MECHANICAL_MIN_FILES,
            "mechanical_max_per_file": MECHANICAL_MAX_PER_FILE,
            "bucket_cycle": list(BUCKET_CYCLE),
        },
        "eligible_count": len(rows),
        "exclusion_counts": dict(Counter(excluded.values())),
        "candidates": records,
    }
    pathlib.Path(args.out).write_text(json.dumps(out, indent=2) + "\n")
    print(f"\n# wrote {args.out}")


if __name__ == "__main__":
    main()
