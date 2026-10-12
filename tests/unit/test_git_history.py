from pathlib import Path

from tcadvisor.ingest import git as G


def test_fix_history_reads_a_utc_z_date(monkeypatch):
    """Recent git prints `%cI` in UTC as `...Z`, which Python 3.10's fromisoformat rejects."""
    calls = []

    def fake_git(repo, *args, check=True):
        calls.append(args)
        return "2026-10-12T06:41:22Z\n" if args[0] == "log" and "-1" in args else "src/a.cpp\n\nsrc/a.cpp\n"

    monkeypatch.setattr(G, "git", fake_git)
    assert G.fix_history(Path("."), "HEAD") == {"src/a.cpp": 2}
    assert any(a.startswith("--since=2025-10-17T06:41:22") for a in calls[1])
