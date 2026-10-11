# Contract — report additions (spec 007)

```json
"test_gaps": [
  {"symbol": {"qualified_name": "leveldb::FindFile", "kind": "function", "file_path": "db/version_set.cc", "line": 87},
   "reason": "no existing test reaches it within 2 hop(s)"}
]
```

Brief output (`--print brief`), one line after the summary:

```text
TEST GAPS leveldb::FindFile (no existing test reaches it within 2 hop(s))
```

New pattern case kinds keep the existing case shape (`evidence[0]` = reader symbol, `activation_condition` names
the changed line, `corner_cases` concrete).
