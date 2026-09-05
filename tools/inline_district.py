"""Inject landing/data/district.json into landing/simulation.html.

The simulation must open by double-clicking the file, with no server: a jury
laptop has no localhost and often no wifi. fetch() is blocked under file://, so
the district data lives inline. This keeps the JSON the single source of truth
and makes the embed reproducible instead of a one-off paste.

Usage: python tools/inline_district.py [district.json] [simulation.html]
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

TAG_OPEN = '<script type="application/json" id="districtData">'
TAG_CLOSE = "</script>"


def main(argv: list[str]) -> int:
    data = Path(argv[1] if len(argv) > 1 else "landing/data/district.json")
    page = Path(argv[2] if len(argv) > 2 else "landing/simulation.html")
    payload = data.read_text(encoding="utf-8").strip()
    if "</script" in payload:
        raise SystemExit("в данных есть </script — встраивать нельзя")

    html = page.read_text(encoding="utf-8")
    pattern = re.compile(re.escape(TAG_OPEN) + r".*?" + re.escape(TAG_CLOSE), re.S)
    if not pattern.search(html):
        raise SystemExit(f"в {page} нет блока {TAG_OPEN}")
    html = pattern.sub(lambda _m: TAG_OPEN + payload + TAG_CLOSE, html, count=1)
    page.write_text(html, encoding="utf-8")
    print(f"встроено {len(payload)/1024:.0f} КБ данных в {page} "
          f"({page.stat().st_size/1024:.0f} КБ всего)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
