"""Build the README artwork from the two places the visuals already live:
the landing page (site/index.html) and the welcome document
(docs/welcome/welcome.html).

Nothing is redrawn here. The lit-phone scene and the architecture diagram are
LIFTED from their sources, so a change to the site or the welcome PDF shows up
in the README on the next build instead of quietly drifting out of date.

  docs/brand/readme/hero-chat.png    the signature phone, from the landing page
  docs/brand/readme/architecture.svg the four-box diagram, from the welcome doc

The phone is a screenshot because it is CSS: gradients, a breathing glow, real
WhatsApp bubble geometry. The diagram is already an SVG, so it is copied as
one — crisp at any size, and a tenth of the bytes of a PNG.

Usage:  py -3 scripts/build_readme_art.py
"""

import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site" / "index.html"
SITE_HE = ROOT / "site" / "he.html"
WELCOME = ROOT / "docs" / "welcome" / "welcome.html"
OUT_DIR = ROOT / "docs" / "brand" / "readme"

BROWSERS = [
    Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
    Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
    Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
    Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
]

# Wide enough for the mascot, which is positioned OUTSIDE the phone; tall
# enough for the caption, which hangs below it. Both would be cropped at the
# phone's own width.
SHOT_W, SHOT_H = 900, 700
SCALE = 2  # retina — GitHub serves it at half size and it stays sharp


def find_browser():
    return next((p for p in BROWSERS if p.exists()), None)


def extract_block(html: str, opening: str) -> str:
    """Return the element starting at `opening`, balanced to its own </div>.

    A regex cannot do this: the scene contains nested divs. Counting is the
    honest way, and the markup is well-formed because a browser prints it.
    """
    start = html.index(opening)
    depth, i = 0, start
    for m in re.finditer(r"<(/?)div\b[^>]*?(/?)>", html[start:]):
        if m.group(2) == "/":  # self-closing, ignore
            continue
        depth += -1 if m.group(1) else 1
        if depth == 0:
            return html[start : start + m.end()]
        i = m.end()
    raise ValueError(f"unbalanced markup after {opening!r} (stopped at {i})")


def build_hero(browser: Path, source: Path, out_name: str) -> Path:
    html = source.read_text(encoding="utf-8")
    style = re.search(r"<style>.*?</style>", html, re.S).group(0)
    scene = extract_block(html, '<div class="scene"')

    # The Hebrew page is RTL, and the bubbles are placed with logical
    # properties (margin-inline-start/end). Lose the direction and every
    # message stacks on the wrong side.
    root = re.search(r"<html[^>]*>", html).group(0)
    rtl = 'dir="rtl"' in root
    lang = 'lang="he" dir="rtl"' if rtl else 'lang="en"'

    # The shot renders from a temp dir, so site-relative image paths would
    # 404 into empty boxes. Point them at the real files.
    def absolutise(m):
        return f'src="{(source.parent / m.group(1)).as_uri()}"'

    scene = re.sub(r'src="([^"/:]+\.png)"', absolutise, scene)

    page = f"""<!doctype html><html {lang}><head><meta charset="utf-8">{style}
<style>
  /* The scene is normally a grid child of .hero. On its own it needs a stage:
     the site's night background, and room on all sides for the glow, the
     mascot and the caption that live outside the phone's own box. */
  body{{background:var(--night);display:flex;align-items:center;
        justify-content:center;width:{SHOT_W}px;height:{SHOT_H}px}}
  .stage{{width:520px;padding:40px 0 70px}}
  .scene .glow{{animation:none;opacity:1}}   /* freeze mid-breath */
</style></head><body><div class="stage">{scene}</div></body></html>"""

    tmp = Path(tempfile.mkdtemp(prefix="shamash-art-"))
    try:
        src = tmp / "hero.html"
        src.write_text(page, encoding="utf-8")
        out = OUT_DIR / out_name
        subprocess.run(
            [
                str(browser),
                "--headless",
                "--disable-gpu",
                "--hide-scrollbars",
                f"--screenshot={out}",
                f"--window-size={SHOT_W},{SHOT_H}",
                f"--force-device-scale-factor={SCALE}",
                # The bubbles arrive on a timer and the typing indicator fades
                # at 4s. Fast-forward past the choreography to the settled
                # frame — otherwise the shot catches a half-empty chat.
                "--virtual-time-budget=8000",
                src.as_uri(),
            ],
            check=True,
            capture_output=True,
            timeout=180,
        )
        return out
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def build_day(browser: Path) -> Path:
    """The 'A normal Tuesday' transcript — a whole day of the product in one
    picture, and the only asset here that shows the digest itself."""
    html = WELCOME.read_text(encoding="utf-8")

    # Anchor on the section: the welcome document has a SECOND .phone on its
    # last page (the five things to try), and a bare search would find
    # whichever happens to come first.
    section = html[html.index("A normal Tuesday") :]
    transcript = extract_block(section, '<div class="phone">')
    style = re.search(r"<style>.*?</style>", html, re.S).group(0)

    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">{style}
