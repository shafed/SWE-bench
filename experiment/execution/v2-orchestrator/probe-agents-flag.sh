#!/usr/bin/env bash
# Probe A settled it: --disallowedTools reaches subagents, so a plain denial
# removes the tool from the whole session, orchestrator and team alike. The arm
# is only implementable if a custom agent type can be given Write explicitly.
# Probe C failed with "Agent type 'worker' not found", which has two candidate
# causes: --setting-sources '' discards custom agents, or the --agents payload
# shape is wrong. These three runs separate them.
set -u
BASE="${TMPDIR:-/tmp}/nir-agentsflag.$$"
AGENTS='{"worker":{"description":"Makes the code changes","prompt":"You implement what you are asked to implement.","tools":["Read","Write","Edit","Bash","Grep","Glob"]}}'
COMMON=(--model claude-sonnet-5 --output-format json
        --permission-mode bypassPermissions --safe-mode
        --strict-mcp-config --mcp-config '{"mcpServers":{}}')
ASK="List every subagent type you can pass to the Task tool, exactly as named. Do not spawn any. Answer with the names only."

run () { local name="$1"; shift; local d="$BASE/$name"; mkdir -p "$d"; cd "$d" || return
  timeout 300 claude -p "$1" "${COMMON[@]}" "${@:2}" >"$d/out.json" 2>"$d/err.log"
  echo "=== $name"
  python3 -c "
import json
try: r=json.load(open('$d/out.json'))
except Exception as e: print('  unparsed:',e); raise SystemExit
print('  is_error:',r.get('is_error'))
print(' ',(r.get('result') or '')[:400].replace(chr(10),' | '))"
  [ -f "$d/probe.txt" ] && echo "  probe.txt WRITTEN" || echo "  probe.txt absent"
}

echo "claude version: $(claude --version)"
run D1_isolated  "$ASK" --setting-sources '' --agents "$AGENTS"
run D2_ambient   "$ASK" --agents "$AGENTS"
run D3_write     "Use the Task tool to spawn a subagent of type 'worker'. Instruct it to use the Write tool to create probe.txt in the current directory containing the word OK. Report whether it succeeded or was blocked." \
                 --agents "$AGENTS" --disallowedTools Write Edit NotebookEdit WebFetch WebSearch
echo; echo "artifacts under: $BASE"
