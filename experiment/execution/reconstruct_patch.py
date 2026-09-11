#!/usr/bin/env python3
"""
reconstruct_patch.py -- rebuild a run's final patch from its trace.

For runs whose collected artefacts (patch.diff, metrics.json, ...) were lost
but whose trace.jsonl survived. Never a substitute for a collected patch: the
output is written as patch-reconstructed.diff and must be reported as such.

Method
  * Start a fresh container of the task image (network none).
  * Replay, in the order their tool results arrived, every successful Edit and
    Write call from the parent agent and all subagents. Calls the CLI reported
    as errors changed nothing and are skipped.
  * Bash is not replayed wholesale (test runs, background jobs). Commands with
    a net effect on /testbed were audited by hand and are listed in
    BASH_EFFECTS as the git/formatter part only; round trips such as
    `git stash && <tests>; git stash pop` or copy-swap-restore are net zero.
  * Checkpoints: wherever the agent ran `git diff` or `git status`, or read a
    /testbed file, the replayed working tree is compared with the output the
    agent saw. A replay
    edit that no longer applies, or a checkpoint mismatch, means divergence.
  * The patch is collected exactly like runner.py:
    `git add -A && git diff --cached <base> --binary`.

Limits: untracked files created only as side effects of commands that are not
replayed (test artefacts) cannot be reproduced; a full `git status` checkpoint
after the last change shows whether any existed at that point.
"""

from __future__ import annotations

import argparse
import collections
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PY = "/opt/miniconda3/bin/python3"

# (instance, condition) -> {op index in extract() order: command run in /testbed}
BASH_EFFECTS: dict[tuple[str, str], dict[int, str]] = {
    ("django__django-16938", "multi"): {
        40: "git stash push -- django/core/serializers/python.py "
        "django/core/serializers/xml_serializer.py",
        42: "git stash pop",
    },
    ("django__django-16938", "single"): {
        39: "/opt/miniconda3/envs/testbed/bin/python -m black "
        "django/core/serializers/python.py django/core/serializers/xml_serializer.py "
        "tests/serializers/models/base.py tests/serializers/tests.py",
    },
    ("pylint-dev__pylint-8898", "single"): {
        42: "git stash",
        45: "git stash apply",
        46: "git stash drop",
    },
    ("pytest-dev__pytest-5787", "single"): {
        35: "git stash",
        38: "git stash apply",
        40: "git stash",
        75: "git stash apply 'stash@{0}'",
        76: "git stash drop 'stash@{0}'; git stash drop 'stash@{0}'",
    },
    ("sympy__sympy-15017", "single"): {
        48: "git stash -- sympy/tensor/array/dense_ndim_array.py "
        "sympy/tensor/array/sparse_ndim_array.py",
        49: "git stash pop",
    },
}

HELPER = r"""
import json, os, sys
op = json.load(sys.stdin)
p = op["path"]
def write(text):
    d = os.path.dirname(p)
    if d:
        os.makedirs(d, exist_ok=True)
    with open(p, "w", encoding="utf-8", newline="") as fh:
        fh.write(text)
if op["kind"] == "write":
    write(op["content"]); print("ok"); sys.exit(0)
if not os.path.exists(p):
    if op["old"] == "":
        write(op["new"]); print("ok"); sys.exit(0)
    print("missing file"); sys.exit(3)
with open(p, encoding="utf-8", newline="") as fh:
    s = fh.read()
old, new = op["old"], op["new"]
n = s.count(old)
if n == 0:
    print("old_string not found"); sys.exit(4)
if n > 1 and not op["all"]:
    print("old_string ambiguous (%d matches)" % n); sys.exit(5)
write(s.replace(old, new) if op["all"] else s.replace(old, new, 1))
print("ok")
"""

CHECKPOINT = re.compile(r"\bgit\s+(?:-C\s+\S+\s+)?(diff|status)\b")
HUNK_META = ("index ", "--- ", "+++ ", "@@", "new file mode", "deleted file mode",
             "old mode", "new mode", "similarity", "rename ", "Binary files", "\\ No newline")


