// Headless smoke test: loads out/extension.js against a stub `vscode` module (no VS Code download needed),
// activates it on an existing report and checks commands, tree, status bar and inline hints.
// usage: node test/smoke.js <dir containing report.json> <repo>
const Module = require("module");
const path = require("path");
const assert = require("assert");
const [reportDir, repo] = process.argv.slice(2);
const registered = {}, diags = new Map(), messages = [];
let treeProvider, status = {};
class EventEmitter { constructor() { this.event = () => {}; } fire() {} }
class TreeItem { constructor(label, state) { this.label = label; this.collapsibleState = state; } }
const cfgValues = { repo, outputDir: reportDir, showInlineHints: true, graphProvider: "auto" };
const vscode = {
  EventEmitter, TreeItem,
  TreeItemCollapsibleState: { None: 0, Collapsed: 1, Expanded: 2 },
  ThemeIcon: class { constructor(id) { this.id = id; } },
  MarkdownString: class { constructor(v) { this.value = v; } },
  StatusBarAlignment: { Left: 1 }, DiagnosticSeverity: { Information: 2, Hint: 3 }, ViewColumn: { One: 1, Beside: -2 },
  ProgressLocation: { Notification: 15 }, ConfigurationTarget: { Workspace: 2 },
  Range: class { constructor(a, b, c, d) { this.a = [a, b, c, d]; } },
  Position: class { constructor(l, c) { this.line = l; this.character = c; } },
  Diagnostic: class { constructor(r, m, s) { this.range = r; this.message = m; this.severity = s; } },
  Uri: { file: f => ({ fsPath: f, toString: () => f }) },
  window: {
    createOutputChannel: () => ({ appendLine() {}, append() {}, show() {}, dispose() {} }),
    createStatusBarItem: () => { status = { show() { status.shown = true; }, dispose() {} }; return status; },
    registerTreeDataProvider: (id, p) => { treeProvider = p; return { dispose() {} }; },
    showInformationMessage: (m) => { messages.push(m); return Promise.resolve(undefined); },
    showErrorMessage: (m) => { messages.push(m); return Promise.resolve(undefined); },
  },
  languages: { createDiagnosticCollection: () => ({ clear() { diags.clear(); }, set(u, d) { diags.set(u.fsPath, d); }, dispose() {} }) },
  workspace: {
    workspaceFolders: [{ uri: { fsPath: repo } }],
    getConfiguration: () => ({ get: (k) => cfgValues[k], update: async () => {} }),
    onDidChangeConfiguration: () => ({ dispose() {} }),
  },
  commands: { registerCommand: (id, fn) => { registered[id] = fn; return { dispose() {} }; } },
  env: { clipboard: { writeText: async (t) => { messages.push("clip:" + t); } } },
};
const orig = Module._load;
Module._load = function (req, ...rest) { return req === "vscode" ? vscode : orig.call(this, req, ...rest); };
const ext = require(path.join(__dirname, "..", "out", "extension.js"));
ext.activate({ subscriptions: [] });

const pkg = require("../package.json");
for (const c of pkg.contributes.commands) assert.ok(registered[c.command], `command not registered: ${c.command}`);
const top = treeProvider.getChildren();
const labels = top.map(n => n.label);
assert.ok(labels.some(l => /^P1 \(\d+\)$/.test(l)), "P1 group: " + labels);
const firstCase = top[0].children[0];
const item = treeProvider.getTreeItem(firstCase);
assert.ok(/^TC-\d{4}/.test(item.label), item.label);
assert.ok(status.shown && /TC: \d+ P1/.test(status.text), status.text);
assert.ok(diags.size > 0, "inline hints");
const report = require(path.join(reportDir, "report.json"));
if (report.ai_verification) {
  assert.ok(labels.some(l => l.startsWith("AI: also check")), "AI group");
  assert.ok(item.description.startsWith("AI: "), "verdict badge: " + item.description);
}
if ((report.existing_tests || []).length) {
  assert.ok(labels.some(l => l.startsWith("Existing tests")), "tests group");
  registered["tcCoverage.copyTestFilter"]().then(() => assert.ok(messages.some(m => m.startsWith("clip:--gtest_filter="))));
}
console.log(`SMOKE OK: ${Object.keys(registered).length} commands, groups=[${labels.join(" | ")}], hints in ${diags.size} file(s)`);
