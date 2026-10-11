// VS Code front-end for tcadvisor: runs the CLI, shows cases in a tree, inline hints and the HTML impact flow.
import * as vscode from "vscode";
import * as cp from "child_process";
import * as fs from "fs";
import * as path from "path";

interface SymbolRef { qualified_name: string; kind: string; file_path: string; line: number }
interface Edge { relation: string; from_symbol: SymbolRef; to_symbol: SymbolRef; source_location: { file_path: string; line: number } }
interface Case {
  id: string; description: string; activation_condition: string; evidence: (SymbolRef | Edge)[];
  priority: string; risk_group: string; sub_reason?: string; hop_distance: number; corner_cases?: string[];
  related_cmake_targets: string[];
  verification?: { verdict: "confirmed" | "weak" | "needs_info"; note: string; extra_corner_cases: string[]; recheck: boolean };
}
interface Flag { category: string; reason: string; related_symbol: SymbolRef | null }
interface Report {
  test_case_candidates: Case[]; uncertainty_flags: Flag[]; affected_targets?: { name: string; relation: string }[];
  no_detected_impact?: boolean; change_input: { target_repo_path: string };
  existing_tests?: { test: string; file_path: string; line: number; hop_distance: number }[];
  ai_verification?: { summary: string; additional_checks: { title: string; why: string; evidence: string }[];
    verified_cases: number; usage?: { cost_usd: number; calls: number } };
  graph_provider?: string;
}
const VERDICT_ICON: Record<string, string> = { confirmed: "pass", weak: "info", needs_info: "question" };

const isSym = (e: SymbolRef | Edge): e is SymbolRef => (e as SymbolRef).qualified_name !== undefined;
const RISK: Record<string, string> = {
  logic: "Logic", abi_layout: "ABI / layout", ownership_lifetime: "Ownership / lifetime",
  thread_safety: "Thread safety", exception_safety: "Exception safety", build_config: "Build config",
};

let report: Report | undefined;
let reportDir: string | undefined;
let panel: vscode.WebviewPanel | undefined;
const output = vscode.window.createOutputChannel("TC Coverage");
const diagnostics = vscode.languages.createDiagnosticCollection("tcCoverage");

function cfg() { return vscode.workspace.getConfiguration("tcCoverage"); }

function repoRoot(): string | undefined {
  const r = cfg().get<string>("repo");
  if (r) { return r; }
  return vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
}

function outDir(repo: string): string {
  const o = cfg().get<string>("outputDir");
  return o ? o : path.join(path.dirname(repo), "tcadvisor-report", path.basename(repo));
}

// ---------------------------------------------------------------------------------- tree view
type Node = { label: string; kind: "group" | "case" | "evidence" | "flag" | "info"; children?: Node[];
  file?: string; line?: number; tooltip?: string; prio?: string; verdict?: string };

class CasesProvider implements vscode.TreeDataProvider<Node> {
  private emitter = new vscode.EventEmitter<Node | undefined>();
  readonly onDidChangeTreeData = this.emitter.event;
  refresh() { this.emitter.fire(undefined); }

  getChildren(n?: Node): Node[] {
    if (n) { return n.children ?? []; }
    if (!report) { return [{ label: "Run 'TC Coverage: Analyze Working Tree Changes'", kind: "info" }]; }
    if (report.no_detected_impact) { return [{ label: "No detected impact (comments/format/non-C++ only)", kind: "info" }]; }
    const groups: Node[] = ["P1", "P2", "P3"].map(p => {
      const cs = report!.test_case_candidates.filter(c => c.priority === p);
      if (cfg().get<string>("ai.order") === "ai") {  // stable: relevance order inside each verdict
        const k = (c: Case) => c.verification ? ({ confirmed: 0, needs_info: 1, weak: 3 } as Record<string, number>)[c.verification.verdict] : 2;
        cs.sort((x, y) => k(x) - k(y));
      }
      return {
        label: `${p} (${cs.length})`, kind: "group" as const, prio: p,
        children: cs.map(c => caseNode(c)),
      };
    }).filter(g => (g.children?.length ?? 0) > 0);
    if (report.existing_tests?.length) {
      groups.push({ label: `Existing tests to re-run (${report.existing_tests.length})`, kind: "group",
        children: report.existing_tests.map(t => ({ label: t.test, kind: "evidence" as const, file: t.file_path, line: t.line })) });
    }
    if (report.ai_verification) {
      const av = report.ai_verification;
      groups.push({ label: `AI: also check (${av.additional_checks.length})`, kind: "group", tooltip: av.summary,
        children: av.additional_checks.map(a => {
          const m = /^(.*):(\d+)$/.exec(a.evidence || "");
          return { label: a.title, kind: "flag" as const, tooltip: a.why, file: m?.[1], line: m ? +m[2] : undefined };
        }) });
    }
    if (report.uncertainty_flags.length) {
      groups.push({
        label: `Uncertain — manual review (${report.uncertainty_flags.length})`, kind: "group",
        children: report.uncertainty_flags.map(f => ({
          label: `${f.category}: ${f.related_symbol?.qualified_name ?? "-"}`, kind: "flag" as const, tooltip: f.reason,
          file: f.related_symbol?.file_path, line: f.related_symbol?.line,
        })),
      });
    }
    if (report.affected_targets?.length) {
      groups.push({ label: `Targets to rebuild/retest (${report.affected_targets.length})`, kind: "group",
        children: report.affected_targets.map(t => ({ label: `${t.name} — ${t.relation}`, kind: "info" as const })) });
    }
    return groups;
  }

