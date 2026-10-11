export const meta = {
  name: 'product-cycle',
  description: 'One full product cycle for TCCoverage: specify → plan → tasks → analyze → implement → test/fix → review/fix → package VS Code extension → retro',
  whenToUse: 'Start a new feature/iteration of the TC Coverage tool; the destination of every cycle is a packaged .vsix',
  phases: [
    { title: 'Specify', detail: 'speckit-specify (assumptions recorded, no interactive clarify)' },
    { title: 'Plan', detail: 'speckit-plan + speckit-tasks', model: 'sonnet' },
    { title: 'Analyze', detail: 'speckit-analyze consistency gate (read-only)', model: 'sonnet' },
    { title: 'Implement', detail: 'speckit-implement, one worker, sequential tasks', model: 'sonnet' },
    { title: 'Test', detail: 'pytest + real-project eval, fix loop (max 2)', model: 'haiku' },
    { title: 'Review', detail: 'two review lenses in parallel, fix blocking findings', model: 'sonnet' },
    { title: 'Package', detail: 'compile + vsce package', model: 'haiku' },
    { title: 'Retro', detail: 'metrics + next-cycle backlog', model: 'haiku' },
  ],
}

// args: { feature: "<what to build>", specDir?: "specs/NNN-x" (skip Specify/Plan when given) }
const a = args || {}
const STATUS = { type: 'object', properties: { ok: { type: 'boolean' }, detail: { type: 'string' } }, required: ['ok', 'detail'] }
const SPEC = { type: 'object', properties: { specDir: { type: 'string' }, assumptions: { type: 'array', items: { type: 'string' } } }, required: ['specDir', 'assumptions'] }
const FINDINGS = {
  type: 'object',
  properties: {
    findings: {
      type: 'array',
      items: {
        type: 'object',
        properties: { file: { type: 'string' }, line: { type: 'integer' }, severity: { type: 'string', enum: ['blocking', 'minor'] }, issue: { type: 'string' } },
        required: ['file', 'severity', 'issue'],
      },
    },
  },
  required: ['findings'],
}
const TEST = { type: 'object', properties: { passed: { type: 'boolean' }, failures: { type: 'string' }, eval: { type: 'string' } }, required: ['passed', 'failures', 'eval'] }

let specDir = a.specDir
if (!specDir) {
  phase('Specify')
  // High-leverage decisions stay on the session model (no override).
  const s = await agent(
    `Follow .claude/skills/speckit-specify/SKILL.md for this feature: ${a.feature}\n` +
    'You cannot ask the user questions: record every open question as an explicit assumption in the ' +
    'Clarifications section instead. Respect .specify/memory/constitution.md. Return the spec directory.',
    { label: 'specify', phase: 'Specify', schema: SPEC })
  specDir = s.specDir
  log(`spec: ${specDir} (${s.assumptions.length} assumptions to review)`)

  phase('Plan')
  await agent(`Follow .claude/skills/speckit-plan/SKILL.md for ${specDir}. Keep it short; reuse existing modules.`,
    { label: 'plan', phase: 'Plan', model: 'sonnet' })
  await agent(`Follow .claude/skills/speckit-tasks/SKILL.md for ${specDir}.`, { label: 'tasks', phase: 'Plan', model: 'sonnet' })
}

phase('Analyze')
const gate = await agent(
  `Follow .claude/skills/speckit-analyze/SKILL.md for ${specDir} (read-only). ok=false only for CRITICAL ` +
  'constitution violations or requirements without tasks; put them in detail.',
  { label: 'analyze', phase: 'Analyze', schema: STATUS, model: 'sonnet', effort: 'low' })
if (gate && !gate.ok) {
  log(`analysis gate failed: ${gate.detail}`)
  return { specDir, stopped: 'analyze', detail: gate.detail }
}

phase('Implement')
await agent(
  `Follow .claude/skills/speckit-implement/SKILL.md for ${specDir}: implement unchecked tasks in order, tick them ` +
  'in tasks.md, run the narrowest pytest selection after each task. Commit nothing.',
  { label: 'implement', phase: 'Implement', model: 'sonnet' })

phase('Test')
const runTests = (i) => agent(
  'Run `python3 -m pytest -q` and `python3 scripts/eval_real_project.py --quiet` (skip the eval if it cannot ' +
  'clone). passed=true only if pytest passed and every eval expectation holds. Put failing test names + ' +
  'short tracebacks in failures (<=60 lines) and the eval summary line in eval.',
  { label: `test:${i}`, phase: 'Test', schema: TEST, model: 'haiku', effort: 'low' })
let t = await runTests(1)
for (let round = 1; t && !t.passed && round <= 2; round++) {
  await agent(`Fix these failures with minimal changes (do not skip or weaken tests):\n${t.failures}\n${t.eval}`,
    { label: `fix:${round}`, phase: 'Test', model: 'sonnet' })
  t = await runTests(round + 1)
}
if (!t || !t.passed) {
  log('tests still failing after 2 fix rounds — stopping before review')
  return { specDir, stopped: 'test', failures: t && t.failures }
}

phase('Review')
const lenses = [
  'correctness bugs in the uncommitted diff (git diff): wrong results, crashes, broken CLI/extension contracts',
  'constitution compliance of the uncommitted diff: evidence-backed cases, LLM never decides inclusion, ' +
  'uncertainty never dropped, no writes into the analysed repo, local-first, no test code generation',
]
const reviews = await parallel(lenses.map((l, i) => () =>
  agent(`Review for ${l}. Report only issues you can point to (file:line). Mark blocking only if it must be fixed before release.`,
    { label: `review:${i + 1}`, phase: 'Review', schema: FINDINGS, model: 'sonnet' })))
const blocking = reviews.filter(Boolean).flatMap(r => r.findings).filter(f => f.severity === 'blocking')
if (blocking.length) {
  await agent(`Fix these review findings, then run python3 -m pytest -q:\n${JSON.stringify(blocking, null, 1)}`,
    { label: 'review-fix', phase: 'Review', model: 'sonnet' })
}

phase('Package')
const pkg = await agent(
  'In vscode-extension/: run `npm install --no-audit --no-fund && npm run compile && npx --yes @vscode/vsce@3.2.1 package ' +
  '--allow-missing-repository --skip-license`. ok=true if a .vsix was produced; detail = its path or the error.',
  { label: 'package', phase: 'Package', schema: STATUS, model: 'haiku', effort: 'low' })

phase('Retro')
const retro = await agent(
  `Write ${specDir}/retro.md (<=60 lines): what shipped (tasks.md checked items), test + eval results ` +
  `(${t.eval}), review findings (${blocking.length} blocking fixed), package result (${pkg && pkg.detail}), and a ` +
  '"Next cycle backlog" list. Return the backlog as plain lines.',
  { label: 'retro', phase: 'Retro', model: 'haiku', effort: 'low' })
return { specDir, eval: t.eval, blockingFixed: blocking.length, vsix: pkg && pkg.detail, backlog: retro }
