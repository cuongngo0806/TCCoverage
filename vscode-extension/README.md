# TC Coverage — VS Code extension

Front-end for `tcadvisor` (in the parent repo). Shows which test cases a C++/CMake change must be
checked against, with the impact flow graph.

## Setup

1. `pip install -e <TCCoverage repo>` (needs Python ≥ 3.11; installs the libclang wheel).
2. Configure the analysed project once with `CMAKE_EXPORT_COMPILE_COMMANDS=ON` and a CMake File API query
   (`<build>/.cmake/api/v1/query/codemodel-v2`).
3. **TC Coverage: Set Up Repository** writes `<repo>/.tcadvisor/config.json` (impact source, report language,
   build dir, output dir, targets, depth) and optionally the GitHub Copilot prompts `/tc-coverage` and
   `/tc-verify`. The CLI, this extension and AI chat all read that file; a `tcCoverage.*` setting left empty
   defers to it. `tcCoverage.pythonPath` (empty = `python` on Windows, `python3` elsewhere) is per machine.

## Use

- Command palette → **TC Coverage: Analyze Working Tree Changes** / **Analyze Last Commit** / **Analyze Commit Range…**
- Right-click a function → **TC Coverage: Analyze Symbol at Cursor**
- Explorer → **TC Coverage** view: cases by priority, evidence (click to jump), uncertain items, targets.
- **TC Coverage: Show Report** opens the interactive impact flow; click `file:line` links to open code.
- P1/P2 cases also appear as inline hints on their evidence lines (toggle `tcCoverage.showInlineHints`).

## Build / package

```bash
npm install && npm run compile          # F5 in VS Code to run the Extension Development Host
npx @vscode/vsce package                # produces tc-coverage-<version>.vsix
```