  getTreeItem(n: Node): vscode.TreeItem {
    const it = new vscode.TreeItem(n.label, n.children?.length
      ? (n.kind === "group" && n.prio !== "P1" && n.prio !== undefined ? vscode.TreeItemCollapsibleState.Collapsed
        : vscode.TreeItemCollapsibleState.Expanded)
      : vscode.TreeItemCollapsibleState.None);
    it.tooltip = n.tooltip ? new vscode.MarkdownString(n.tooltip) : undefined;
    const icons: Record<string, string> = { case: "beaker", evidence: "symbol-method", flag: "warning", info: "info" };
    if (icons[n.kind]) { it.iconPath = new vscode.ThemeIcon(icons[n.kind]); }
    if (n.kind === "case") {
      it.collapsibleState = vscode.TreeItemCollapsibleState.Collapsed;
      if (n.verdict) { it.iconPath = new vscode.ThemeIcon(VERDICT_ICON[n.verdict] ?? "beaker"); }
    }
    if (n.file) {
      it.command = { command: "tcCoverage.openEvidence", title: "Open", arguments: [n.file, n.line ?? 1] };
      it.description = (n.verdict ? `AI: ${n.verdict} · ` : "") + `${n.file}:${n.line}`;
    }
    return it;
  }
}

function caseNode(c: Case): Node {
  const first = c.evidence.find(isSym);
  const tip = `**${c.id}** ${c.priority} · ${RISK[c.risk_group]}${c.sub_reason ? " · " + c.sub_reason : ""}\n\n` +
    `${c.description}\n\n*When*: ${c.activation_condition}\n\n` +
    (c.corner_cases?.length ? "*Corner cases*:\n" + c.corner_cases.map(h => `- ${h}`).join("\n") + "\n\n" : "") +
    `*Targets*: ${c.related_cmake_targets.join(", ")}` +
    (c.verification ? `\n\n---\n**AI (${c.verification.verdict}${c.verification.recheck ? ", re-check" : ""})**: ${c.verification.note}` +
      c.verification.extra_corner_cases.map(h => `\n- ${h}`).join("") : "");
  const children: Node[] = c.evidence.map(e => isSym(e)
    ? { label: e.qualified_name, kind: "evidence" as const, file: e.file_path, line: e.line }
    : { label: `${e.relation} → ${e.to_symbol.qualified_name}`, kind: "evidence" as const,
        file: e.source_location.file_path, line: e.source_location.line });
  for (const h of c.corner_cases ?? []) { children.push({ label: h, kind: "info" }); }
  for (const h of c.verification?.extra_corner_cases ?? []) { children.push({ label: `AI: ${h}`, kind: "info" }); }
  return { label: `${c.id} [${RISK[c.risk_group]}] ${first?.qualified_name ?? ""}`, kind: "case", tooltip: tip,
    children, file: first?.file_path, line: first?.line, verdict: c.verification?.verdict };
}