<style>
  /* Off the printed page the transcript has no column to sit in. Give it the
     welcome document's own text measure so the bubbles wrap where they do in
     the PDF, and its paper so it does not float on white. */
  body{{background:var(--paper);margin:0;padding:9mm 8mm;width:174mm}}
</style></head><body>{transcript}</body></html>"""

    tmp = Path(tempfile.mkdtemp(prefix="shamash-art-"))
    try:
        src = tmp / "day.html"
        src.write_text(page, encoding="utf-8")
        out = OUT_DIR / "a-normal-tuesday.png"
        subprocess.run(
            [
                str(browser),
                "--headless",
                "--disable-gpu",
                "--hide-scrollbars",
                f"--screenshot={out}",
                # 174mm at 96dpi, plus the padding above. Height is generous
                # and the result is trimmed to the ink below.
                f"--window-size=730,1180",
                f"--force-device-scale-factor={SCALE}",
                "--virtual-time-budget=6000",
                src.as_uri(),
            ],
            check=True,
            capture_output=True,
            timeout=180,
        )
        trim(out)
        return out
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def trim(png: Path, pad: int = 18) -> None:
    """Crop the flat paper margin a fixed window size leaves below the last
    bubble. Without this the README shows a tall band of nothing."""
    from PIL import Image, ImageChops

    im = Image.open(png).convert("RGB")
    bg = Image.new("RGB", im.size, im.getpixel((0, 0)))
    box = ImageChops.difference(im, bg).getbbox()
    if box is None:  # a blank render — leave it for the size check to catch
        return
    left, top, right, bottom = box
    w, h = im.size
    im.crop(
        (max(0, left - pad), max(0, top - pad),
         min(w, right + pad), min(h, bottom + pad))
    ).save(png)


def build_architecture() -> Path:
    html = WELCOME.read_text(encoding="utf-8")
    svg = re.search(r"<svg viewBox=\"0 0 640 300\".*?</svg>", html, re.S).group(0)

    # The travelling dot animates on screen and is hidden in print. In a
    # README it would be a smudge parked on one arrow, so it goes.
    svg = re.sub(r"<circle class=\"flowdot\".*?</circle>", "", svg, flags=re.S)

    # Standalone now, so it carries what the welcome page gave it: a real
    # width, and the paper it was drawn on (GitHub dark mode would otherwise
    # show black text on transparent).
    svg = svg.replace(
        '<svg viewBox="0 0 640 300" width="100%" style="margin:0 0 6mm">',
        # White, not the welcome page's off-white paper: the diagram masks its
        # own crossing lines with a #fff label patch, which would show as a
        # band against anything else.
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="-8 38 656 246" width="984">'
        '<rect x="-8" y="38" width="656" height="246" fill="#fff"/>',
    )

    out = OUT_DIR / "architecture.svg"
    out.write_text(svg, encoding="utf-8")
    return out


def main() -> int:
    for path in (SITE, SITE_HE, WELCOME):
        if not path.exists():
            print(f"missing source: {path}")
            return 1

    browser = find_browser()
    if browser is None:
        print("No Edge or Chrome found — cannot render the phone.")
        return 1

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    for src, name in ((SITE, "hero-chat.png"), (SITE_HE, "hero-chat.he.png")):
        hero = build_hero(browser, src, name)
        # A browser that fails to paint still exits 0 and leaves a tiny file.
        if not hero.exists() or hero.stat().st_size < 20_000:
            print(f"FAILED — {hero} is missing or suspiciously small")
            return 1
        print(f"OK  {hero}  ({hero.stat().st_size // 1024} KB)")

    day = build_day(browser)
    if not day.exists() or day.stat().st_size < 20_000:
        print(f"FAILED — {day} is missing or suspiciously small")
        return 1
    print(f"OK  {day}  ({day.stat().st_size // 1024} KB)")

    arch = build_architecture()
    print(f"OK  {arch}  ({arch.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
