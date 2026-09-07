# /// script
# requires-python = ">=3.11"
# dependencies = ["datasets>=2.19"]
# ///
#
# v2 of experiment/preregistration/select_instances.py.
#
# Change from v1: "dispersion" no longer means "gold patch touches >=2
# directories". It means "gold patch touches >=2 directories AND those
# files don't share identifiers AND no single file dominates the diff".
# v1's D cells were being satisfied by tightly-coupled multi-file fixes
# (one real file + a one-line touch elsewhere, or files that only make
# sense read together) -- exactly the kind of task where a single agent
# has no reason to delegate, because there is no independent subtask to
# hand off. That is a plausible root cause for MULTI collapsing into
# "solve it all, delegate the test run".
#
# Change from v1: population is no longer fixed to SWE-bench_Verified.
# A four-rung ladder tries Verified first (highest annotation quality),
# then falls back to the combined Verified+full pool only if a rung
# can't fill every cell under the new, stricter dispersion definition.
# This is the same ladder *idea* v1 already used for difficulty
# (primary -> fallback); it's just extended with a second axis (pool).
#
# This script has NOT been run against live data in the environment
# that produced it (no dataset-hub network access there). Run
# --audit yourself before trusting any cell sizes or ladder step below.
#
# If any real (non-dev) instance from the v1 sample has already been
# run through the actual SINGLE/MULTI pipeline, do not silently swap
# this in for select_instances.py. Log it as a numbered deviation from
# PROTOCOL.md instead -- see DESIGN_NOTES.md.

import argparse
import hashlib
import json
import posixpath
import random
import re
from collections import Counter

from datasets import load_dataset


SOURCES = {
    "verified": ("SWE-bench/SWE-bench_Verified", "test"),
    "full": ("SWE-bench/SWE-bench", "test"),
}

EXCLUDE_INSTANCES = {"sympy__sympy-20590"}
EXCLUDE_REPOS = set()

PER_CELL = 2
RESERVE_PER_CELL = 2
MAX_PER_REPO = 2
MAX_SEED = 10000

MAX_FILE_SHARE = 0.7
COUPLING_MAX = 0.15

DISPERSION_LEVELS = ("L", "M", "D")
DIFFICULTY_LEVELS = ("lo", "hi")
CELL_ORDER = [
    (dispersion, difficulty)
    for dispersion in DISPERSION_LEVELS
    for difficulty in DIFFICULTY_LEVELS
]

LONG_LABELS = {"1-4 hours", ">4 hours", "proxy-long"}
EASY_LABELS = {"<15 min fix", "proxy-short"}

TEST_PATH = re.compile(
    r"(^|/)(tests?|testing)(/|$)"
    r"|(^|/)test_[^/]*\.py$"
    r"|_test\.py$"
    r"|(^|/)conftest\.py$"
)

FILE_HEADER = re.compile(r"^diff --git a/(\S+) b/\S+", re.M)
HUNK = re.compile(r"^@@ ", re.M)
ADDED = re.compile(r"^\+(?!\+\+\+)", re.M)
DELETED = re.compile(r"^-(?!---)", re.M)
ADDED_LINE = re.compile(r"^\+(?!\+\+\+)(.*)$", re.M)
DELETED_LINE = re.compile(r"^-(?!---)(.*)$", re.M)
IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]{2,}")

REQUIRE_TEST_DISPERSION = False


def patched_files(patch):
    return sorted(set(FILE_HEADER.findall(patch or "")))


def split_patch(patch):
    if not patch:
        return {}
    heads = list(FILE_HEADER.finditer(patch))
    blocks = {}
    for i, m in enumerate(heads):
        start = m.end()
        end = heads[i + 1].start() if i + 1 < len(heads) else len(patch)
        blocks[m.group(1)] = patch[start:end]
    return blocks


def file_stats(block):
    added = ADDED_LINE.findall(block)
    deleted = DELETED_LINE.findall(block)
    idents = set()
    for text in added + deleted:
        idents.update(IDENT.findall(text))
    return len(added) + len(deleted), idents


def coupling(prod_files, blocks):
    ident_sets = [file_stats(blocks.get(f, ""))[1] for f in prod_files]
    best = 0.0
    for i in range(len(ident_sets)):
        for j in range(i + 1, len(ident_sets)):
            a, b = ident_sets[i], ident_sets[j]
            union = a | b
            if union:
                best = max(best, len(a & b) / len(union))
    return best


