"""Fail the build if any relative link in the rendered site does not resolve.

A broken relative link renders perfectly and 404s only when someone clicks it,
so it cannot be caught by looking at the page. The site is a few dozen files,
so checking all of them costs nothing.
"""

import re
import sys
from pathlib import Path
from urllib.parse import urldefrag

EXTERNAL = ("http://", "https://", "#", "mailto:")


def main(root: Path) -> int:
    pages = sorted(root.rglob("*.html"))
    if not pages:
        print(f"error: no HTML found under {root}", file=sys.stderr)
        return 1

    checked = broken = skipped = 0
    for page in pages:
        for href in re.findall(r'href="([^"]+)"', page.read_text()):
            if href.startswith(EXTERNAL):
                skipped += 1
                continue
            if href.startswith("/"):
                # Root-relative links break under a project page's base path.
                print(f"root-relative: {page.relative_to(root)} -> {href}")
                broken += 1
                continue
            target, _ = urldefrag(href)
            checked += 1
            if not (page.parent / target).resolve().exists():
                print(f"broken: {page.relative_to(root)} -> {href}")
                broken += 1

    print(f"{len(pages)} pages, {checked} relative links checked, {skipped} external")
    if broken:
        print(f"error: {broken} links do not resolve", file=sys.stderr)
        return 1
    print("all internal links resolve")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1] if len(sys.argv) > 1 else "site")))
