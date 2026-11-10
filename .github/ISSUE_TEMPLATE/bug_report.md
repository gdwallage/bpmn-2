---
name: Bug report
about: Create a report to help reproduce and fix a validator or rendering flaw
title: "[BUG] "
labels: bug
assignees: ''
---

**Describe the bug**
A clear and concise description of what went wrong during normalization, validation, or rendering.

**Reproduction Steps**
1. Command run: `python scripts/bpmn.py render ...`
2. Input BPMN XML or source snippet:
```xml
<!-- paste minimal XML here -->
```
3. Error message / traceback:

**Expected behavior**
What you expected to happen per OMG BPMN 2.0.2 specification.

**Environment:**
- OS: [e.g. Ubuntu 24.04, WSL2, macOS]
- Python version: [e.g. 3.11]
- CairoSVG / libxml version:
