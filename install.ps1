<#
  sap-kb toolkit installer (Windows / PowerShell)

  Usage:
      .\install.ps1                              # KB root -> %USERPROFILE%\mcp-servers\sap-kb
      .\install.ps1 -KbRoot "D:\sap\kb"          # custom KB root

  Installs: 2 skills, 2 agents, the _tools pipeline, an empty KB with a valid index,
  and appends the "use sap-kb first" rule to your global ~/.claude/CLAUDE.md.
  Re-running is safe: it backs up anything it would overwrite.
#>
[CmdletBinding()]
param(
    [string]$KbRoot = (Join-Path $env:USERPROFILE "mcp-servers\sap-kb")
)

$ErrorActionPreference = "Stop"
$src       = $PSScriptRoot
$claudeDir = Join-Path $env:USERPROFILE ".claude"
$stamp     = Get-Date -Format "yyyyMMdd-HHmmss"

function Say($msg, $color = "Gray") { Write-Host $msg -ForegroundColor $color }

# Windows PowerShell 5.1's -Encoding utf8 emits a BOM. A BOM before a SKILL.md's
# '---' frontmatter can stop the skill registering, so write UTF-8 without one.
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
function Write-Utf8NoBom($path, $text) {
    [System.IO.File]::WriteAllText($path, $text, $utf8NoBom)
}
function Append-Utf8NoBom($path, $text) {
    $existing = if (Test-Path $path) { [System.IO.File]::ReadAllText($path) } else { "" }
    [System.IO.File]::WriteAllText($path, $existing + $text, $utf8NoBom)
}

Say ""
Say "sap-kb toolkit installer" Cyan
Say "  KB root      : $KbRoot"
Say "  Claude config: $claudeDir"
Say ""

# ---------------------------------------------------------------- 1. prereqs
$pythonExe = $null
foreach ($cand in @("python", "py")) {
    $cmd = Get-Command $cand -ErrorAction SilentlyContinue
    if ($cmd) { $pythonExe = $cand; break }
}
if (-not $pythonExe) {
    Say "ERROR: Python not found on PATH. Install Python 3.9+ from python.org, then re-run." Red
    exit 1
}
$pyVer = & $pythonExe --version 2>&1
Say "  [ok] Python found: $pyVer" Green

& $pythonExe -c "import fitz" 2>$null
if ($LASTEXITCODE -ne 0) {
    Say "  [..] PyMuPDF (fitz) missing - installing via pip..." Yellow
    & $pythonExe -m pip install --quiet pymupdf
    if ($LASTEXITCODE -ne 0) {
        Say "ERROR: 'pip install pymupdf' failed. Install it manually, then re-run." Red
        exit 1
    }
}
Say "  [ok] PyMuPDF available" Green

# ------------------------------------------------------------- 2. KB + tools
New-Item -ItemType Directory -Force -Path $KbRoot | Out-Null
$toolsDst = Join-Path $KbRoot "_tools"
New-Item -ItemType Directory -Force -Path $toolsDst | Out-Null
Copy-Item (Join-Path $src "kb\_tools\*") $toolsDst -Force
Say "  [ok] _tools installed -> $toolsDst" Green

# ------------------------------------------ 3. skills (KB root substituted in)
foreach ($skill in @("sap-kb", "sap-crawl")) {
    $dstDir = Join-Path $claudeDir "skills\$skill"
    New-Item -ItemType Directory -Force -Path $dstDir | Out-Null
    $dst = Join-Path $dstDir "SKILL.md"
    if (Test-Path $dst) {
        Copy-Item $dst "$dst.bak-$stamp" -Force
        Say "  [..] existing $skill/SKILL.md backed up to SKILL.md.bak-$stamp" Yellow
    }
    $text = Get-Content (Join-Path $src "skills\$skill\SKILL.md") -Raw
    $text = $text.Replace("{{SAP_KB_ROOT}}", $KbRoot)
    Write-Utf8NoBom $dst $text
    Say "  [ok] skill installed: $skill" Green
}

# ------------------------------------------------------------------ 4. agents
$agentsDst = Join-Path $claudeDir "agents"
New-Item -ItemType Directory -Force -Path $agentsDst | Out-Null
foreach ($agent in @("sap-text-reader.md", "sap-image-reader.md")) {
    $dst = Join-Path $agentsDst $agent
    if (Test-Path $dst) { Copy-Item $dst "$dst.bak-$stamp" -Force }
    Copy-Item (Join-Path $src "agents\$agent") $dst -Force
    Say "  [ok] agent installed: $agent" Green
}

# ------------------------------------------------------- 5. global CLAUDE.md
$claudeMd = Join-Path $claudeDir "CLAUDE.md"
$rule = @"

## SAP / ABAP knowledge base (use FIRST)
For ANY SAP, ABAP, S/4HANA, SAP BTP, RAP, CDS, Fiori, OData, BOPF, IDoc/RFC, or SAP-config
question - before answering from memory or searching the web - invoke the ``sap-kb`` skill
and answer from the local knowledge base at ``$KbRoot``
(master list: ``INDEX.json``). This applies to subagents too.

- Answer only from a read page/source; **cite** every SAP claim (``<topic>/reference.json`` + page).
- Never invent SAP facts. If the KB lacks the answer, say so, then follow the skill's fallback
  ladder: local ``sap-docs`` MCP if installed (``[sap-docs: ...]``) -> live help.sap.com
  (``[sap-help: URL]``) -> Community (``[community - unverified]``) -> web
  (``[web - unverified against official PDF]``). Keep customer/system specifics out of queries.
- To add a topic that has no PDF, use the ``sap-crawl`` skill (finds + fetches help.sap.com pages
  over HTTP, incl. the ABAP Keyword Documentation).
"@

if ((Test-Path $claudeMd) -and (Select-String -Path $claudeMd -Pattern "sap-kb" -Quiet)) {
    Say "  [--] CLAUDE.md already mentions sap-kb - left untouched." Yellow
    Say "       If its KB path is wrong, edit it to: $KbRoot" Yellow
} else {
    if (Test-Path $claudeMd) { Copy-Item $claudeMd "$claudeMd.bak-$stamp" -Force }
    Append-Utf8NoBom $claudeMd $rule
    Say "  [ok] global rule appended to ~/.claude/CLAUDE.md" Green
}

# ------------------------------------------------- 6. build the empty index
& $pythonExe (Join-Path $toolsDst "build_index.py") $KbRoot | Out-Null
if ($LASTEXITCODE -eq 0) { Say "  [ok] empty INDEX.json / INDEX.md generated" Green }
else { Say "  [!!] build_index.py returned $LASTEXITCODE - check it manually" Yellow }

Say ""
Say "Done." Cyan
Say ""
Say "Next steps:" Cyan
Say "  1. Open a NEW Claude Code session (skills/agents register at session start)."
Say "  2. Verify:  /sap-kb  what SAP topics are in the KB?   -> should say the KB is empty."
Say "  3. Smoke-test the pipeline end to end (no SAP PDF needed):"
Say "       mkdir `"$KbRoot\test-topic`""
Say "       $pythonExe `"$toolsDst\make_test_pdf.py`" `"$KbRoot\test-topic`""
Say "     then in Claude Code:  Ingest the test-topic folder into the SAP KB."
Say "     Delete the folder afterwards and re-run build_index.py."
Say "  4. Add real knowledge:"
Say "     - PDF   : export a help.sap.com guide, drop it in $KbRoot\<topic>\, say"
Say "               `"Ingest the <topic> folder into the SAP KB.`""
Say "     - Crawl : /sap-crawl add 'RAP side effects' to the KB."
Say ""
