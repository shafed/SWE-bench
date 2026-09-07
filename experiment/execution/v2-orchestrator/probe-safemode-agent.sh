#!/usr/bin/env bash
# Root cause of E1/E2/E3/F1-F3: --safe-mode disables "custom commands and
# agents" and "workflows" outright (claude --help). Every earlier probe carried
# --safe-mode, copied from the runner, so no custom agent could ever register.
#
# --agent <agent> sets the agent for the SESSION itself. With --agents defining
# both roles, the main loop can be given Read/Grep/Glob/Bash/Task while the
# worker gets Write/Edit. That restricts the orchestrator only -- unlike
# --disallowedTools, which probe A showed is session-wide and reaches subagents.
set -u
BASE="${TMPDIR:-/tmp}/nir-safemode.$$"
AGENTS='{"orchestrator":{"description":"Plans and delegates","prompt":"You are the orchestrator. You cannot write files; delegate all file changes to the worker subagent.","tools":["Read","Grep","Glob","Bash","Task"]},"worker":{"description":"Makes the code changes","prompt":"You implement what you are asked to implement.","tools":["Read","Write","Edit","Bash","Grep","Glob"]}}'
COMMON=(--model claude-sonnet-5 --output-format json
        --permission-mode bypassPermissions
        --strict-mcp-config --mcp-config '{"mcpServers":{}}')

run () { local name="$1" prompt="$2"; shift 2; local d="$BASE/$name"
  mkdir -p "$d"; cd "$d" || return
  timeout 300 claude -p "$prompt" "${COMMON[@]}" "$@" >"$d/out.json" 2>"$d/err.log"
  echo "=== $name"
  python3 -c "
import json
try: r=json.load(open('$d/out.json'))
except Exception as e: print('  unparsed:',e); raise SystemExit
print(' ',(r.get('result') or '')[:450].replace(chr(10),' | '))"
  [ -f "$d/probe.txt" ] && echo "  >> probe.txt WRITTEN" || echo "  >> probe.txt absent"
  [ -s "$d/err.log" ] && { echo "  stderr:"; head -c 300 "$d/err.log"; }
}

echo "claude version: $(claude --version)"

ASK="Name the subagent types you can pass to the Task tool, and name your own available tools. Do not spawn anything."

# H1: does dropping --safe-mode register the custom agents at all?
run H1_register "$ASK" --setting-sources '' --agents "$AGENTS"

# H2: does --agent restrict the session itself to the orchestrator tool set?
run H2_restricted "$ASK" --setting-sources '' --agents "$AGENTS" --agent orchestrator

# H3: the real thing -- orchestrator cannot write, worker must.
run H3_delegate "Create a file probe.txt in the current directory containing exactly the word OK. Then report who created it and how." \
  --setting-sources '' --agents "$AGENTS" --agent orchestrator

echo; echo "artifacts under: $BASE"