// ---------------------------------------------------------------------------------- running
function runAnalyze(modeArgs: string[], tree: CasesProvider): Thenable<void> {
  const repo = repoRoot();
  if (!repo) { vscode.window.showErrorMessage("TC Coverage: open the analysed repository as a workspace folder."); return Promise.resolve(); }
  const bd = cfg().get<string>("buildDir") || "build";
  const buildDir = path.isAbsolute(bd) ? bd : path.join(repo, bd);
  const out = outDir(repo);
  const args = ["-m", "tcadvisor", "analyze", "--repo", repo, "--build-dir", buildDir, "--output-dir", out,
    "--max-hop-depth", String(cfg().get<number>("maxHopDepth") ?? 2), ...modeArgs, ...(cfg().get<string[]>("extraArgs") ?? [])];
  args.push("--graph", cfg().get<string>("graphProvider") || "auto");
  const gbin = cfg().get<string>("graphBin");
  if (gbin) { args.push("--graph-bin", gbin); }
  const targets = cfg().get<string>("targets");
  if (targets) { args.push("--targets", targets); }
  const py = cfg().get<string>("pythonPath") || "python3";
  output.appendLine(`$ ${py} ${args.join(" ")}`);
  return vscode.window.withProgress({ location: vscode.ProgressLocation.Notification, title: "TC Coverage: analysing change…" },
    () => new Promise<void>(resolve => {
      const proc = cp.spawn(py, args, { cwd: repo });
      let stdout = "";
      proc.stdout.on("data", d => { stdout += d; output.append(String(d)); });
      proc.stderr.on("data", d => output.append(String(d)));
      proc.on("error", err => { vscode.window.showErrorMessage(`TC Coverage: cannot start ${py}: ${err.message}`); resolve(); });
      proc.on("close", code => {
        if (code === 0) {
          loadReport(out, tree);
          const s = stdout.split("\n")[0];
          vscode.window.showInformationMessage(`TC Coverage: ${s}`, "Show Report").then(a => { if (a) { showReport(); } });
        } else {
          const what = code === 1 ? "prerequisite missing (compile_commands.json / CMake File API — see output)"
            : code === 2 ? "invalid input (see output)" : "internal error (see output)";
          vscode.window.showErrorMessage(`TC Coverage: ${what}`, "Show Output").then(a => { if (a) { output.show(); } });
        }
        resolve();
      });
    }));
}

function runPython(args: string[], title: string, cwd: string): Thenable<number> {
  const py = cfg().get<string>("pythonPath") || "python3";
  output.appendLine(`$ ${py} ${args.join(" ")}`);
  return vscode.window.withProgress({ location: vscode.ProgressLocation.Notification, title }, () =>
    new Promise<number>(resolve => {
      const proc = cp.spawn(py, args, { cwd });
      proc.stdout.on("data", d => output.append(String(d)));
      proc.stderr.on("data", d => output.append(String(d)));
      proc.on("error", err => { output.appendLine(String(err)); resolve(127); });
      proc.on("close", code => resolve(code ?? 1));
    }));
}

async function verifyWithClaude(tree: CasesProvider) {
  if (!report || !reportDir) { vscode.window.showInformationMessage("TC Coverage: run an analysis first."); return; }
  const c = cfg();
  if (!c.get<boolean>("ai.approved")) {
    const pick = await vscode.window.showWarningMessage(
      "AI verification sends packed code windows (≤40 lines per impacted symbol, never the whole repository) " +
      "to Anthropic through the Claude Code CLI. Is that allowed for this code base?", { modal: true },
      "Always allow on this machine", "Allow once");
    if (!pick) { return; }
    if (pick === "Always allow on this machine") {
      await c.update("ai.approved", true, vscode.ConfigurationTarget.Global);
    }
  }
  const args = ["-m", "tcadvisor", "verify", path.join(reportDir, "report.json"), "--ai-external-approved",
    "--claude-bin", c.get<string>("ai.claudePath") || "claude",
    "--verify-model", c.get<string>("ai.verifyModel") || "haiku", "--synth-model", c.get<string>("ai.synthModel") || "sonnet"];
  const budget = c.get<number>("ai.budgetUsd");
  if (budget) { args.push("--budget-usd", String(budget)); }
  const code = await runPython(args, "TC Coverage: verifying cases with Claude…", report.change_input.target_repo_path);
  if (code !== 0) {
    vscode.window.showErrorMessage("TC Coverage: AI verification failed (see output)", "Show Output").then(a => { if (a) { output.show(); } });
    return;
  }
  loadReport(reportDir, tree);
  const av = report?.ai_verification;
  vscode.window.showInformationMessage(`TC Coverage: AI verified ${av?.verified_cases ?? 0} case(s)` +
    (av?.usage ? ` · ${av.usage.calls} calls · $${av.usage.cost_usd.toFixed(3)}` : ""), "Show Report").then(a => { if (a) { showReport(); } });
}

