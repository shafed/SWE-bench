# /// script
# requires-python = ">=3.11"
# dependencies = ["datasets>=2.19"]
# ///
#
# Builds the per-candidate annotation bundles for the v3 selection.
#
# pass1/<instance_id>.md  problem statement only (no gold patch, no dataset
#                         difficulty label -- the annotator estimates
#                         difficulty itself in pass 2, and the label would
#                         anchor it).
# pass2/<instance_id>.md  gold patch + FAIL_TO_PASS node ids.
#
# Neither bundle names the target category counts, the other candidates, or
# any SINGLE/MULTI result.

import json
import pathlib

from datasets import load_dataset

ROOT = pathlib.Path(__file__).resolve().parent
CANDIDATES = json.loads((ROOT / "candidates.json").read_text())
CHECKOUTS = pathlib.Path.home() / ".cache/nir-v3-src"


def main():
    ds = load_dataset(CANDIDATES["dataset"], split=CANDIDATES["split"])
    by_id = {r["instance_id"]: r for r in ds}

    p1 = ROOT / "annotation" / "pass1"
    p2 = ROOT / "annotation" / "pass2"
    p1.mkdir(parents=True, exist_ok=True)
    p2.mkdir(parents=True, exist_ok=True)

    for cand in CANDIDATES["candidates"]:
        iid = cand["instance_id"]
        inst = by_id[iid]
        tree = CHECKOUTS / iid

        (p1 / f"{iid}.md").write_text(
            f"# Candidate {iid}\n\n"
            f"- repository: `{inst['repo']}`\n"
            f"- base commit: `{inst['base_commit']}`\n"
            f"- checkout: `{tree}`\n\n"
            "The checkout is the repository as it stands before the fix, with\n"
            "no git history. The tests that accompany the fix are not present.\n\n"
            "## Problem statement\n\n"
            f"{inst['problem_statement']}\n"
        )

        f2p = inst["FAIL_TO_PASS"]
        if isinstance(f2p, str):
            f2p = json.loads(f2p)
        (p2 / f"{iid}.md").write_text(
            f"# Candidate {iid} — gold patch\n\n"
            f"- repository: `{inst['repo']}`\n"
            f"- base commit: `{inst['base_commit']}`\n"
            f"- checkout: `{tree}`\n\n"
            "## Tests that must go from failing to passing\n\n"
            + "".join(f"- `{t}`\n" for t in f2p)
            + "\n## Problem statement\n\n"
            f"{inst['problem_statement']}\n\n"
            "## Gold patch\n\n```diff\n"
            f"{inst['patch']}\n```\n"
        )

    checkouts = {
        c["instance_id"]: {
            "repo": by_id[c["instance_id"]]["repo"],
            "base_commit": by_id[c["instance_id"]]["base_commit"],
            "checkout": str(CHECKOUTS / c["instance_id"]),
        }
        for c in CANDIDATES["candidates"]
    }
    (ROOT / "annotation" / "checkouts.json").write_text(
        json.dumps(checkouts, indent=2) + "\n"
    )
    print(f"wrote {len(CANDIDATES['candidates'])} pass1 + pass2 bundles")


if __name__ == "__main__":
    main()
