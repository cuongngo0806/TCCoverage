export const meta = {
  name: 'tc-verify',
  description: 'Graph-based impact (tcadvisor + codegraph/GitNexus) then token-lean AI verification: Haiku per batch, one Sonnet synthesis',
  whenToUse: 'After a C++ change: get the test cases to check, verified by AI, annotated into the report shown in VS Code',
  phases: [
    { title: 'Analyze', detail: 'tcadvisor analyze + verify-pack (deterministic, no LLM reasoning)', model: 'haiku' },
    { title: 'Verify', detail: 'tc-case-verifier per batch of 8 packets', model: 'haiku' },
    { title: 'Synthesize', detail: 'tc-verify-synthesizer merges + annotates', model: 'sonnet' },
  ],
}

// args: { approved: true (required: packed code windows go to the model provider), repo, buildDir, mode: "--commit-range A..B" | "--working-tree" | "--symbols X", graph?: "auto",
//         outDir?, targets?, report? (skip Analyze and verify an existing report.json) }
const a = args || {}
const VERDICTS = {
  type: 'object',
  properties: {
    verdicts: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          id: { type: 'string' },
          verdict: { type: 'string', enum: ['confirmed', 'weak', 'needs_info'] },
          note: { type: 'string' },
          extra_corner_cases: { type: 'array', items: { type: 'string' } },
          recheck: { type: 'boolean' },
        },
        required: ['id', 'verdict', 'note', 'extra_corner_cases', 'recheck'],
      },
    },
  },
  required: ['verdicts'],
}
const MANIFEST = {
  type: 'object',
  properties: {
    report: { type: 'string' },
    verify_dir: { type: 'string' },
    batches: { type: 'array', items: { type: 'string' } },
    summary: { type: 'string' },
    error: { type: 'string' },
  },
  required: ['report', 'verify_dir', 'batches', 'summary'],
}

// Agent instructions live in .claude/agents/*.md. They are referenced by path instead of agentType so the
// workflow also works in sessions started before those agent files existed.
const AGENT_DOC = (name) => `Your role and rules: read .claude/agents/${name}.md in the TCCoverage repo ` +
  `(${a.toolRepo || '/home/user/TCCoverage'}) and follow its body (ignore the frontmatter).`

const q = (v) => "'" + String(v).replace(/'/g, "'\\''") + "'"  // POSIX shell quoting
const MODE = /^(--working-tree|--commit-range [\w.\/~^@{}-]+\.\.[\w.\/~^@{}-]*|--symbols [\w:,~]+)$/
if (!a.approved) {
  log('AI verification sends packed code windows to the model provider: pass args.approved=true to confirm')
  return { error: 'not approved (args.approved=true required)' }
}
if (a.mode && !MODE.test(a.mode)) return { error: `unsupported mode string: ${a.mode}` }

phase('Analyze')
let analyzeCmd = ''
if (!a.report) {
  const out = a.outDir || `${a.repo}/../tcadvisor-report`
  const graph = ['auto', 'codegraph', 'gitnexus', 'clang'].includes(a.graph) ? a.graph : 'auto'
  analyzeCmd = `python3 -m tcadvisor analyze --repo ${q(a.repo)} --build-dir ${q(a.buildDir)} ${a.mode || '--working-tree'} ` +
    `--graph ${graph} ${a.targets ? '--targets ' + q(a.targets) : ''} --output-dir ${q(out)} --print brief -q`
}
const reportPath = a.report || `${a.outDir || a.repo + '/../tcadvisor-report'}/report.json`
const m = await agent(
  (analyzeCmd ? `Run exactly:\n${analyzeCmd}\nIf it exits non-zero, return error=<stderr tail> and empty batches.\n` : '') +
  `Then run: python3 -m tcadvisor verify-pack ${q(reportPath)}\n` +
  `Return report=${reportPath}, verify_dir (from the manifest), batches = the batch file paths, ` +
  `summary = the first line of ${reportPath.replace(/report\.json$/, 'report.brief.txt')}. Do not read other files.`,
  { label: 'analyze', phase: 'Analyze', schema: MANIFEST, model: 'haiku', effort: 'low' })
if (!m || m.error || !m.batches.length) {
  log(m && m.error ? `analysis failed: ${m.error}` : 'nothing to verify (no P1/P2 cases)')
  return { summary: m && m.summary, error: m && m.error, verified: 0 }
}
log(`${m.summary} — ${m.batches.length} batch(es) to verify`)

// Each batch verifies independently; synthesis needs all of them (one barrier, by design).
const results = await parallel(m.batches.map((b, i) => () =>
  agent(`${AGENT_DOC('tc-case-verifier')}\nVerify the batch file ${b}. Return every case id in it.`,
    { label: `verify:${i + 1}`, phase: 'Verify', schema: VERDICTS, model: 'haiku', effort: 'low' })))
const ok = results.filter(Boolean)
if (ok.length < m.batches.length) log(`${m.batches.length - ok.length} batch(es) failed; their cases stay unverified`)
const merged = {}
for (const r of ok) for (const v of r.verdicts) merged[v.id] = v

phase('Synthesize')
const synth = await agent(
  `Report: ${m.report}\nVerify dir: ${m.verify_dir}\nBatch verdicts (already merged, id -> verdict):\n` +
  JSON.stringify(merged) +
  `\nWrite ${m.verify_dir}/verdicts.json as {"cases": {<id>: {verdict, note, extra_corner_cases, recheck}}, ` +
  `"summary", "additional_checks", "models": ["haiku (case verification)", "sonnet (synthesis)"]} and annotate.\n` +
  AGENT_DOC('tc-verify-synthesizer'),
  { label: 'synthesize', phase: 'Synthesize', model: 'sonnet' })
return { summary: m.summary, batches: m.batches.length, verified: Object.keys(merged).length, annotate: synth }