function loadReport(dir: string, tree: CasesProvider) {
  const p = path.join(dir, "report.json");
  if (!fs.existsSync(p)) { return; }
  report = JSON.parse(fs.readFileSync(p, "utf8")) as Report;
  reportDir = dir;
  tree.refresh();
  updateDiagnostics();
  if (panel) { panel.webview.html = reportHtml(); }
  const verified = report.test_case_candidates.filter(c => c.verification).length;
  status.tooltip = `graph: ${report.graph_provider ?? "clang"}${verified ? ` · AI-verified ${verified}` : ""}`;
  status.text = report.no_detected_impact ? "$(beaker) TC: no impact"
    : `$(beaker) TC: ${report.test_case_candidates.filter(c => c.priority === "P1").length} P1 / ${report.test_case_candidates.length}`;
  status.show();
}

function updateDiagnostics() {
  diagnostics.clear();
  if (!report || !cfg().get<boolean>("showInlineHints")) { return; }
  const repo = report.change_input.target_repo_path;
  const byFile = new Map<string, vscode.Diagnostic[]>();
  for (const c of report.test_case_candidates) {
    if (c.priority === "P3") { continue; }
    const e = c.evidence.find(isSym);
    if (!e) { continue; }
    const line = Math.max(0, e.line - 1);
    const d = new vscode.Diagnostic(new vscode.Range(line, 0, line, 200), `${c.id} ${c.priority} [${RISK[c.risk_group]}] ${c.description}`,
      c.priority === "P1" ? vscode.DiagnosticSeverity.Information : vscode.DiagnosticSeverity.Hint);
    d.source = "TC Coverage";
    const f = path.join(repo, e.file_path);
    byFile.set(f, [...(byFile.get(f) ?? []), d]);
  }
  for (const [f, ds] of byFile) { diagnostics.set(vscode.Uri.file(f), ds); }
}

function reportHtml(): string {
  const p = reportDir ? path.join(reportDir, "report.html") : "";
  if (!p || !fs.existsSync(p)) { return "<p>No report yet.</p>"; }
  return fs.readFileSync(p, "utf8");
}

function showReport() {
  if (!report) { vscode.window.showInformationMessage("TC Coverage: run an analysis first."); return; }
  if (!panel) {
    panel = vscode.window.createWebviewPanel("tcCoverageReport", "TC Coverage Report", vscode.ViewColumn.Beside,
      { enableScripts: true, retainContextWhenHidden: true });
    panel.onDidDispose(() => { panel = undefined; });
    panel.webview.onDidReceiveMessage(m => {
      if (m?.type === "open") { openEvidence(m.file, m.line); }
      else if (m?.type === "saveReport") { saveFromReport(m.name, Buffer.from(String(m.html), "utf8"), true); }
      else if (m?.type === "saveFile") { saveFromReport(m.name, Buffer.from(String(m.data), "base64"), false); }
    });
  }
  panel.webview.html = reportHtml();
  panel.reveal();
}

// Test results (spec 006): the report webview cannot download files, so saving goes through a save dialog.
async function saveFromReport(name: string, data: Buffer, isReport: boolean) {
  const base = reportDir ?? repoRoot() ?? ".";
  const target = await vscode.window.showSaveDialog({
    defaultUri: vscode.Uri.file(path.join(base, path.basename(String(name || "report.html")))),
    filters: isReport ? { "TC Coverage report": ["html"] } : undefined,
    title: isReport ? "Save TC Coverage report with test results" : "Save evidence file",
  });
  if (!target) { return; }
  await vscode.workspace.fs.writeFile(target, data);
  if (isReport) {
    panel?.webview.postMessage({ type: "saved", path: target.fsPath });
    vscode.window.showInformationMessage(`TC Coverage: report saved to ${target.fsPath}`);
  }
}

async function openEvidence(file: string, line: number) {
  const repo = report?.change_input.target_repo_path ?? repoRoot();
  if (!repo) { return; }
  const target = path.resolve(repo, file);
  if (path.relative(path.resolve(repo), target).startsWith("..") || path.isAbsolute(path.relative(path.resolve(repo), target))) {
    vscode.window.showWarningMessage(`TC Coverage: refusing to open ${file} (outside the repository)`);
    return;
  }
  const doc = await vscode.workspace.openTextDocument(target);
  const pos = new vscode.Position(Math.max(0, line - 1), 0);
  await vscode.window.showTextDocument(doc, { selection: new vscode.Range(pos, pos), viewColumn: vscode.ViewColumn.One });
}

