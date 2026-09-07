#!/usr/bin/env bash
# Materialises one checkout per v3 candidate at its base commit.
#
# Deliberately `git archive`, not `git worktree`: a worktree keeps the whole
# clone reachable, so a pass-1 annotator could walk forward from base_commit
# and read the actual fix commit. Pass 1 must be blind to the fix, so the
# checkout carries no git history at all.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
CLONES="${NIR_V3_CLONES:-$HOME/.cache/nir-v3-repos}"
SRC="${NIR_V3_SRC:-$HOME/.cache/nir-v3-src}"
mkdir -p "$CLONES" "$SRC"

python3 - "$ROOT/annotation/checkouts.json" <<'PY' | while IFS=$'\t' read -r iid repo commit dest; do
import json, sys
for iid, v in json.load(open(sys.argv[1])).items():
    print(f"{iid}\t{v['repo']}\t{v['base_commit']}\t{v['checkout']}")
PY
    slug="${repo//\//__}"
    clone="$CLONES/$slug"
    if [ ! -d "$clone" ]; then
        echo "== cloning $repo"
        git clone --quiet "https://github.com/$repo.git" "$clone"
    fi
    if [ -d "$dest" ] && [ -n "$(ls -A "$dest" 2>/dev/null)" ]; then
        continue
    fi
    if ! git -C "$clone" cat-file -e "$commit^{commit}" 2>/dev/null; then
        git -C "$clone" fetch --quiet origin "$commit" || git -C "$clone" fetch --quiet --all
    fi
    mkdir -p "$dest"
    git -C "$clone" archive "$commit" | tar -x -C "$dest"
    echo "== $iid"
done
echo "done"