def extract(path: Path) -> list[dict]:
    """File-affecting tool calls, ordered by tool_result arrival."""
    uses, ops = {}, []
    for line in path.open():
        e = json.loads(line)
        content = (e.get("message") or {}).get("content")
        if not isinstance(content, list):
            continue
        if e.get("type") == "assistant":
            for c in content:
                if c.get("type") == "tool_use":
                    uses[c["id"]] = c
        elif e.get("type") == "user":
            for c in content:
                if c.get("type") == "tool_result" and c.get("tool_use_id") in uses:
                    u = uses.pop(c["tool_use_id"])
                    res = c.get("content")
                    if isinstance(res, list):
                        res = "\n".join(p.get("text", "") for p in res if isinstance(p, dict))
                    ops.append({"name": u["name"], "input": u.get("input", {}),
                                "is_error": bool(c.get("is_error")), "result": res or ""})
    return ops


def parse_diff(text: str) -> dict[str, collections.Counter]:
    """+/- lines per file. Hunks are consumed by the counts in their @@ header,
    so output printed right after a diff (`echo ---`) is not read as a line."""
    files: dict[str, collections.Counter] = {}
    cur, old_left, new_left = None, 0, 0
    for line in text.splitlines():
        if line.startswith("diff --git a/"):
            cur, old_left, new_left = line.split(" b/", 1)[1], 0, 0
            files.setdefault(cur, collections.Counter())
            continue
        m = re.match(r"^@@ -\d+(?:,(\d+))? \+\d+(?:,(\d+))? @@", line)
        if cur is not None and m:
            old_left = int(m.group(1)) if m.group(1) is not None else 1
            new_left = int(m.group(2)) if m.group(2) is not None else 1
            continue
        if cur is None or (old_left <= 0 and new_left <= 0):
            continue
        if line.startswith("-"):
            files[cur][("-", line[1:].rstrip())] += 1
            old_left -= 1
        elif line.startswith("+"):
            files[cur][("+", line[1:].rstrip())] += 1
            new_left -= 1
        elif line.startswith(" ") or line == "":
            old_left -= 1
            new_left -= 1
        elif not line.startswith("\\"):
            old_left = new_left = 0  # truncated output
    return files


def parse_porcelain(text: str) -> tuple[set, set]:
    tracked, untracked = set(), set()
    for line in text.splitlines():
        m = re.match(r"^([ MADRCUT?!]{2}) (\S.*)$", line)
        if m:
            (untracked if m.group(1) == "??" else tracked).add(m.group(2).split(" -> ")[-1])
    return tracked, untracked


def parse_status(text: str) -> tuple[set, set, bool]:
    tracked, untracked, in_untracked = set(), set(), False
    clean = "working tree clean" in text
    for line in text.splitlines():
        m = re.match(r"^\t(modified|new file|deleted|renamed|typechange):\s+(.+)$", line)
        if m:
            tracked.add(m.group(2).split(" -> ")[-1])
            in_untracked = False
        elif line.startswith("Untracked files:"):
            in_untracked = True
        elif in_untracked and line.startswith("\t"):
            untracked.add(line.strip())
        elif in_untracked and not line.startswith("  ("):
            in_untracked = False
    return tracked, untracked, clean


def parse_stat(text: str) -> dict[str, int]:
    out = {}
    for line in text.splitlines():
        m = re.match(r"^ (\S.*?)\s+\|\s+(\d+)( [+-]*)?$", line)
        if m:
            out[m.group(1)] = int(m.group(2))
    return out


class Container:
    def __init__(self, image: str, name: str):
        self.name = name
        subprocess.run(["docker", "rm", "-f", name], capture_output=True)
        subprocess.run(["docker", "run", "-d", "--rm", "--network", "none", "--name", name,
                        "--entrypoint", "sleep", image, "infinity"], check=True,
                       capture_output=True)
        self.sh("git config --global --add safe.directory /testbed && "
                "git config --global user.email recon@local && "
                "git config --global user.name recon")

    def sh(self, cmd: str, stdin: str | None = None, check: bool = True) -> subprocess.CompletedProcess:
        p = subprocess.run(["docker", "exec", "-i", "-w", "/testbed", self.name, "bash", "-c", cmd],
                           input=stdin, capture_output=True, text=True)
        if check and p.returncode:
            raise RuntimeError(f"{cmd!r} failed: {p.stderr[-500:]}")
        return p

    def close(self):
        subprocess.run(["docker", "rm", "-f", self.name], capture_output=True)


