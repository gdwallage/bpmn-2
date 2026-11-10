# bpmn-2: Enterprise BPMN 2.0.2 Process Modelling & Validation Engine

A portable, platform-agnostic BPMN 2.0.2 engineering skill, CLI suite, and API specification designed for automated process discovery, formal schema validation, Diagram Interchange (DI) layout generation, and multi-format rendering (SVG, PNG, XML).

Fully compatible with Google Gemini, Anthropic Claude, OpenAI, and local LLM harnesses (OpenClaw, TrueForge, LiteLLM).

[![CI Conformance](https://github.com/garywallage/bpmn-2/actions/workflows/ci.yml/badge.svg)](https://github.com/garywallage/bpmn-2/actions/workflows/ci.yml)
[![BPMN Specification](https://img.shields.io/badge/OMG%20Spec-BPMN%202.0.2-blue.svg)](http://www.omg.org/spec/BPMN/20100524/MODEL)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

---

## Key Capabilities

* **Authoritative OMG XSD Validation**: Validates directly against official `BPMN20.xsd`, `Semantic.xsd`, `BPMNDI.xsd`, `DC.xsd`, and `DI.xsd`.
* **Structural Rule Verification**: 30+ syntactic and structural verification gates mapped to clauses of OMG `formal/2013-12-09`.
* **Soundness & Token-Game Engine**: Evaluates up to 20,000 states per process level to detect potential deadlocks (`P001`) and lack of synchronization (`P002`).
* **Automated Orthogonal Layout**: Generates standards-compliant Diagram Interchange bounds, waypoints, and participant bands without human intervention.
* **Deterministic Normalizer**: Fixes child element sequences into strict XSD sequence order prior to verification.
* **Cross-Framework Extensions**: Native reference models for APQC PCF, Lean Six Sigma TIMWOODS waste mapping, and ArchiMate 3.x business layer alignment.

---

## Repository Structure

```text
├── assets/
│   ├── templates/          # Standard reference BPMN 2.0 XML models
│   └── xsd/                # Official OMG schema definition files
├── references/             # Comprehensive technical architecture & rule guides
│   ├── authoring-guide.md
│   ├── conformance-and-levels.md
│   ├── convert-and-correct.md
│   ├── hierarchy-and-levels.md
│   ├── notation-catalogue.md
│   ├── source-analysis.md
│   ├── structural-rules.md
│   └── extensions/         # APQC, Lean Six Sigma, ArchiMate specifications
├── scripts/                # Standalone Python CLI & validation suite
│   ├── bpmn.py             # Master CLI (render, validate, normalize, info, extract)
│   ├── bpmnlib.py          # Core taxonomy, metamodel definitions, and XPath helpers
│   ├── didi.py             # Diagram Interchange (DI) serialization
│   ├── draw.py             # Vector SVG rendering implementing Cl. 7.3 depiction
│   ├── ingest.py           # Multi-source document and image normalizer
│   ├── layout.py           # Graph ranking, row assignment, & orthogonal router
│   ├── normalize.py        # Schema reordering & automatic repair engine
│   ├── textutil.py         # Font metrics and greedy word wrapping
│   └── validate_bpmn.py    # Multi-level conformance & token-game analyzer
├── .github/
│   ├── workflows/ci.yml    # Automated GitHub Actions test pipeline
│   └── ISSUE_TEMPLATE/     # Standard bug and feature issue templates
├── BACKLOG.md              # Detailed sprint backlog & technical backlog
├── CONTRIBUTING.md         # Architecture standards & PR guidelines
├── requirements.txt        # Runtime and test dependencies
├── SKILL.md                # System prompt / skill manifest for AI agents
├── tools.json              # OpenAPI tool schemas for function calling
└── ROADMAP.md              # Strategic product roadmap & milestone tracking
```

---

## Installation & Setup

### Prerequisites
Requires Python 3.10+ and system Cairo libraries for raster PNG export:

```bash
# Ubuntu / Debian
sudo apt-get update && sudo apt-get install -y libcairo2-dev libxml2-dev libxslt1-dev fonts-liberation

# macOS (Homebrew)
brew install cairo pango
```

### Python Environment
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

---

## CLI Usage

### 1. Validate a BPMN XML File
```bash
python scripts/bpmn.py validate path/to/model.bpmn --soundness --level analytic
```

### 2. Render to SVG, PNG, and DI-Complete BPMN
```bash
python scripts/bpmn.py render path/to/model.bpmn -o output/diagram --formats png,svg,bpmn --soundness
```

### 3. Normalise Child Element Sequence
```bash
python scripts/bpmn.py normalize raw_model.bpmn -o clean_model.bpmn
```

### 4. Extract Embedded BPMN from PNG / SVG Metadata
```bash
python scripts/bpmn.py extract output/diagram.png -o recovered.bpmn
```

---

## AI Agent Integration

### Google Gemini / OpenAI / LiteLLM Function Calling
Use the tool definitions in `tools.json`. They map directly to `bpmn_render`, `bpmn_validate`, `bpmn_normalize`, and `bpmn_info`.

### System Prompt Configuration
Import `SKILL.md` into your agent runtime instructions (OpenClaw, TrueForge, Gemini System Instructions).
