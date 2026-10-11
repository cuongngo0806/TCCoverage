# Quickstart — validate spec 009

```bash
pip install -e '.[dev]'
python3 -m pytest -q tests/unit/test_edits.py tests/unit/test_coupling.py tests/integration/test_us7_side_effects.py
python3 -m pytest -q                                   # full suite
python3 scripts/eval_real_project.py --quiet           # leveldb acceptance (network)
python3 scripts/seeded_regressions.py --workdir /tmp/tcadvisor-eval   # SC-701..SC-703
```

Expected: seeded summary `victims named ≥ 11/12; corner hinted ≥ 10/12; victim MRR ≥ 0.295`.
