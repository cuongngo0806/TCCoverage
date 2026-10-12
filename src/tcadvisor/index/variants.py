"""Build-flow detection and confirmation (spec 012 US3, research R4).

Switch values come from the real build first: `config.status` (automake conditionals `S["X_TRUE"]=""` = on,
`"#"` = off), the `configure` command line recorded in `config.log`, the generated `config.h` (`#define` /
`/* #undef */`) and `-D` / `-U` of the variant's compile database (read in `classify/variants.py`). The user only
names, keeps or removes variants and sets switches the build does not reveal.
"""
from __future__ import annotations

import json
import os
import re
import shlex
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_CS_COND = re.compile(r'^S\["([A-Za-z_][A-Za-z0-9_]*)_(TRUE|FALSE)"\]="(#?)"', re.M)
_CFG_LOG_CMD = re.compile(r"^\s*\$\s+(\S*configure)\s*(.*)$", re.M)
_DEFINE = re.compile(r"^\s*#\s*define\s+([A-Za-z_]\w*)(?:\s+(.*?))?\s*$", re.M)
_UNDEF = re.compile(r"^\s*/\*\s*#\s*undef\s+([A-Za-z_]\w*)\s*\*/", re.M)


def configure_options(argv: list[str]) -> dict[str, Any]:
    """`--enable-x` / `--disable-x` / `--with-y=v` / `--without-y` → {"--enable-x": True|False, "--with-y": "v"}."""
    out: dict[str, Any] = {}
    for a in argv:
        m = re.match(r"^--(enable|disable|with|without)-([A-Za-z0-9_-]+)(?:=(.*))?$", a)
        if not m:
            continue
        kind, name, val = m.groups()
        key = f"--{'enable' if kind in ('enable', 'disable') else 'with'}-{name}"
        if kind in ("disable", "without"):
            out[key] = False
        else:
            out[key] = True if val in (None, "yes") else (False if val == "no" else val)
    return out


def build_values(repo: Path, variant: dict[str, Any]) -> dict[str, Any]:
    """Switch values a variant's build directory reveals (AM:*, --enable-*, config.h macros)."""
    vals: dict[str, Any] = {}
    bdir = variant.get("build_dir")
    if not bdir:
        return vals
    b = Path(bdir) if Path(bdir).is_absolute() else repo / bdir
    cs = b / "config.status"
    if cs.is_file():
        text = cs.read_text(encoding="utf-8", errors="replace")
        for name, which, hashmark in _CS_COND.findall(text):
            if which == "TRUE":
                vals[f"AM:{name}"] = hashmark == ""
    log = b / "config.log"
    if log.is_file():
        m = _CFG_LOG_CMD.search(log.read_text(encoding="utf-8", errors="replace"))
        if m:
            try:
                vals.update(configure_options(shlex.split(m.group(2))))
            except ValueError:
                pass
    for h in _config_headers(repo, b):
        text = h.read_text(encoding="utf-8", errors="replace")
        for name in _UNDEF.findall(text):
            vals.setdefault(name, False)
        for name, body in _DEFINE.findall(text):
            vals[name] = body if body else "1"
    return vals


def _config_headers(repo: Path, bdir: Path) -> list[Path]:
    from tcadvisor.index.automake import read_configure
    names = read_configure(repo).config_headers or ["config.h"]
    return [bdir / n for n in names if (bdir / n).is_file()]


def _candidates(repo: Path, recipe: str | None = None) -> list[dict[str, Any]]:
    """Build directories / compile databases found in the usual places."""
    found: list[dict[str, Any]] = []
    for d in sorted(repo.iterdir()) if repo.is_dir() else []:
        if d.is_dir() and not d.name.startswith(".") and (d / "config.status").is_file():
            v = {"name": re.sub(r"[^A-Za-z0-9._-]", "-", d.name), "build_dir": d.relative_to(repo).as_posix()}
            if (d / "compile_commands.json").is_file():
                v["compile_db"] = f"{v['build_dir']}/compile_commands.json"
            found.append(v)
    tb = repo / ".tcadvisor" / "build"
    for d in sorted(tb.iterdir()) if tb.is_dir() else []:
        if (d / "compile_commands.json").is_file():
            found.append({"name": d.name, "compile_db": (d / "compile_commands.json").relative_to(repo).as_posix()})
    bb = os.environ.get("BUILDDIR")
    if bb and Path(bb).is_dir():
        name = recipe or repo.name
        for w in sorted(Path(bb).glob(f"tmp*/work/*/{name}/*")):
            log = w / "temp" / "log.do_compile"
            if log.is_file():
                arch = w.parent.parent.name
                b = w / "build" if (w / "build").is_dir() else w
                found.append({"name": re.sub(r"[^A-Za-z0-9._-]", "-", f"{arch}"), "build_log": str(log),
                              "build_dir": str(b)})
    return found