def state(c: Container) -> dict:
    diff = c.sh("git diff HEAD").stdout
    numstat = {}
    for line in c.sh("git diff HEAD --numstat").stdout.splitlines():
        a, d, path = line.split("\t", 2)
        numstat[path] = (int(a) if a != "-" else 0) + (int(d) if d != "-" else 0)
    tracked, untracked = set(), set()
    for line in c.sh("git status --porcelain").stdout.splitlines():
        (untracked if line.startswith("??") else tracked).add(line[3:].split(" -> ")[-1])
    return {"diff": parse_diff(diff), "numstat": numstat, "tracked": tracked, "untracked": untracked}


def compare(cmd: str, recorded: str, st: dict) -> dict:
    problems, checks = [], []
    rec_diff = parse_diff(recorded)
    for path, lines in rec_diff.items():
        checks.append("diff")
        missing = lines - st["diff"].get(path, collections.Counter())
        if missing:
            problems.append(f"diff {path}: {sum(missing.values())} recorded +/- lines absent in replay")
    full_diff = bool(re.fullmatch(r"\s*(cd /testbed && )?git diff( HEAD)?\s*", cmd))
    if full_diff and "truncated" not in recorded:
        checks.append("full-diff")
        if set(rec_diff) != set(st["diff"]):
            problems.append(f"full diff files differ: recorded {sorted(rec_diff)} replay {sorted(st['diff'])}")
        for path in rec_diff.keys() & st["diff"].keys():
            if rec_diff[path] != st["diff"][path]:
                problems.append(f"full diff {path}: line multisets differ")
    for path, n in parse_stat(recorded).items():
        checks.append("stat")
        match = [p for p in st["numstat"] if p == path or (path.startswith("...") and p.endswith(path[3:]))]
        if not match or st["numstat"][match[0]] != n:
            problems.append(f"stat {path}: recorded {n}, replay {[st['numstat'][m] for m in match]}")
    if re.search(r"\bgit status\b(?!\s+(-s|--short|--porcelain))", cmd) and (
        "On branch" in recorded or "HEAD detached" in recorded
    ):
        tracked, untracked, clean = parse_status(recorded)
        checks.append("status")
        if clean and (st["tracked"] or st["untracked"]):
            problems.append(f"status: recorded clean, replay {sorted(st['tracked'] | st['untracked'])}")
        if not clean and tracked != st["tracked"]:
            problems.append(f"status tracked: recorded {sorted(tracked)} replay {sorted(st['tracked'])}")
        if not clean and untracked != st["untracked"]:
            problems.append(f"status untracked: recorded {sorted(untracked)} replay {sorted(st['untracked'])}")
    if re.search(r"\bgit status\s+(-s|--short|--porcelain)\b", cmd):
        tracked, untracked = parse_porcelain(recorded)
        checks.append("porcelain")
        if (tracked, untracked) != (st["tracked"], st["untracked"]):
            problems.append(f"porcelain: recorded {sorted(tracked)} + ?? {sorted(untracked)}, "
                            f"replay {sorted(st['tracked'])} + ?? {sorted(st['untracked'])}")
    return {"checks": checks, "problems": problems}


def compare_read(recorded: str, current: str | None) -> dict:
    """A Read result is `N<TAB>line`; every numbered line must match the replay."""
    lines = [(int(m.group(1)), m.group(2)) for m in
             (re.match(r"^(\d+)\t(.*)$", l) for l in recorded.splitlines()) if m]
    if not lines:
        return {"checks": [], "problems": []}
    if current is None:
        return {"checks": ["read"], "problems": ["read: file missing in replay"]}
    have = current.split("\n")
    bad = [n for n, text in lines if n > len(have) or have[n - 1].rstrip() != text.rstrip()]
    return {"checks": ["read"], "problems": [f"read: {len(bad)} of {len(lines)} lines differ, first at {bad[0]}"] if bad else []}


