"""Report-language coverage: which pipeline sentences of the given reports have no translation.

  python3 scripts/l10n_check.py [--lang vi] REPORT_GLOB...   (exit 1 when any sentence is untranslated)
"""
from __future__ import annotations

import argparse
import glob
import json
import re
import sys
from collections import Counter

from tcadvisor.report.l10n import Translator, localize


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lang", default="vi")
    ap.add_argument("--limit", type=int, default=200)
    ap.add_argument("reports", nargs="+")
    a = ap.parse_args()
    T, n = Translator(a.lang), 0
    for pattern in a.reports:
        for p in sorted(glob.glob(pattern, recursive=True)):
            localize(json.loads(open(p, encoding="utf-8").read()), T)
            n += 1
    misses = T.misses()
    shapes = Counter()
    example = {}
    for text, k in misses.items():
        shape = re.sub(r"\d+", "N", re.sub(r"`[^`]*`", "`X`", text))
        shapes[shape] += k
        example.setdefault(shape, text)
    print(f"{n} report(s); {len(misses)} untranslated sentence(s) in {len(shapes)} shape(s)")
    for shape, k in shapes.most_common(a.limit):
        print(f"{k:6d}  {example[shape][:300]}")
    return 1 if misses else 0


if __name__ == "__main__":
    sys.exit(main())