def max_file_share(prod_files, blocks):
    counts = [file_stats(blocks.get(f, ""))[0] for f in prod_files]
    total = sum(counts)
    return (max(counts) / total) if total else 1.0


def test_modules(raw):
    try:
        tests = json.loads(raw) if isinstance(raw, str) else (raw or [])
    except (TypeError, ValueError):
        tests = []
    mods = set()
    for t in tests:
        path = t.split("::", 1)[0]
        mods.add(posixpath.dirname(path) or path)
    return mods


def features(inst):
    patch = inst.get("patch") or ""
    files = patched_files(patch)
    prod = [f for f in files if f.endswith(".py") and not TEST_PATH.search(f)]
    dirs = sorted({posixpath.dirname(f) for f in prod})
    blocks = split_patch(patch)

    return {
        "instance_id": inst["instance_id"],
        "repo": inst["repo"],
        "source": inst["source"],
        "n_prod_files": len(prod),
        "n_dirs": len(dirs),
        "n_hunks": len(HUNK.findall(patch)),
        "patch_lines": len(ADDED.findall(patch)) + len(DELETED.findall(patch)),
        "problem_len": len(inst.get("problem_statement") or ""),
        "prod_files": prod,
        "dirs": dirs,
        "coupling": round(coupling(prod, blocks), 3),
        "max_file_share": round(max_file_share(prod, blocks), 3),
        "n_test_modules": len(test_modules(inst.get("FAIL_TO_PASS") or "[]")),
    }


def assign_difficulty(inst, patch_lines, n_hunks):
    label = inst.get("difficulty")
    if label:
        return label, "annotated"
    proxy = "proxy-short" if patch_lines <= 20 and n_hunks <= 2 else "proxy-long"
    return proxy, "proxy"


def genuine_independent(row):
    ok = row["max_file_share"] <= MAX_FILE_SHARE and row["coupling"] <= COUPLING_MAX
    if REQUIRE_TEST_DISPERSION:
        ok = ok and row["n_test_modules"] >= 2
    return ok


def dispersion(row):
    if row["n_dirs"] >= 2 and genuine_independent(row):
        return "D"
    if row["n_prod_files"] >= 2:
        return "M"
    return "L"


def primary_difficulty(label):
    return "hi" if label in LONG_LABELS else "lo"


def fallback_difficulty(label):
    return "lo" if label in EASY_LABELS else "hi"


def cell_sizes(rows, fn):
    counts = Counter((dispersion(row), fn(row["difficulty"])) for row in rows)
    return {cell: counts.get(cell, 0) for cell in CELL_ORDER}


LADDER = [
    ("verified", "primary", primary_difficulty),
    ("verified", "fallback", fallback_difficulty),
    ("combined", "primary", primary_difficulty),
    ("combined", "fallback", fallback_difficulty),
]


def choose_split(rows_by_pool):
    report = []
    for pool_name, split_name, split_fn in LADDER:
        rows = rows_by_pool[pool_name]
        sizes = cell_sizes(rows, split_fn)
        report.append((pool_name, split_name, sizes))

        if min(sizes.values()) >= PER_CELL:
            full_reserves = min(sizes.values()) >= PER_CELL + RESERVE_PER_CELL
            step = f"{pool_name}/{split_name}/{'full' if full_reserves else 'partial'}"
            return pool_name, split_fn, step, report

    raise SystemExit("ladder exhausted: no pool/split has >=2 candidates per cell")


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
    main = [iid for cell in CELL_ORDER for iid in selection[cell][:PER_CELL]]
    counts = Counter(feat_by_id[iid]["repo"] for iid in main)
    return all(count <= MAX_PER_REPO for count in counts.values())


def load_pool():
    verified, full = [], []
    for source, (name, split) in SOURCES.items():
        ds = load_dataset(name, split=split)
        for inst in ds:
            d = dict(inst)
            d["source"] = source
            (verified if source == "verified" else full).append(d)

    verified_ids = {d["instance_id"] for d in verified}
    full = [d for d in full if d["instance_id"] not in verified_ids]
    return verified, full


