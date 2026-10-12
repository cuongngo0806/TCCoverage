# Feature Specification: Linux-first, Yocto/autotools modules, build-variant profile, per-run reports, inline image evidence

**Feature Branch**: `claude/project-improvements-post-test-saoygs`

**Created**: 2026-10-12

**Status**: Draft

**Input**: User description (field-test feedback, translated): "(1) reports must be created inside the workspace of
the project being analysed, and every report must be different so nothing is overwritten; (2) the first target of
the tool is now Linux — update the install and usage guides for Linux; (3) our modules are built with Yocto and
mostly use Makefile.am and configure.ac, so the usage must be updated for that; (4) each module can be built for
different variants / types, so on the first run confirm the build flow with the user and save it in the config to
filter out cases on branches that are not built and reduce noise; (5) evidence attachments in the report: allow
pasting/copying images in and show the images directly in the report."

## Context (what exists today)

- Reports go to one fixed folder **outside** the analysed repository (`<repo>/../tcadvisor-report/<repo-name>`); a
  new run overwrites the previous `report.*` (only a *filled* `report.html` is backed up first).
- The build model comes from CMake only (CMake File API targets + `compile_commands.json`); install/usage docs
  assume a CMake project and are platform-neutral, with PowerShell helpers kept for Windows/Copilot.
- `.tcadvisor/config.json` has no notion of build variants: every `#if` branch and every source file is treated as
  built.
- The fillable report accepts evidence by drag-and-drop or file picker and shows a small thumbnail; there is no
  paste-from-clipboard and no full-size view.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Each run leaves its own report inside the project workspace (Priority: P1)

A developer analyses a change in module `remotecontrolapp`. The report appears in a folder inside that module's
workspace, named so the developer can tell which run (time, change analysed) it belongs to. Running again on the
next commit creates a second folder; the first one is untouched, including any results a tester already filled in.

**Why this priority**: In the field test, reports landed outside the workspace (hard to find, not next to the code
in the IDE) and later runs replaced earlier ones, losing the trail of what was checked for which change.

**Independent Test**: Run the analysis twice on the same workspace (same change, then another change); two
distinct report folders exist inside the workspace, both complete, neither modified by the other run, and the
version-control status of the module shows no new untracked files.

**Acceptance Scenarios**:

1. **Given** a workspace with no previous report, **When** the developer runs an analysis, **Then** the report is
   written to a new run folder under the workspace's tool folder, and the CLI / chat output prints that folder.
2. **Given** a previous run folder exists, **When** a second analysis runs (even on the same change, in the same
   second), **Then** a different run folder is created and no file of the earlier folder is changed.
3. **Given** several run folders, **When** the developer wants the newest one, **Then** a stable "latest" pointer
   (or the CLI) names it without searching.
4. **Given** a filled report from an earlier run, **When** the developer starts a new analysis with that report as
   the previous one, **Then** results carry over into the new run folder exactly as today (by case key).
5. **Given** the workspace is a git repository, **When** reports are created, **Then** they do not appear as
   untracked changes of the module (they are ignored locally without editing tracked files).

---

### User Story 2 - Analyse a Yocto-built autotools module (Priority: P1)

A developer whose module is built by a Yocto recipe from `configure.ac` + `Makefile.am` (no CMake) runs the tool
on a change. The tool understands which programs / libraries the module builds and from which sources, and which
compile flags and defines apply, and produces the same kind of case list it produces for CMake projects.

**Why this priority**: Most of the user's modules are autotools + Yocto; without this the tool either cannot run
or runs with "reduced accuracy" and maps no case to a build target.

**Independent Test**: On a sample autotools module (with a `configure.ac`, a top-level and a sub-directory
`Makefile.am`, one program and one library), change a function in the library; the report maps the impacted
callers to the program and library that contain them, using the module's real compile flags.

**Acceptance Scenarios**:

1. **Given** an autotools module that has been built at least once (in the Yocto build or locally), **When** the
   developer runs the analysis, **Then** the build products (programs, libraries) and their sources are taken
   from the module's own build description and the cases name those build products, just as CMake targets are
   named today.
2. **Given** the module's compile flags are not available yet, **When** the analysis runs, **Then** the tool says
   exactly which one command to run to produce them for this build flow and continues in reduced-accuracy mode
   with an uncertainty flag (never a silent guess).
3. **Given** a CMake project, **When** the analysis runs, **Then** behaviour and results are unchanged.
4. **Given** a source file that no build product lists, **When** it changes, **Then** it is reported as not built
   by any product (out of scope with a reason), not silently dropped.

---

### User Story 3 - Confirm the build flow once, then filter out branches that are not built (Priority: P2)