def detect(repo: Path, cfg: dict[str, Any]) -> dict[str, Any]:
    """Proposal shown to the user (`tcadvisor profile --detect --json`)."""
    from tcadvisor.index.automake import detect_build_system, load_automake_model
    repo = repo.resolve()
    system = cfg.get("build_system") if cfg.get("build_system") not in (None, "auto") else (
        detect_build_system(repo) or "cmake")
    switches: list[dict[str, Any]] = []
    fingerprint = None
    if system == "autotools":
        m = load_automake_model(repo)
        fingerprint = m.fingerprint
        conf = "configure.ac" if (repo / "configure.ac").is_file() else "configure.in"
        switches += [{"name": f"AM:{n}", "kind": "am_conditional", "declared_at": f"{conf}:{ln}"}
                     for n, ln in sorted(m.configure.am_conditionals.items())]
        switches += [{"name": n, "kind": "configure_option", "declared_at": f"{conf}:{ln}"}
                     for n, ln in sorted(m.configure.enables.items())]
        switches += [{"name": n, "kind": "macro", "declared_at": f"{conf}:{ln}"}
                     for n, ln in sorted(m.configure.defines.items())]
    existing = {v["name"]: dict(v) for v in ((cfg.get("build") or {}).get("variants") or [])}
    for c in _candidates(repo):
        existing.setdefault(c["name"], c)
    variants = list(existing.values()) or [{"name": "default"}]
    for v in variants:
        bv = build_values(repo, v)
        user = {k: x for k, x in (v.get("values") or {}).items() if (v.get("value_source") or {}).get(k) == "user"}
        v["values"] = {s["name"]: user.get(s["name"], bv.get(s["name"])) for s in switches}
        v["values"].update({k: x for k, x in bv.items() if k not in v["values"]})
        v["value_source"] = {k: ("user" if k in user else "build") for k, x in v["values"].items() if x is not None}
    return {"system": system, "fingerprint": fingerprint, "switches": switches, "variants": variants,
            "unset": {v["name"]: [s["name"] for s in switches if v["values"].get(s["name"]) is None]
                      for v in variants}}


def save_profile(repo: Path, data: dict[str, Any], cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    """Validate and store a confirmed profile (`build` key)."""
    from tcadvisor.config import check_build_profile, config_path, update_file
    variants = data.get("variants")
    prof = {"system": data.get("system", "auto"), "confirmed": True,
            "confirmed_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            **({"fingerprint": data["fingerprint"]} if data.get("fingerprint") else {}),
            "variants": [{k: x for k, x in v.items() if k in ("name", "compile_db", "build_log", "log_sha256",
                                                              "build_dir", "values", "value_source")}
                         for v in variants or []]}
    for v in prof["variants"]:
        if "values" in v:
            v["values"] = {k: x for k, x in v["values"].items() if x is not None}
            v["value_source"] = {k: s for k, s in (v.get("value_source") or {}).items() if k in v["values"]}
    check_build_profile(config_path(repo), prof)

    def put(d: dict) -> None:
        d["build"] = prof
    update_file(repo, put)
    return prof


def profile_state(repo: Path, prof: dict[str, Any] | None) -> str:
    """absent | unconfirmed | confirmed | stale (build description changed since confirmation)."""
    if not prof:
        return "absent"
    if not prof.get("confirmed"):
        return "unconfirmed"
    fp = prof.get("fingerprint")
    if fp:
        from tcadvisor.index.automake import detect_build_system, load_automake_model
        if detect_build_system(repo) == "autotools" and load_automake_model(repo).fingerprint != fp:
            return "stale"
    return "confirmed"


def _ask(prompt: str, default: str = "") -> str:
    sys.stderr.write(prompt)
    sys.stderr.flush()
    ans = sys.stdin.readline()
    if not ans:
        return default
    return ans.strip() or default


def _parse_value(text: str) -> Any:
    t = text.strip()
    if t.lower() in ("y", "yes", "on", "true", "1"):
        return True if not t.isdigit() else "1"
    if t.lower() in ("n", "no", "off", "false", "undef", "0"):
        return False if not t.isdigit() else "0"
    return t or None


def confirm_interactively(repo: Path, cfg: dict[str, Any]) -> dict[str, Any] | None:
    """Terminal dialog: show the detected build flow, keep / rename / remove variants, set unknown switch values,
    save. Returns the saved profile (None when the user declines)."""
    p = detect(repo, cfg)
    w = sys.stderr.write
    w(f"\nBuild flow of {repo.resolve().name}: {p['system']}"
      + (f", {len(p['switches'])} switch(es)" if p["switches"] else "") + "\n")
    for s in p["switches"]:
        w(f"  switch {s['name']} ({s['kind']}, {s['declared_at']})\n")
    kept = []
    for v in p["variants"]:
        src = v.get("compile_db") or v.get("build_log") or v.get("build_dir") or "no build information yet"
        known = {k: x for k, x in v["values"].items() if x is not None}
        w(f"\nVariant '{v['name']}' ({src}); known values: "
          + (", ".join(f"{k}={x}" for k, x in sorted(known.items())[:12]) or "none") + "\n")
        if _ask("  Is this variant built and shipped? [Y/n] ", "y").lower().startswith("n"):
            continue
        name = _ask(f"  Name [{v['name']}]: ", v["name"])
        v["name"] = re.sub(r"[^A-Za-z0-9._-]", "-", name)
        for s in [x["name"] for x in p["switches"] if v["values"].get(x["name"]) is None]:
            val = _parse_value(_ask(f"  {s} in this variant? (y/n/value, empty = unknown) ", ""))
            if val is not None:
                v["values"][s] = val
                v.setdefault("value_source", {})[s] = "user"
        kept.append(v)
    if not kept:
        w("No variant confirmed: nothing is filtered. Run `tcadvisor profile` again later.\n")
        return None
    if not _ask(f"\nSave this profile ({', '.join(v['name'] for v in kept)}) to .tcadvisor/config.json? [Y/n] ",
                "y").lower().startswith("n"):
        prof = save_profile(repo, {**p, "variants": kept}, cfg)
        w("Saved. Cases on code not built in any of these variants will be listed separately.\n")
        return prof
    return None


def proposal_json(repo: Path, cfg: dict[str, Any]) -> str:
    return json.dumps(detect(repo, cfg), indent=2, ensure_ascii=False)