def build_rows(instances, dropped_counter):
    rows = []
    for inst in instances:
        if inst["instance_id"] in EXCLUDE_INSTANCES:
            continue
        if inst["repo"] in EXCLUDE_REPOS:
            continue

        row = features(inst)
        if row["n_prod_files"] == 0:
            dropped_counter[0] += 1
            continue

        diff, dsource = assign_difficulty(inst, row["patch_lines"], row["n_hunks"])
        row["difficulty"] = diff
        row["difficulty_source"] = dsource
        rows.append(row)
    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--audit", action="store_true")
    parser.add_argument("--require-test-dispersion", action="store_true")
    args = parser.parse_args()

    global REQUIRE_TEST_DISPERSION
    REQUIRE_TEST_DISPERSION = args.require_test_dispersion

    script_sha = hashlib.sha256(open(__file__, "rb").read()).hexdigest()

    verified_inst, full_inst = load_pool()

    dropped = [0]
    verified_rows = build_rows(verified_inst, dropped)
    full_rows = build_rows(full_inst, dropped)
    combined_rows = verified_rows + full_rows

    rows_by_pool = {"verified": verified_rows, "combined": combined_rows}

    print(f"# script_sha256 = {script_sha}")
    print(f"# require_test_dispersion = {REQUIRE_TEST_DISPERSION}")
    print(f"# verified pool size = {len(verified_rows)}")
    print(f"# full-only pool size (dedup'd) = {len(full_rows)}")
    print(f"# dropped without production .py = {dropped[0]}")

    pool_name, split_fn, ladder_step, report = choose_split(rows_by_pool)

    for p_name, s_name, sizes in report:
        text = ", ".join(f"{d}/{f}={sizes[(d, f)]}" for d, f in CELL_ORDER)
        print(f"# sizes pool={p_name} split={s_name}: {text}")

    print(f"# ladder step = {ladder_step}")

    if args.audit:
        return

    rows = rows_by_pool[pool_name]
    feat_by_id = {row["instance_id"]: row for row in rows}

    pools = {cell: [] for cell in CELL_ORDER}
    for row in rows:
        cell = (dispersion(row), split_fn(row["difficulty"]))
        pools[cell].append(row["instance_id"])
    for cell in CELL_ORDER:
        pools[cell].sort()

    chosen = None
    used_seed = None
    for seed in range(MAX_SEED):
        candidate = draw(pools, seed)
        if candidate and repo_feasible(candidate, feat_by_id):
            chosen = candidate
            used_seed = seed
            break

    if chosen is None:
        raise SystemExit(f"No feasible seed below {MAX_SEED}")

    print(f"# selected seed = {used_seed}")
    print()

    records = []
    for cell in CELL_ORDER:
        for rank, iid in enumerate(chosen[cell]):
            record = dict(feat_by_id[iid])
            record["cell"] = f"{cell[0]}/{cell[1]}"
            record["role"] = (
                "main" if rank < PER_CELL else f"reserve{rank - PER_CELL + 1}"
            )
            records.append(record)

    fields = [
        "instance_id", "repo", "source", "difficulty", "difficulty_source",
        "n_prod_files", "n_dirs", "n_hunks", "patch_lines",
        "coupling", "max_file_share", "n_test_modules",
        "cell", "role",
    ]

    print("\t".join(fields))
    for record in records:
        print("\t".join(str(record[field]) for field in fields))

    output = {
        "pool": pool_name,
        "script_sha256": script_sha,
        "ladder_step": ladder_step,
        "seed": used_seed,
        "config": {
            "exclude_instances": sorted(EXCLUDE_INSTANCES),
            "exclude_repos": sorted(EXCLUDE_REPOS),
            "per_cell": PER_CELL,
            "reserve_per_cell": RESERVE_PER_CELL,
            "max_per_repo": MAX_PER_REPO,
            "max_file_share": MAX_FILE_SHARE,
            "coupling_max": COUPLING_MAX,
            "require_test_dispersion": REQUIRE_TEST_DISPERSION,
        },
        "records": records,
    }

    with open("experiment/preregistration/selection_v2.json", "w") as f:
        json.dump(output, f, indent=2)

    print("\n# wrote experiment/preregistration/selection_v2.json")


if __name__ == "__main__":
    main()