On the first run in a workspace, the tool detects the build flow (build system, the variants it can see: e.g.
machines / product types, enabled or disabled features and configure switches) and shows the developer what it
found. The developer confirms or corrects which variant(s) they actually ship / test. The answer is saved in the
workspace config. From then on, cases that only concern code not compiled in any confirmed variant (a conditional
source not built, an `#if` branch whose condition is false in every confirmed variant) are moved out of the main
list, with the reason, so the list holds only code that is really built.

**Why this priority**: Modules are built for several variants; cases on branches that are never built for the
team's products were the second biggest source of noise after unit-test cases. Depends on Story 2 for autotools
modules, but also applies to CMake projects.

**Independent Test**: In a module with a feature switch `FEATURE_X` (on in variant A, off in variant B) and code
under `#ifdef FEATURE_X`, confirm only variant B; a change inside that `#ifdef` yields no case in the main report
and one entry in the "not built in the confirmed variants" section naming the switch; confirming A and B brings
the case back.

**Acceptance Scenarios**:

1. **Given** a workspace without a saved build profile, **When** the developer runs the analysis from the CLI in an
   interactive terminal or through the AI chat, **Then** the detected build flow and variants are shown and the
   developer is asked to confirm / pick before the analysis continues; the answer is saved in the workspace config.
2. **Given** a non-interactive run (CI, script) without a saved profile, **When** the analysis runs, **Then** it does
   not block: it assumes every detected variant is built (no filtering), says so in the run notes, and tells how
   to save a profile.
3. **Given** a saved profile with several variants, **When** a case concerns code built in at least one of them,
   **Then** the case stays in the main list (filtering uses the union of the confirmed variants).
4. **Given** a case filtered by the profile, **When** the report is opened, **Then** it is listed in a separate
   "not built in the confirmed variants" section with the variant condition that excludes it, and it is still in
   the machine-readable report.
5. **Given** a condition the tool cannot evaluate for a variant (value computed at build time, unknown macro),
   **When** a case depends on it, **Then** the case is kept and flagged uncertain, never filtered.
6. **Given** a saved profile, **When** the developer wants to change it, **Then** one command (or asking the AI
   chat) re-runs the confirmation and updates the config; a command-line override can pick variants for one run.

---

### User Story 4 - Linux-first installation and usage guide (Priority: P2)

A developer on a Linux build host (the same machine / container where the Yocto build runs) follows one guide to
install the tool and its prerequisites, prepare a module (CMake or autotools, inside or outside Yocto), configure
the workspace, run an analysis and open the report — every command shown is a Linux shell command.

**Why this priority**: Linux is now the primary platform; the current guide mixes platforms and assumes CMake.

**Independent Test**: A developer who has never used the tool follows only the guide on a fresh Linux machine with
an autotools module and gets a report without asking for help.

**Acceptance Scenarios**:

1. **Given** a fresh Linux host, **When** the developer follows the install section, **Then** the listed system
   packages and the install command are enough to run the tool (Linux package names, Python environment, no
   Windows-only step).
2. **Given** a Yocto-built module, **When** the developer follows the Yocto section, **Then** they know how to get
   the module's sources and its compile information out of the Yocto build (or a local build), where the tool keeps
   its config and reports in the workspace, and how to set the build profile.
3. **Given** a Windows or macOS user, **When** they read the guide, **Then** a short note says what is supported
   there on a best-effort basis; Windows-only helpers are no longer the default path.

---

### User Story 5 - Paste screenshots as evidence and see them in the report (Priority: P3)

A tester filling in the report takes a screenshot of the device / log viewer and pastes it (clipboard) directly
into a case's evidence area. The image appears at a readable size inside the case; clicking it shows it full size.
After saving, anyone who opens the saved report sees the images inline, also in the printed / PDF version.

**Why this priority**: Attaching evidence by saving a screenshot to a file and then picking it was slow; small
thumbnails were not enough to review the evidence.

**Independent Test**: Open a report, paste an image from the clipboard into one case, save; reopen the saved file
offline: the image is shown inline in that case, full-size view works, the printed version contains it.

**Acceptance Scenarios**:

1. **Given** an image on the clipboard, **When** the tester pastes while a case's evidence area is focused,
   **Then** the image is attached to that case (with a generated name) and shown inline.
2. **Given** several images, **When** they are pasted or dropped, **Then** each is shown inline in the order added
   and can be removed or downloaded individually.
3. **Given** a saved report with images, **When** it is reopened on another machine without network, **Then** the
   images still show (the report stays a single self-contained file).
