"""Build the welcome document: docs/welcome/welcome.html -> Welcome-to-Shamash.pdf

The HTML is the source. It animates when opened in a browser (candle flicker,
cards rising, a dot travelling the architecture diagram) and prints flat and
clean to PDF — the @media print block hides what can't survive the crossing.

No pandoc, no LaTeX, no Node: Edge ships with Windows and prints headlessly.

Usage:  python scripts/build_welcome.py [output.pdf]
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "docs" / "welcome" / "welcome.html"
DEFAULT_OUT = ROOT / "docs" / "welcome" / "Welcome-to-Shamash.pdf"

EDGE_CANDIDATES = [
    Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
    Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
    Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
    Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
]


def find_browser() -> Path | None:
    return next((p for p in EDGE_CANDIDATES if p.exists()), None)


def main() -> int:
    out = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else DEFAULT_OUT

    if not SRC.exists():
        print(f"missing source: {SRC}")
        return 1

    browser = find_browser()
    if browser is None:
        print("No Edge or Chrome found — send docs/welcome/welcome.html instead.")
        return 1

    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        out.unlink()

    subprocess.run(
        [
            str(browser),
            "--headless",
            "--disable-gpu",
            "--no-pdf-header-footer",
            f"--print-to-pdf={out}",
            SRC.as_uri(),
        ],
        check=True,
        capture_output=True,
        timeout=180,
    )

    # A browser that fails to paint still exits 0 and leaves a near-empty file.
    if not out.exists() or out.stat().st_size < 50_000:
        print(f"FAILED — {out} is missing or suspiciously small")
        return 1

    print(f"OK  {out}  ({out.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
