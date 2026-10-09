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

// args: { repo, buildDir, mode: "--commit-range A..B" | "--working-tree" | "--symbols X", graph?: "auto",
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

phase('Analyze')
let analyzeCmd = ''
if (!a.report) {
  const out = a.outDir || `${a.repo}/../tcadvisor-report`
  analyzeCmd = `python3 -m tcadvisor analyze --repo ${a.repo} --build-dir ${a.buildDir} ${a.mode || '--working-tree'} ` +
    `--graph ${a.graph || 'auto'} ${a.targets ? '--targets ' + a.targets : ''} --output-dir ${out} --print brief -q`
}
const reportPath = a.report || `${a.outDir || a.repo + '/../tcadvisor-report'}/report.json`
const m = await agent(
  (analyzeCmd ? `Run exactly:\n${analyzeCmd}\nIf it exits non-zero, return error=<stderr tail> and empty batches.\n` : '') +
  `Then run: python3 -m tcadvisor verify-pack ${reportPath}\n` +
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
  agent(`Verify the batch file ${b}. Return every case id in it.`,
    { label: `verify:${i + 1}`, phase: 'Verify', schema: VERDICTS, agentType: 'tc-case-verifier', model: 'haiku' })))
const ok = results.filter(Boolean)
if (ok.length < m.batches.length) log(`${m.batches.length - ok.length} batch(es) failed; their cases stay unverified`)
const merged = {}
for (const r of ok) for (const v of r.verdicts) merged[v.id] = v

phase('Synthesize')
const synth = await agent(
  `Report: ${m.report}\nVerify dir: ${m.verify_dir}\nBatch verdicts (already merged, id -> verdict):\n` +
  JSON.stringify(merged) +
  `\nWrite ${m.verify_dir}/verdicts.json as {"cases": {<id>: {verdict, note, extra_corner_cases, recheck}}, ` +
  `"summary", "additional_checks", "models": ["haiku (case verification)", "sonnet (synthesis)"]} and annotate.`,
  { label: 'synthesize', phase: 'Synthesize', agentType: 'tc-verify-synthesizer', model: 'sonnet' })
return { summary: m.summary, batches: m.batches.length, verified: Object.keys(merged).length, annotate: synth }
