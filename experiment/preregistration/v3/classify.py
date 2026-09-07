# /// script
# requires-python = ">=3.11"
# ///
#
# Applies the fixed RUBRIC.md profile rules to the two-pass annotation scores.
# The annotator produces features; this file produces categories. Keeping the
# two apart is what stops a category quota from leaking back into scoring.

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent
SCORES = ROOT / "annotation" / "scores"

P1_FIELDS = {
    "spec_clarity": (0, 2),
    "discoverability": (0, 2),
    "early_fanout": (0, 2),
}
P1_ENUMS = {
    "fanout_kind": {
        "parallel-investigation", "parallel-implementation", "mixed", "none",
    }
}
P1_BOOLS = ["env_risk"]

P2_FIELDS = {
    "n_subtasks": (0, 2),
    "independence": (0, 2),
    "integration_cost": (0, 2),
    "global_context": (0, 2),
    "locality": (0, 2),
    "difficulty_overall": (0, 4),
    "investigation_volume": (0, 2),
}
P2_ENUMS = {
    "change_type": {
        "bugfix", "behavior-change", "feature", "refactor",
        "validation-error-message",
    }
}
P2_BOOLS = ["nonproduction_patch", "unsolvable"]


def check(record, iid, ranges, enums, bools, where):
    problems = []
    for field, (lo, hi) in ranges.items():
        v = record.get(field)
        if not isinstance(v, int) or isinstance(v, bool) or not lo <= v <= hi:
            problems.append(f"{where}/{iid}: {field}={v!r} not an int in [{lo},{hi}]")
    for field, allowed in enums.items():
        v = record.get(field)
        if v not in allowed:
            problems.append(f"{where}/{iid}: {field}={v!r} not in {sorted(allowed)}")
    for field in bools:
        if not isinstance(record.get(field), bool):
            problems.append(f"{where}/{iid}: {field} must be true/false")
    return problems


def categorize(f):
    """Rules are verbatim from RUBRIC.md; do not tune them against results."""
    if f["spec_clarity"] == 0:
        return "excluded", "spec_clarity=0"
    if f["env_risk"]:
        return "excluded", "env_risk"
    if f["nonproduction_patch"]:
        return "excluded", "nonproduction_patch"
    if f["unsolvable"]:
        return "excluded", "unsolvable"

    friendly = (
        f["n_subtasks"] == 2
        and f["independence"] >= 1
        and f["integration_cost"] <= 1
        and f["global_context"] <= 1
        and f["locality"] <= 1
    )
    risky = f["n_subtasks"] == 2 and (
        f["integration_cost"] == 2
        or f["global_context"] == 2
        or f["independence"] == 0
    )
    single = (
        f["n_subtasks"] == 0
        and f["locality"] == 2
        and f["early_fanout"] == 0
        and f["discoverability"] <= 1
    )

    if friendly:
        if f["early_fanout"] == 2 and f["discoverability"] == 2:
            return "orchestration-friendly", "fan-out"
        return "orchestration-friendly", "sequential"
    if risky:
        return "orchestration-risky", "risky"
    if single:
        return "single-friendly", "single"
    return "borderline", "profile did not match any category"


def main():
    candidates = json.loads((ROOT / "candidates.json").read_text())["candidates"]
    by_id = {c["instance_id"]: c for c in candidates}

    problems, out, missing = [], {}, []
    for iid in by_id:
        f1 = SCORES / "pass1" / f"{iid}.json"
        f2 = SCORES / "pass2" / f"{iid}.json"
        if not f1.exists() or not f2.exists():
            missing.append(iid)
            continue
        r1, r2 = json.loads(f1.read_text()), json.loads(f2.read_text())
        problems += check(r1, iid, P1_FIELDS, P1_ENUMS, P1_BOOLS, "pass1")
        problems += check(r2, iid, P2_FIELDS, P2_ENUMS, P2_BOOLS, "pass2")
        if problems:
            continue
        feat = {**r1, **r2}
        category, sub = categorize(feat)
        out[iid] = {
            **{k: feat[k] for k in
               list(P1_FIELDS) + list(P1_ENUMS) + P1_BOOLS
               + list(P2_FIELDS) + list(P2_ENUMS) + P2_BOOLS},
            "instance_id": iid,
            "repo": by_id[iid]["repo"],
            "prod_code_lines": by_id[iid]["prod_code_lines"],
            "n_prod_files": by_id[iid]["n_prod_files"],
            "dataset_difficulty": by_id[iid]["difficulty"],
            "category": category,
            "subcategory": sub,
            "p1_notes": r1.get("p1_notes", ""),
            "p2_notes": r2.get("p2_notes", ""),
        }

    if problems:
        print("\n".join(problems), file=sys.stderr)
        sys.exit(f"{len(problems)} malformed score(s)")
    if missing:
        print(f"# not yet annotated ({len(missing)}): {' '.join(sorted(missing))}")

    from collections import Counter
    tally = Counter(
        v["subcategory"] if v["category"] == "orchestration-friendly" else v["category"]
        for v in out.values()
    )
    print("# categories: " + ", ".join(f"{k}={v}" for k, v in sorted(tally.items())))

    dest = ROOT / "annotation" / "classified.json"
    dest.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n")
    print(f"# wrote {dest}")

    fields = ["instance_id", "repo", "category", "subcategory",
              "difficulty_overall", "change_type", "investigation_volume",
              "n_subtasks", "independence", "integration_cost",
              "global_context", "locality", "discoverability",
              "early_fanout", "fanout_kind"]
    print("\t".join(fields))
    for iid in sorted(out, key=lambda i: (out[i]["category"], i)):
        print("\t".join(str(out[iid][f]) for f in fields))


if __name__ == "__main__":
    main()
