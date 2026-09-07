#!/usr/bin/env bash
# D1/D2 showed --agents is ignored silently, with or without --setting-sources,
# and stderr is empty. Three candidates remain:
#   E1 the flag works but the "tools" key invalidated the whole payload
#   E2 the flag is not honoured at all in -p mode (documented example fails too)
#   E3 the on-disk .claude/agents/<name>.md route works, at the cost of
#      --setting-sources project
# Whichever registers decides how the orchestrator arm is built.
set -u
BASE="${TMPDIR:-/tmp}/nir-agentreg.$$"
COMMON=(--model claude-sonnet-5 --output-format json
        --permission-mode bypassPermissions --safe-mode
        --strict-mcp-config --mcp-config '{"mcpServers":{}}')
ASK="List every subagent type you can pass to the Task tool, exactly as named. Do not spawn any. Answer with the names only."

run () { local name="$1" d="$BASE/$1"; shift; mkdir -p "$d"; cd "$d" || return
  timeout 300 claude -p "$ASK" "${COMMON[@]}" "$@" >"$d/out.json" 2>"$d/err.log"
  echo "=== $name"
  python3 -c "
import json
try: r=json.load(open('$d/out.json'))
except Exception as e: print('  unparsed:',e); raise SystemExit
print(' ',(r.get('result') or '')[:300].replace(chr(10),' | '))"
  [ -s "$d/err.log" ] && { echo "  stderr:"; head -c 300 "$d/err.log"; }
}

echo "claude version: $(claude --version)"

# E2 first: the payload copied verbatim from --help, no extra keys.
run E2_help_example --agents '{"reviewer":{"description":"Reviews code","prompt":"You are a code reviewer"}}'

# E1: same payload plus the tools key.
run E1_with_tools --agents '{"reviewer":{"description":"Reviews code","prompt":"You are a code reviewer","tools":["Read","Grep"]}}'

# E3: on-disk project agent. Needs the project setting source.
mkdir -p "$BASE/E3_file/.claude/agents"
cat > "$BASE/E3_file/.claude/agents/worker.md" <<'MD'
---
name: worker
description: Makes the code changes
tools: Read, Write, Edit, Bash, Grep, Glob
---
You implement what you are asked to implement.
MD
run E3_file --setting-sources project

echo; echo "artifacts under: $BASE"
