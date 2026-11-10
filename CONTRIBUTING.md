# Contributing to bpmn-2

Thank you for contributing to `bpmn-2`! We welcome bug fixes, conformance enhancements, and framework extensions.

## Architecture Guidelines

1. **OMG Conformance First**: All changes to semantic XML representation or Diagram Interchange MUST strictly follow OMG BPMN 2.0.2 (`formal/2013-12-09`).
2. **Deterministic Behavior**: Layout calculations and normalization must produce deterministic, idempotent output.
3. **No External Network Calls**: Validation and parsing MUST run completely offline using local XSD schemas in `assets/xsd/`.
4. **Platform Neutrality**: Scripts must never assume vendor-specific sandbox paths or hardcoded toolchains.

## Development Workflow

1. Fork and clone the repository.
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Run test suite and reference validations:
   ```bash
   for f in assets/templates/*.bpmn; do
     python scripts/bpmn.py validate "$f" --soundness
   done
   ```
4. Submit a Pull Request targeting `main`. Ensure all CI checks pass.
