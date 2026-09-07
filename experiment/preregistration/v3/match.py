# /// script
# requires-python = ">=3.11"
# ///
#
# Mechanical selection of the final 12 from the classified candidate pool.
#
# 5 orchestration-friendly (>= 3 of them fan-out, <= 2 pipeline)
#   paired 1:1 with 5 single-friendly tasks of matched difficulty/type;
# 2 orchestration-risky, each reported against its nearest friendly reference.
#
# The pairing metric deliberately uses only difficulty, change type,
# investigation volume and patch structure. Orchestration features are
# excluded from it: those are the dimension the pairs are supposed to differ
# on, so matching on them would erase the contrast being measured.
#
# Selection is exact, not greedy: every admissible 5-subset of the friendly
# group is enumerated and each is optimally assigned against the
# single-friendly group, then the cheapest whole configuration wins.

import argparse
import itertools
import json
import math
import pathlib
from collections import Counter

ROOT = pathlib.Path(__file__).resolve().parent

W_DIFFICULTY = 3.0
W_CHANGE_TYPE = 2.0
W_INVESTIGATION = 2.0
W_STRUCT_LINES = 0.5
W_STRUCT_FILES = 0.5
SAME_REPO_BONUS = -1.5
DUP_FANOUT_KIND_PENALTY = 1.0
REPO_OVERFLOW_PENALTY = 1.0
MAX_PER_REPO_SOFT = 3
# Plan section 2 asks for "desirably 3" fan-out tasks and caps the
# implementation -> testing/debug/review pattern at 2. The annotated pool of the
# fully exhausted hard stratum yields 2 fan-out and 3 friendly tasks that are two
# dependent implementation lines -- none of them the reviewer pattern the cap
# targets, so that cap is satisfied at 0. The "desirably 3" is relaxed to 2
# because the stratum that produces fan-out tasks is exhausted, not because the
# rubric was loosened.
MIN_FANOUT = 2
N_PAIRS = 5
N_RISKY = 2


def pair_cost(a, b):
    cost = W_DIFFICULTY * abs(a["difficulty_overall"] - b["difficulty_overall"])
    cost += W_CHANGE_TYPE * (a["change_type"] != b["change_type"])
    cost += W_INVESTIGATION * abs(a["investigation_volume"] - b["investigation_volume"])
    cost += W_STRUCT_LINES * abs(
        math.log2(1 + a["prod_code_lines"]) - math.log2(1 + b["prod_code_lines"])
    )
    cost += W_STRUCT_FILES * min(abs(a["n_prod_files"] - b["n_prod_files"]), 2)
    if a["repo"] == b["repo"]:
        cost += SAME_REPO_BONUS
    return cost


def assign(rows, cols, cost):
    """Exact min-cost assignment of every row to a distinct column.

    Successive shortest augmenting paths with potentials (Jonker-Volgenant
    form). len(rows) <= len(cols) is required.
    """
    n, m = len(rows), len(cols)
    assert n <= m
    INF = float("inf")
    u = [0.0] * (n + 1)
    v = [0.0] * (m + 1)
    p = [0] * (m + 1)   # column -> row (1-indexed, 0 = free)
    way = [0] * (m + 1)

    for i in range(1, n + 1):
        p[0] = i
        j0 = 0
        minv = [INF] * (m + 1)
        used = [False] * (m + 1)
        while True:
            used[j0] = True
            i0, delta, j1 = p[j0], INF, 0
            for j in range(1, m + 1):
                if used[j]:
                    continue
                cur = cost[i0 - 1][j - 1] - u[i0] - v[j]
                if cur < minv[j]:
                    minv[j], way[j] = cur, j0
                if minv[j] < delta:
                    delta, j1 = minv[j], j
            for j in range(m + 1):
                if used[j]:
                    u[p[j]] += delta
                    v[j] -= delta
                else:
                    minv[j] -= delta
            j0 = j1
            if p[j0] == 0:
                break
        while j0:
            j1 = way[j0]
            p[j0] = p[j1]
            j0 = j1

    matching = [None] * n
    for j in range(1, m + 1):
        if p[j]:
            matching[p[j] - 1] = j - 1
    total = sum(cost[i][matching[i]] for i in range(n))
    return matching, total