4. **Given** a non-image file (log), **When** it is attached, **Then** it behaves as today (name, size, download).
5. **Given** a pasted item that is not an image or a file (plain text), **When** pasted into the evidence area,
   **Then** it is not turned into an attachment (it may go to the comment field).

### Edge Cases

- Two analyses start at the same moment in the same workspace: run folders must still be distinct.
- The workspace is read-only or the tool folder cannot be created: the run fails with a clear message naming the
  folder and the `output_dir` override; it does not fall back to writing elsewhere silently.
- An explicit `output_dir` is configured (old behaviour): it is honoured, still with one sub-folder per run.
- Disk growth from many run folders: the guide documents how to clean them; the tool never deletes reports on its own.
- Yocto build directory not on this machine (only the module source is available): analysis runs in
  reduced-accuracy mode with a flag and the guide's command to obtain compile information.
- `configure.ac` / `Makefile.am` uses constructs the tool cannot read statically (generated `Makefile.am`,
  `include`d fragments, `m4` macros from layers): the affected products / sources are flagged uncertain.
- The module is built in an out-of-tree build directory (`B != S` in Yocto): paths must map back to the workspace.
- A variant switch toggles a whole sub-directory (`SUBDIRS` under a conditional): all its sources follow the switch.
- A change edits the build files themselves (`configure.ac`, `Makefile.am`, recipe-level options): the change is
  reported as a build-configuration change, and the saved profile is shown as possibly stale.
- Pasted image is very large: the existing size warning applies; the report stays usable.
- Saved profile names a variant that no longer exists: the run warns and asks (interactive) or ignores it (batch).

## Requirements *(mandatory)*

### Functional Requirements

**Report location and naming**

- **FR-001**: By default the tool MUST write reports into the analysed project's workspace, under the tool's own
  folder in that workspace (the same place as its config), not outside it.
- **FR-002**: Every analysis MUST create a new run folder whose name is unique and human-readable (date-time and the
  analysed change, e.g. the short commit / range or `working-tree`); an existing run folder MUST never be modified
  or overwritten by a later run.
- **FR-003**: The tool MUST expose the newest run folder by a stable pointer and print the run folder path at the
  end of every run (CLI, brief, AI front-ends).
- **FR-004**: Report folders MUST be ignored by the workspace's version control without editing tracked files
  (local ignore), so they never show up as module changes.
- **FR-005**: A configured `output_dir` MUST still be honoured (relative to the workspace), with one run folder per
  analysis inside it; the current rule that the report folder must lie outside the repository is removed.
- **FR-006**: Carrying test results from a previous filled report MUST keep working across run folders.

**Linux-first documentation**

- **FR-007**: The README and usage docs MUST present Linux as the primary platform: Linux system prerequisites,
  install in a Python virtual environment, shell commands only in the main path; other platforms in a short
  best-effort note.
- **FR-008**: The docs MUST contain a Yocto + autotools guide covering: where the module source lives
  (`devtool modify` / external source / plain checkout), how to obtain its compile information from a Yocto build
  or a local build, running the analysis, the build-profile confirmation, and where reports are written.
- **FR-009**: The AI front-ends installed by `tcadvisor init` (skill, agents, prompts) MUST describe the Linux /
  autotools flow and the build-profile confirmation consistently with the docs.

**Autotools / Yocto build model**

- **FR-010**: The tool MUST support autotools modules (`configure.ac` + `Makefile.am`) as a first-class build system
  alongside CMake, detected automatically from the workspace, with an explicit config / flag override.
- **FR-011**: For autotools modules the tool MUST derive build products (programs, libraries) and the sources of
  each from the module's own build description, and use them wherever CMake targets are used today (case target
  names, target filtering via `targets`).
- **FR-012**: The tool MUST use a deterministic compile database for autotools modules when one is available
  (compile flags, include paths, defines per source) and MUST state how to produce it for a Yocto build and for a
  local build when it is missing; without it the run continues in reduced-accuracy mode with an uncertainty flag.
- **FR-013**: Build-description constructs the tool cannot resolve statically MUST become uncertainty flags naming
  the file and construct; they MUST never be silently ignored.
- **FR-014**: CMake projects MUST keep today's behaviour and results (no regression on the existing benchmarks).

**Build-variant profile**

- **FR-015**: The tool MUST detect the build flow and the variant dimensions visible in the workspace (build
  system, conditional switches in the build description, configure options / feature switches, and any variant
  list the user declares) and present them for confirmation on the first run.
- **FR-016**: The confirmed build profile (build system, build directory / compile-database location, the selected
  variants and the switch values of each) MUST be saved in the workspace config and reused by every front-end (CLI,
  Claude Code, Copilot).
