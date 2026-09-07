#!/usr/bin/env bash
# Materialises one read-only checkout per v3 candidate at its base commit,
# for pass-1 annotation. One clone per repository, one worktree per instance.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
CLONES="${NIR_V3_CLONES:-$HOME/.cache/nir-v3-repos}"
TREES="${NIR_V3_WORKTREES:-$HOME/.cache/nir-v3-worktrees}"
mkdir -p "$CLONES" "$TREES"

python3 - "$ROOT/annotation/checkouts.json" <<'PY' | while IFS=$'\t' read -r iid repo commit tree; do
import json, sys
for iid, v in json.load(open(sys.argv[1])).items():
    print(f"{iid}\t{v['repo']}\t{v['base_commit']}\t{v['worktree']}")
PY
    slug="${repo//\//__}"
    clone="$CLONES/$slug"
    if [ ! -d "$clone" ]; then
        echo "== cloning $repo"
        git clone --quiet "https://github.com/$repo.git" "$clone"
    fi
    if [ -d "$tree/.git" ] || [ -f "$tree/.git" ]; then
        echo "-- $iid already checked out"
        continue
    fi
    if ! git -C "$clone" cat-file -e "$commit^{commit}" 2>/dev/null; then
        echo "== fetching $commit for $repo"
        git -C "$clone" fetch --quiet origin "$commit" || git -C "$clone" fetch --quiet --all
    fi
    echo "== worktree $iid"
    git -C "$clone" worktree add --quiet --detach "$tree" "$commit"
done
echo "done"
