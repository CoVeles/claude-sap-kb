#!/usr/bin/env bash
# sap-kb toolkit installer (macOS / Linux / Git-Bash)
#
# Usage:
#   ./install.sh                      # KB root -> $HOME/mcp-servers/sap-kb
#   ./install.sh /path/to/sap-kb      # custom KB root
#
# Installs: 2 skills, 2 agents, the _tools pipeline, an empty KB with a valid
# index, and appends the "use sap-kb first" rule to your global ~/.claude/CLAUDE.md.
# Re-running is safe: it backs up anything it would overwrite.
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KB_ROOT="${1:-$HOME/mcp-servers/sap-kb}"
CLAUDE_DIR="$HOME/.claude"
STAMP="$(date +%Y%m%d-%H%M%S)"

G='\033[0;32m'; Y='\033[0;33m'; R='\033[0;31m'; C='\033[0;36m'; N='\033[0m'
say() { printf '%b\n' "$1"; }

say ""
say "${C}sap-kb toolkit installer${N}"
say "  KB root      : $KB_ROOT"
say "  Claude config: $CLAUDE_DIR"
say ""

# ------------------------------------------------------------------ 1. prereqs
PY=""
for cand in python3 python; do
  if command -v "$cand" >/dev/null 2>&1; then PY="$cand"; break; fi
done
if [ -z "$PY" ]; then
  say "${R}ERROR: Python 3 not found on PATH. Install Python 3.9+ and re-run.${N}"; exit 1
fi
say "${G}  [ok] Python found: $($PY --version 2>&1)${N}"

if ! "$PY" -c "import fitz" >/dev/null 2>&1; then
  say "${Y}  [..] PyMuPDF (fitz) missing - installing via pip...${N}"
  if ! "$PY" -m pip install --quiet pymupdf; then
    say "${R}ERROR: 'pip install pymupdf' failed. Install it manually, then re-run.${N}"; exit 1
  fi
fi
say "${G}  [ok] PyMuPDF available${N}"

# --------------------------------------------------------------- 2. KB + tools
mkdir -p "$KB_ROOT/_tools"
cp -f "$SRC/kb/_tools/"* "$KB_ROOT/_tools/"
say "${G}  [ok] _tools installed -> $KB_ROOT/_tools${N}"

# --------------------------------------------- 3. skills (KB root substituted)
for skill in sap-kb sap-crawl; do
  mkdir -p "$CLAUDE_DIR/skills/$skill"
  dst="$CLAUDE_DIR/skills/$skill/SKILL.md"
  if [ -f "$dst" ]; then
    cp -f "$dst" "$dst.bak-$STAMP"
    say "${Y}  [..] existing $skill/SKILL.md backed up to SKILL.md.bak-$STAMP${N}"
  fi
  # '|' delimiter so Windows-style backslash paths pass through untouched
  sed "s|{{SAP_KB_ROOT}}|$KB_ROOT|g" "$SRC/skills/$skill/SKILL.md" > "$dst"
  say "${G}  [ok] skill installed: $skill${N}"
done

# -------------------------------------------------------------------- 4. agents
mkdir -p "$CLAUDE_DIR/agents"
for agent in sap-text-reader.md sap-image-reader.md; do
  dst="$CLAUDE_DIR/agents/$agent"
  [ -f "$dst" ] && cp -f "$dst" "$dst.bak-$STAMP"
  cp -f "$SRC/agents/$agent" "$dst"
  say "${G}  [ok] agent installed: $agent${N}"
done

# ---------------------------------------------------------- 5. global CLAUDE.md
CLAUDE_MD="$CLAUDE_DIR/CLAUDE.md"
if [ -f "$CLAUDE_MD" ] && grep -q "sap-kb" "$CLAUDE_MD"; then
  say "${Y}  [--] CLAUDE.md already mentions sap-kb - left untouched.${N}"
  say "${Y}       If its KB path is wrong, edit it to: $KB_ROOT${N}"
else
  [ -f "$CLAUDE_MD" ] && cp -f "$CLAUDE_MD" "$CLAUDE_MD.bak-$STAMP"
  cat >> "$CLAUDE_MD" <<EOF

## SAP / ABAP knowledge base (use FIRST)
For ANY SAP, ABAP, S/4HANA, SAP BTP, RAP, CDS, Fiori, OData, BOPF, IDoc/RFC, or SAP-config
question - before answering from memory or searching the web - invoke the \`sap-kb\` skill
and answer from the local knowledge base at \`$KB_ROOT\`
(master list: \`INDEX.json\`). This applies to subagents too.

- Answer only from a read page/source; **cite** every SAP claim (\`<topic>/reference.json\` + page).
- Never invent SAP facts. If the KB lacks the answer, say so, then follow the skill's fallback
  ladder: local \`sap-docs\` MCP if installed (\`[sap-docs: ...]\`) -> live help.sap.com
  (\`[sap-help: URL]\`) -> Community (\`[community - unverified]\`) -> web
  (\`[web - unverified against official PDF]\`). Keep customer/system specifics out of queries.
- To add a topic that has no PDF, use the \`sap-crawl\` skill (finds + fetches help.sap.com pages
  over HTTP, incl. the ABAP Keyword Documentation).
EOF
  say "${G}  [ok] global rule appended to ~/.claude/CLAUDE.md${N}"
fi

# --------------------------------------------------- 6. build the empty index
if "$PY" "$KB_ROOT/_tools/build_index.py" "$KB_ROOT" >/dev/null; then
  say "${G}  [ok] empty INDEX.json / INDEX.md generated${N}"
else
  say "${Y}  [!!] build_index.py failed - check it manually${N}"
fi

say ""
say "${C}Done.${N}"
say ""
say "${C}Next steps:${N}"
say "  1. Open a NEW Claude Code session (skills/agents register at session start)."
say "  2. Verify:  /sap-kb  what SAP topics are in the KB?   -> should say the KB is empty."
say "  3. Smoke-test the pipeline end to end (no SAP PDF needed):"
say "       mkdir -p \"$KB_ROOT/test-topic\""
say "       $PY \"$KB_ROOT/_tools/make_test_pdf.py\" \"$KB_ROOT/test-topic\""
say "     then in Claude Code:  Ingest the test-topic folder into the SAP KB."
say "     Delete the folder afterwards and re-run build_index.py."
say "  4. Add real knowledge:"
say "     - PDF   : export a help.sap.com guide, drop it in $KB_ROOT/<topic>/, say"
say "               \"Ingest the <topic> folder into the SAP KB.\""
say "     - Crawl : /sap-crawl add 'RAP side effects' to the KB."
say ""