def set_penalty(friendly, singles):
    penalty = 0.0
    kinds = Counter(
        f["fanout_kind"] for f in friendly if f["subcategory"] == "fan-out"
    )
    for count in kinds.values():
        penalty += DUP_FANOUT_KIND_PENALTY * (count - 1)
    repos = Counter(r["repo"] for r in friendly + singles)
    for count in repos.values():
        penalty += REPO_OVERFLOW_PENALTY * max(0, count - MAX_PER_REPO_SOFT)
    return penalty


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--classified",
                    default=str(ROOT / "annotation" / "classified.json"))
    ap.add_argument("--out", default=str(ROOT / "selection_v3.json"))
    args = ap.parse_args()

    rows = json.loads(pathlib.Path(args.classified).read_text())
    friendly = [r for r in rows.values() if r["category"] == "orchestration-friendly"]
    singles = [r for r in rows.values() if r["category"] == "single-friendly"]
    risky = [r for r in rows.values() if r["category"] == "orchestration-risky"]
    friendly.sort(key=lambda r: r["instance_id"])
    singles.sort(key=lambda r: r["instance_id"])
    risky.sort(key=lambda r: r["instance_id"])

    n_fanout = sum(1 for f in friendly if f["subcategory"] == "fan-out")
    print(f"# friendly={len(friendly)} (fan-out={n_fanout}, "
          f"sequential={len(friendly) - n_fanout}) "
          f"single={len(singles)} risky={len(risky)}")

    short = []
    if len(friendly) < N_PAIRS or n_fanout < MIN_FANOUT:
        short.append("orchestration-friendly")
    if len(singles) < N_PAIRS:
        short.append("single-friendly")
    if len(risky) < N_RISKY:
        short.append("orchestration-risky")
    if short:
        raise SystemExit(
            "pool cannot fill: " + ", ".join(short)
            + "\nExtend the pool with candidate_pool.py --size <N+10> and "
              "annotate the new block. Do not loosen the rubric."
        )

    best = None
    for subset in itertools.combinations(range(len(friendly)), N_PAIRS):
        chosen = [friendly[i] for i in subset]
        if sum(1 for f in chosen if f["subcategory"] == "fan-out") < MIN_FANOUT:
            continue
        cost = [[pair_cost(f, s) for s in singles] for f in chosen]
        matching, total = assign(chosen, singles, cost)
        matched_singles = [singles[j] for j in matching]
        score = total + set_penalty(chosen, matched_singles)
        if best is None or score < best[0]:
            best = (score, chosen, matched_singles, cost, matching)

    if best is None:
        raise SystemExit(f"no admissible friendly 5-subset with >= {MIN_FANOUT} fan-out")

    score, chosen, matched, cost, matching = best
    pairs = [
        {
            "orchestration_friendly": f["instance_id"],
            "subcategory": f["subcategory"],
            "fanout_kind": f["fanout_kind"],
            "single_friendly": s["instance_id"],
            "same_repo": f["repo"] == s["repo"],
            "mismatch": round(cost[i][matching[i]], 3),
            "difficulty_overall": [f["difficulty_overall"], s["difficulty_overall"]],
            "change_type": [f["change_type"], s["change_type"]],
        }
        for i, (f, s) in enumerate(zip(chosen, matched))
    ]

    # Risky tasks get a reference from the five already chosen, so the
    # comparison is against a task that is in the experiment anyway.
    risky_scored = sorted(
        risky,
        key=lambda r: min(pair_cost(r, f) for f in chosen),
    )[:N_RISKY]
    risky_out = []
    for r in risky_scored:
        ref = min(chosen, key=lambda f: pair_cost(r, f))
        risky_out.append({
            "orchestration_risky": r["instance_id"],
            "friendly_reference": ref["instance_id"],
            "mismatch": round(pair_cost(r, ref), 3),
        })

    tasks = (
        [p["orchestration_friendly"] for p in pairs]
        + [p["single_friendly"] for p in pairs]
        + [r["orchestration_risky"] for r in risky_out]
    )

    print(f"# total mismatch (incl. set penalties) = {score:.3f}\n")
    print("orchestration-friendly\tsubcategory\tfanout_kind\tsingle-friendly\tmismatch\tsame_repo")
    for p in pairs:
        print(f"{p['orchestration_friendly']}\t{p['subcategory']}\t{p['fanout_kind']}\t"
              f"{p['single_friendly']}\t{p['mismatch']}\t{p['same_repo']}")
    print("\norchestration-risky\tfriendly_reference\tmismatch")
    for r in risky_out:
        print(f"{r['orchestration_risky']}\t{r['friendly_reference']}\t{r['mismatch']}")
    print("\n# repo mix: " + ", ".join(
        f"{k}={v}" for k, v in sorted(Counter(rows[t]["repo"] for t in tasks).items())))

    out = {
        "weights": {
            "difficulty": W_DIFFICULTY,
            "change_type": W_CHANGE_TYPE,
            "investigation_volume": W_INVESTIGATION,
            "struct_lines": W_STRUCT_LINES,
            "struct_files": W_STRUCT_FILES,
            "same_repo_bonus": SAME_REPO_BONUS,
            "dup_fanout_kind_penalty": DUP_FANOUT_KIND_PENALTY,
            "repo_overflow_penalty": REPO_OVERFLOW_PENALTY,
            "max_per_repo_soft": MAX_PER_REPO_SOFT,
            "min_fanout": MIN_FANOUT,
        },
        "total_mismatch": round(score, 3),
        "pairs": pairs,
        "risky": risky_out,
        "tasks": tasks,
    }
    pathlib.Path(args.out).write_text(json.dumps(out, indent=2) + "\n")
    print(f"\n# wrote {args.out}  ({len(tasks)} tasks)")


if __name__ == "__main__":
    main()