- **FR-017**: Confirmation MUST happen interactively in a terminal session and through the AI chat front-ends; a
  non-interactive run without a profile MUST NOT block and MUST NOT filter, and MUST say so in the run notes.
- **FR-018**: With a saved profile, a case whose evidence lies only in code not compiled in any selected variant
  (sources excluded by a build condition, preprocessor branches inactive in every selected variant) MUST be moved
  out of the main case list into a "not built in the confirmed variants" section that names the excluding
  condition; it MUST stay in the machine-readable report.
- **FR-019**: When the tool cannot evaluate a condition for a variant, the case MUST stay in the main list with an
  uncertainty flag (filtering only removes what is provably not built).
- **FR-020**: Users MUST be able to re-run the confirmation, edit the profile, and override the selected variants
  for a single run from the command line.
- **FR-021**: A change to the build description itself MUST be reported as a build-configuration change and MUST
  mark the saved profile as possibly stale in the report.

**Image evidence in the report**

- **FR-022**: The fillable report MUST accept images pasted from the clipboard into a case's evidence area, in
  addition to drag-and-drop and the file picker.
- **FR-023**: Image attachments MUST be shown inline at a readable size within the case, with a full-size view on
  click, and MUST appear in the printed / PDF version.
- **FR-024**: The saved report MUST remain a single self-contained file that shows the images offline; existing
  rules (size warning, a failed case needs an attachment or a defect reference, integrity hash) MUST apply to
  pasted images too.
- **FR-025**: All new report sentences (sections, prompts, notes) MUST exist in both report languages.

### Key Entities

- **Run folder**: one analysis' output (reports, AI verification files, notes); identified by time and the analysed
  change; immutable after the run.
- **Build profile**: the confirmed build flow of a workspace — build system, where compile information comes from,
  the selected variants; saved in the workspace config; has a "possibly stale" state.
- **Variant**: one buildable configuration of the module (e.g. a product type / machine) with values for each
  build switch it sets.
- **Build switch**: a condition that decides whether code is built — a build-description conditional, a configure
  option / feature, or a preprocessor macro.
- **Build product**: a program or library the module builds, with its source list; the autotools counterpart of a
  CMake target.
- **Evidence attachment**: a file or image attached to a case result, embedded in the report with name, type, size
  and hash.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 10 consecutive analyses of the same workspace produce 10 distinct, complete run folders inside the
  workspace; 0 files of earlier runs change; the module's version-control status shows 0 new entries.
- **SC-002**: On the pilot autotools module, at least 90% of impacted callers in the report name the build product
  that contains them (today: none for autotools modules).
- **SC-003**: On a module with at least two variants and a profile selecting one, cases on code not built in that
  variant drop out of the main list (target: at least 80% of such cases), while 0 cases on code that is built are
  removed (recall is not reduced).
- **SC-004**: The first-run confirmation takes the developer under 2 minutes; later runs ask nothing.
- **SC-005**: A new developer installs the tool and produces the first report for a Yocto autotools module on Linux
  following only the guide, in under 30 minutes.
- **SC-006**: Attaching one screenshot to a case takes one paste (no file saving); 100% of attached images are
  visible inline in the reopened saved report and in its printed version.
- **SC-007**: Existing CMake benchmarks (leveldb ground truth, seeded regressions dev + holdout) show no drop.

## Assumptions

- The tool runs on the Linux host where the module source is checked out; for Yocto modules this is typically the
  build host / container (source via `devtool modify`, an external-source recipe or a plain checkout of the module).
- Compile information for autotools modules is obtained by the developer once per build configuration (a build
  under a compile-command recorder, locally or inside the Yocto build); the tool reads it, it never runs the Yocto
  build or `configure` itself (constitution: the tool does not configure or run builds).
- Variants are identified from what is visible in the workspace (`configure.ac` options, `Makefile.am`
  conditionals, preprocessor switches) plus what the developer declares at confirmation; the tool does not parse
  Yocto layers / recipes to discover machines. Declaring the switch values per variant at confirmation is
  acceptable to users.
- Writing reports and config into the tool's own folder in the workspace (locally ignored) is acceptable and does
  not count as modifying the analysed project; the constitution's scope fence (no source modification) still holds.
- Filtering uses the union of the confirmed variants; a case is removed only when the code is provably not built in
  all of them.
- Old run folders are kept until the user deletes them; no automatic retention policy in this feature.
- CMake support stays; Windows / macOS stay best-effort (not removed, not the documented main path).
- Evidence stays embedded in the single HTML report (no separate evidence folder), as today.
- The constitution's "Target codebases: C++ and CMake-based projects" line needs an amendment to cover autotools
  (C and C++); this is done through `/speckit-constitution` during planning.
