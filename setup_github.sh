#!/usr/bin/env bash
# ==============================================================================
# setup_github.sh - Initialize bpmn-2 on GitHub with Issues, Milestones & Labels
# ==============================================================================
set -euo pipefail

REPO_NAME="${1:-bpmn-2}"
VISIBILITY="${2:-public}"

echo "==> Checking GitHub CLI authentication..."
if ! command -v gh &> /dev/null; then
    echo "Error: GitHub CLI (gh) is not installed. Please install it first."
    exit 1
fi

if ! gh auth status &> /dev/null; then
    echo "Error: gh is not authenticated. Please run 'gh auth login' first."
    exit 1
fi

echo "==> Creating GitHub repository: ${REPO_NAME} (${VISIBILITY})..."
if ! gh repo view "${REPO_NAME}" &> /dev/null; then
    gh repo create "${REPO_NAME}" --"${VISIBILITY}" --source=. --remote=origin --description="Enterprise BPMN 2.0.2 Process Modelling, Layout & Conformance Engine"
    echo "Repository created successfully."
else
    echo "Repository ${REPO_NAME} already exists. Linking remote..."
    git remote add origin "$(gh repo view "${REPO_NAME}" --json url -q .url).git" 2>/dev/null || true
fi

echo "==> Initializing git and pushing main branch..."
git init -b main 2>/dev/null || git checkout -b main 2>/dev/null || true
git add .
git commit -m "Initial commit: bpmn-2 v1.0.0 complete portable engine & documentation" || true
git push -u origin main

echo "==> Configuring Issue Labels..."
gh label create "conformance" --color "0e8a16" --description "BPMN 2.0.2 OMG specification compliance" --force
gh label create "layout" --color "1d76db" --description "Diagram Interchange (DI) & routing issues" --force
gh label create "soundness" --color "d93f0b" --description "Token-game reachability and deadlock detection" --force
gh label create "mcp" --color "5319e7" --description "Model Context Protocol & LLM tooling" --force
gh label create "extensions" --color "fbca04" --description "APQC, Lean Six Sigma, ArchiMate integrations" --force

echo "==> Creating Milestones..."
MILESTONE_1_URL=$(gh api repos/:owner/:repo/milestones -f title="v1.1.0 - Tooling, MCP & Interop" -f description="MCP wrapper, APQC tooling, and enhanced edge routing" --jq .url 2>/dev/null || echo "")
MILESTONE_2_URL=$(gh api repos/:owner/:repo/milestones -f title="v1.2.0 - Process Mining & Multi-notation" -f description="IEEE XES ingestion and ArchiMate 3.2 exchange export" --jq .url 2>/dev/null || echo "")

echo "==> Populating GitHub Issues Backlog..."

gh issue create \
  --title "Model Context Protocol (MCP) stdio server implementation" \
  --label "mcp,enhancement" \
  --body "Implement a native MCP (Model Context Protocol) server for \`bpmn-2\` to allow seamless stdio/SSE tool execution in Claude Desktop, OpenClaw, TrueForge, and Gemini agent harnesses.

### Requirements:
- Surface \`bpmn_render\`, \`bpmn_validate\`, \`bpmn_normalize\`, and \`bpmn_info\` as MCP tools.
- Support file-path inputs and inline XML strings.
- Return structured tool outputs and image blobs directly to the host client."

gh issue create \
  --title "Enhance orthogonal edge routing for non-adjacent cross-pool message flows" \
  --label "layout,bug" \
  --body "When multiple collaboration pools are stacked vertically, message flows between non-adjacent pools (e.g. Pool 1 directly to Pool 3) can cut across intermediate pools.

### Tasks:
- Implement pool obstacle bounding box avoidance in \`layout.py\`.
- Route vertical segments around the right-hand or left-hand outer channel of intermediate pools."

gh issue create \
  --title "APQC PCF v7.4 automated validation and sidecar generator" \
  --label "extensions,enhancement" \
  --body "Provide an automated validation rule in \`scripts/validate_bpmn.py\` and CLI flag (\`--apqc\`) that verifies element IDs recorded in \`<documentation>\` against standard APQC PCF hierarchical schemas.

### Deliverables:
- Offline cache of APQC PCF hierarchy in JSON.
- Verification that \`PCF X.Y.Z\` references exist."

gh issue create \
  --title "Direct ingestion and mapping of IEEE XES event streams" \
  --label "extensions,enhancement" \
  --body "Add support in \`scripts/ingest.py\` for standard \`.xes\` process mining logs, automatically extracting the dominant execution variant and generating an Analytic-level BPMN 2.0 XML baseline."

gh issue create \
  --title "ArchiMate 3.2 Open Exchange XML export" \
  --label "extensions,enhancement" \
  --body "Generate valid ArchiMate 3.2 XML from collaboration diagrams:
- Pools -> Business Actors / Roles
- Tasks -> Business Processes / Services
- Message flows -> Business Interactions / Triggering relations."

echo "==> Setup complete! Visit your repository on GitHub."