def reconstruct(run_dir: Path, image: str) -> dict:
    instance, condition = run_dir.parent.name, run_dir.name
    effects = BASH_EFFECTS.get((instance, condition), {})
    ops = extract(run_dir / "trace.jsonl")
    c = Container(image, f"recon-{instance}-{condition}".replace("_", "-").lower())
    report = {"instance_id": instance, "condition": condition, "image": image,
              "edits_replayed": 0, "writes_replayed": 0, "bash_effects_replayed": 0,
              "replay_failures": [], "checkpoints": [], "last_change_op": None}
    try:
        report["base_commit"] = c.sh("git rev-parse HEAD").stdout.strip()
        for i, op in enumerate(ops):
            name, inp = op["name"], op["input"]
            if name in ("Edit", "Write") and not op["is_error"]:
                payload = ({"kind": "write", "path": inp["file_path"], "content": inp["content"]}
                           if name == "Write" else
                           {"kind": "edit", "path": inp["file_path"], "old": inp["old_string"],
                            "new": inp["new_string"], "all": bool(inp.get("replace_all"))})
                p = subprocess.run(["docker", "exec", "-i", c.name, PY, "-c", HELPER],
                                   input=json.dumps(payload), capture_output=True, text=True)
                if p.returncode:
                    report["replay_failures"].append({"op": i, "tool": name, "path": inp["file_path"],
                                                      "error": (p.stdout + p.stderr).strip()[-300:]})
                else:
                    report["edits_replayed" if name == "Edit" else "writes_replayed"] += 1
                report["last_change_op"] = i
            elif name == "Read" and not op["is_error"] and inp.get("file_path", "").startswith("/testbed/"):
                p = c.sh(f"cat -- {json.dumps(inp['file_path'])}", check=False)
                result = compare_read(op["result"], p.stdout if p.returncode == 0 else None)
                if result["checks"]:
                    report["checkpoints"].append({"op": i, "command": f"Read {inp['file_path']}", **result})
            elif name == "Bash":
                cmd = inp.get("command", "")
                if i in effects:
                    p = c.sh(effects[i], check=False)
                    report["bash_effects_replayed"] += 1
                    report["last_change_op"] = i
                    if p.returncode:
                        report["replay_failures"].append({"op": i, "tool": "Bash", "command": effects[i],
                                                          "error": (p.stdout + p.stderr).strip()[-300:]})
                if CHECKPOINT.search(cmd):
                    result = compare(cmd, op["result"], state(c))
                    if result["checks"]:
                        report["checkpoints"].append({"op": i, "command": cmd[:200], **result})
        final = [cp for cp in report["checkpoints"]
                 if report["last_change_op"] is None or cp["op"] > report["last_change_op"]]
        report["checkpoints_total"] = len(report["checkpoints"])
        report["checkpoints_failed"] = sum(bool(cp["problems"]) for cp in report["checkpoints"])
        report["final_checks"] = sorted({k for cp in final for k in cp["checks"]})
        report["final_checks_failed"] = sum(bool(cp["problems"]) for cp in final)
        report["last_checkpoint_ok"] = not final[-1]["problems"] if final else None
        report["untracked_before_staging"] = c.sh(
            "git ls-files --others --exclude-standard").stdout.split()
        patch = c.sh(f"git add -A && git diff --cached {report['base_commit']} --binary").stdout
        (run_dir / "patch-reconstructed.diff").write_text(patch)
        report["patch_bytes"] = len(patch.encode())
    finally:
        c.close()
    (run_dir / "reconstruction.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


def image_for(instance: str) -> str:
    repo, num = instance.rsplit("-", 1)
    return f"swebench/sweb.eval.x86_64.{repo.replace('__', '_1776_')}-{num}:latest"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("label", help="run label under experiment/runs/")
    ap.add_argument("--instance", action="append", help="limit to these instances")
    ap.add_argument("--condition", action="append", choices=["single", "multi"])
    args = ap.parse_args()
    runs = sorted((ROOT / "experiment" / "runs" / args.label).glob("*/*/trace.jsonl"))
    for trace in runs:
        run_dir = trace.parent
        if args.instance and run_dir.parent.name not in args.instance:
            continue
        if args.condition and run_dir.name not in args.condition:
            continue
        r = reconstruct(run_dir, image_for(run_dir.parent.name))
        print(f"{r['instance_id']:<34} {r['condition']:<6} edits={r['edits_replayed']:<3} "
              f"writes={r['writes_replayed']} bash={r['bash_effects_replayed']} "
              f"fail={len(r['replay_failures'])} cp={r['checkpoints_total']}/-{r['checkpoints_failed']} "
              f"final={','.join(r['final_checks']) or '-'}/-{r['final_checks_failed']} "
              f"last_ok={r['last_checkpoint_ok']} "
              f"bytes={r['patch_bytes']}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
