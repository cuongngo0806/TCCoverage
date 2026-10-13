# Quickstart — validate spec 013

```bash
pip install -e '.[dev]'
python3 -m pytest -q tests/unit/test_scenarios.py tests/unit/test_rules.py
# re-render the pilot from its report.json (no re-analysis needed)
python3 -m tcadvisor render --help   # or the helper below
python3 - <<'PY'
import json; from pathlib import Path
from tcadvisor.report.render import write_outputs
r = json.loads(Path("human-test/remotecontrolapp/20261013-124545-61ffe19_cb62fef/report.json").read_text())
print(write_outputs(r, Path("/tmp/pilot013")))
PY
head -40 /tmp/pilot013/report.md      # expected: "4 scenario(s) cover 7 case(s)" and a mermaid flow
```

Expected: S1 `processRxResSig → checkEndF → determineResSuspend` covers TC-0153, TC-0018, TC-0001; S2
`handleMessage → processOrderResp` covers TC-0017, TC-0005; full suite green.
