#!/usr/bin/env bash
# E1/E2/E3 all failed: --agents is ignored in -p mode even with the payload
# copied from --help, and a project-scope .claude/agents/worker.md did not
# register either. One untested explanation remains for the file route: the
# probe directory was an untrusted, non-git scratch dir, so project settings
# may never have been loaded. Two scopes the runner actually controls:
#   F1 project scope inside a real git repo
#   F2 user scope under a private HOME (this is where the runner could ship it)
#   F3 same as F2 with no --setting-sources flag at all (CLI defaults)
# If none registers, structural enforcement is unavailable on this version and
# the orchestrator constraint has to be prompt-level plus trace-based auditing.
set -u
BASE="${TMPDIR:-/tmp}/nir-agentscope.$$"
COMMON=(--model claude-sonnet-5 --output-format json
        --permission-mode bypassPermissions --safe-mode
        --strict-mcp-config --mcp-config '{"mcpServers":{}}')
ASK="List every subagent type you can pass to the Task tool, exactly as named. Do not spawn any. Answer with the names only."

agentfile () { mkdir -p "$1"; cat > "$1/worker.md" <<'MD'
---
name: worker
description: Makes the code changes
tools: Read, Write, Edit, Bash, Grep, Glob
---
You implement what you are asked to implement.
MD
}

run () { local name="$1" d="$2"; shift 2; cd "$d" || return
  timeout 300 env "$@" claude -p "$ASK" "${COMMON[@]}" "${EXTRA[@]}" >"$d/out.json" 2>"$d/err.log"
  echo "=== $name"
  python3 -c "
import json
try: r=json.load(open('$d/out.json'))
except Exception as e: print('  unparsed:',e); raise SystemExit
print(' ',(r.get('result') or '')[:300].replace(chr(10),' | '))"
  [ -s "$d/err.log" ] && { echo "  stderr:"; head -c 300 "$d/err.log"; }
}

echo "claude version: $(claude --version)"

D1="$BASE/F1_git_project"; mkdir -p "$D1"; git -C "$D1" init -q
agentfile "$D1/.claude/agents"
EXTRA=(--setting-sources project); run F1_git_project "$D1" HOME="$HOME"

D2="$BASE/F2_user_home"; mkdir -p "$D2/home"
agentfile "$D2/home/.claude/agents"
EXTRA=(--setting-sources user); run F2_user_home "$D2" HOME="$D2/home"

D3="$BASE/F3_user_default"; mkdir -p "$D3/home"
agentfile "$D3/home/.claude/agents"
EXTRA=(); run F3_user_default "$D3" HOME="$D3/home"

echo; echo "artifacts under: $BASE"
