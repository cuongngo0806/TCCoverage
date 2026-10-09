#!/usr/bin/env python3
"""Find "introducing -> fixing" commit pairs with the SZZ heuristic (git blame of the lines a fix removes).

  python3 scripts/szz_pairs.py --repo R [--since 2025-01-01] [--grep '^(fix|Fix)'] [--max 20] > pairs.txt
Only non-test C++ sources are blamed; formatting / mass-change commits (>200 files or subject matching
format|clang-format|rename|license) are ignored as introducers. Output lines: `<intro> -> <fix> | subject`.
"""
import argparse
import collections
import re
import subprocess

CPP = (".c", ".cc", ".cpp", ".cxx", ".h", ".hh", ".hpp", ".hxx", ".inl")
NOISE = re.compile(r"format|clang-tidy|rename|license|copyright|whitespace|version", re.I)


def git(repo, *a):
    return subprocess.run(["git", "-C", repo, *a], capture_output=True, text=True).stdout


def is_test(p):
    p = p.lower()
    return "test" in p


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--since", default="2025-01-01")
    ap.add_argument("--grep", default=r"^(fix|Fix|FIX)\b")
    ap.add_argument("--max", type=int, default=20)
    a = ap.parse_args()
    big = {}
    out = 0
    for line in git(a.repo, "log", f"--since={a.since}", "--no-merges", "--format=%h\t%s").splitlines():
        h, subj = line.split("\t", 1)
        if not re.search(a.grep, subj) or "test" in subj.lower() and "fix" not in subj.lower()[:4]:
            continue
        votes = collections.Counter()
        diff = git(a.repo, "diff", "-U0", "--no-color", f"{h}^", h)
        cur = None
        for dl in diff.splitlines():
            if dl.startswith("--- "):
                cur = dl[6:] if dl.startswith("--- a/") else None
                if cur and (not cur.endswith(CPP) or is_test(cur)):
                    cur = None
            m = re.match(r"^@@ -(\d+)(?:,(\d+))? ", dl)
            if m and cur:
                start, n = int(m.group(1)), int(m.group(2) or 1)
                if n == 0:
                    continue
                for bl in git(a.repo, "blame", "-l", "-s", "-L", f"{start},{start + n - 1}", f"{h}^", "--", cur).splitlines():
                    votes[bl.split()[0].lstrip("^")[:9]] += 1
        for intro, _n in votes.most_common():
            if intro not in big:
                files = git(a.repo, "show", "--name-only", "--format=%s", intro).splitlines()
                big[intro] = len(files) > 200 or bool(NOISE.search(files[0] if files else ""))
            if not big[intro]:
                print(f"{intro} -> {h} | {subj}")
                out += 1
                break
        if out >= a.max:
            break


if __name__ == "__main__":
    main()