async function symbolAtCursor(): Promise<string | undefined> {
  const ed = vscode.window.activeTextEditor;
  if (!ed) { return undefined; }
  const syms = await vscode.commands.executeCommand<vscode.DocumentSymbol[]>("vscode.executeDocumentSymbolProvider", ed.document.uri);
  const wanted = new Set([vscode.SymbolKind.Function, vscode.SymbolKind.Method, vscode.SymbolKind.Constructor,
    vscode.SymbolKind.Class, vscode.SymbolKind.Struct]);
  const scopes = new Set([vscode.SymbolKind.Namespace, vscode.SymbolKind.Class, vscode.SymbolKind.Struct]);
  let best: string | undefined;
  const walk = (list: vscode.DocumentSymbol[] | undefined, prefix: string[]) => {
    for (const s of list ?? []) {
      if (!s.range.contains(ed.selection.active)) { continue; }
      const name = s.name.replace(/\(.*$/, "").trim();
      const parts = name.includes("::") ? name.split("::") : [...prefix, name];
      if (wanted.has(s.kind)) { best = parts.join("::"); }
      walk(s.children, scopes.has(s.kind) ? parts : prefix);
    }
  };
  walk(syms, []);
  if (best) { return best; }
  const r = ed.document.getWordRangeAtPosition(ed.selection.active, /[A-Za-z_][\w:]*/);
  return r ? ed.document.getText(r) : undefined;
}

const status = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 50);

export function activate(ctx: vscode.ExtensionContext) {
  const tree = new CasesProvider();
  status.command = "tcCoverage.showReport";
  const repo = repoRoot();
  if (repo) { loadReport(outDir(repo), tree); }
  ctx.subscriptions.push(
    output, diagnostics, status,
    vscode.window.registerTreeDataProvider("tcCoverage.cases", tree),
    vscode.commands.registerCommand("tcCoverage.analyzeWorkingTree", () => runAnalyze(["--working-tree"], tree)),
    vscode.commands.registerCommand("tcCoverage.analyzeLastCommit", () => runAnalyze(["--commit-range", "HEAD~1..HEAD"], tree)),
    vscode.commands.registerCommand("tcCoverage.analyzeRange", async () => {
      const r = await vscode.window.showInputBox({ prompt: "Commit range (A..B)", value: "origin/main..HEAD" });
      if (r) { await runAnalyze(["--commit-range", r], tree); }
    }),
    vscode.commands.registerCommand("tcCoverage.analyzeSymbol", async () => {
      const guess = await symbolAtCursor();
      const s = await vscode.window.showInputBox({ prompt: "Function/method/class (qualified name)", value: guess ?? "" });
      if (s) { await runAnalyze(["--symbols", s], tree); }
    }),
    vscode.commands.registerCommand("tcCoverage.showReport", showReport),
    vscode.commands.registerCommand("tcCoverage.verifyWithClaude", () => verifyWithClaude(tree)),
    vscode.commands.registerCommand("tcCoverage.copyTestFilter", async () => {
      const t = report?.existing_tests ?? [];
      if (!t.length) { vscode.window.showInformationMessage("TC Coverage: no existing tests found in the impact."); return; }
      await vscode.env.clipboard.writeText(`--gtest_filter=${t.map(x => x.test).join(":")}`);
      vscode.window.showInformationMessage(`TC Coverage: copied filter for ${t.length} test(s)`);
    }),
    vscode.commands.registerCommand("tcCoverage.openEvidence", openEvidence),
    vscode.commands.registerCommand("tcCoverage.clearCache", () => {
      const r = repoRoot();
      if (!r) { return; }
      cp.execFile(cfg().get<string>("pythonPath") || "python3", ["-m", "tcadvisor", "cache", "clear", "--repo", r],
        (err, out) => vscode.window.showInformationMessage(err ? `TC Coverage: ${err.message}` : `TC Coverage: ${out.trim()}`));
    }),
    vscode.workspace.onDidChangeConfiguration(e => { if (e.affectsConfiguration("tcCoverage.showInlineHints")) { updateDiagnostics(); }
      if (e.affectsConfiguration("tcCoverage.ai.order")) { tree.refresh(); } }),
  );
}

export function deactivate() { /* nothing */ }
