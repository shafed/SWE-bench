#!/usr/bin/env bash
# The orchestrator arm removes Edit/Write/NotebookEdit from the main loop and
# keeps Read/Grep/Glob/Bash, so it can still explore and verify. That only works
# if the denial does NOT reach subagents. Two questions:
#   A  does --disallowedTools Write Edit block a *subagent's* Write?
#   C  does --agents accept a per-agent tool list, so the worker can be given
#      Write explicitly without touching --setting-sources?
# If A blocks, the arm is not implementable as a plain denial and C is the only
# route. If both block, the arm is dead on this CLI version.
set -u
BASE="${TMPDIR:-/tmp}/nir-toolscope.$$"
COMMON=(--model claude-sonnet-5 --output-format json
        --permission-mode bypassPermissions --safe-mode
        --setting-sources '' --strict-mcp-config --mcp-config '{"mcpServers":{}}')

probe () { # name, prompt, extra flags...
  local name="$1" prompt="$2"; shift 2
  local d="$BASE/$name"; mkdir -p "$d"; cd "$d" || return
  timeout 300 claude -p "$prompt" "${COMMON[@]}" "$@" >"$d/out.json" 2>"$d/err.log"
  if [ -f "$d/probe.txt" ]; then echo "$name: subagent WROTE the file -> denial does not reach subagents"
  else echo "$name: no file -> blocked, or the subagent never ran (read out.json)"; fi
}

echo "claude version: $(claude --version)"

probe A_plain_denial \
  "Use the Task tool to spawn a general-purpose subagent. Instruct it to use the Write tool to create probe.txt in the current directory containing the word OK. Report whether it succeeded or was blocked." \
  --disallowedTools Write Edit NotebookEdit WebFetch WebSearch

probe C_agents_tools \
  "Use the Task tool to spawn a subagent of type 'worker'. Instruct it to use the Write tool to create probe.txt in the current directory containing the word OK. Report whether it succeeded or was blocked." \
  --disallowedTools Write Edit NotebookEdit WebFetch WebSearch \
  --agents '{"worker":{"description":"Makes the code changes","prompt":"You implement what you are asked to implement.","tools":["Read","Write","Edit","Bash","Grep","Glob"]}}'

echo
echo "artifacts under: $BASE"
for f in "$BASE"/*/err.log; do [ -s "$f" ] && { echo "--- $f"; head -c 400 "$f"; echo; }; done
