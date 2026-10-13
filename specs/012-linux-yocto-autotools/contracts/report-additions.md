# report.json additions (spec 012)

All keys optional for older readers; `specs/001-change-impact-test-advisor/contracts/output-schema.json` is extended.

```json
{
  "run": {"name": "20261012-101530-a1b2c3d_e4f5a6b", "path": "/abs/repo/.tcadvisor/reports/20261012-101530-a1b2c3d_e4f5a6b",
          "created_at": "2026-10-12T10:15:30Z", "change": "a1b2c3d..e4f5a6b"},
  "build_model": {"system": "autotools", "products": 4, "fingerprint": "…"},
  "build_profile": {"state": "confirmed|stale|absent|overridden", "variants": ["imx8-basic", "imx8-pro"], "filtering": true},
  "not_built": [
    {"case": {"id": "TC-012", "...": "full case object"},
     "excluded_by": [{"variant": "imx8-basic", "reason": "preprocessor", "condition": "defined(FEATURE_X)",
                      "where": "src/remote.c:120"}]}
  ],
  "not_built_changes": [{"path": "src/pro_only.c", "symbol": "pro_init", "line": 10, "excluded_by": [{"variant": "imx8-basic", "reason": "source_not_in_product", "condition": "if FEATURE_X", "where": "lib/Makefile.am:7"}]}]
}
```

- Case `targets` for autotools hold product names (`remotecontrolapp`, `libremote`).
- New uncertainty category `build_description_unresolved` (`{file, line, construct}` in the reason).
- `report.md` / `report.html` / brief: section "Not built in the confirmed variants" (count + entries with the
  condition), a header line with the profile state; brief line `not built (profile): N`; last line
  `report: <run folder>`. vi catalog entries for all of them.
- HTML evidence: paste support, inline images (`.evimg`, ≤ 480 px), full-size overlay, print shows images.
