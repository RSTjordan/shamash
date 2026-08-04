"""Build the brand marks as square PNGs (profile pictures, social, favicons).

Three marks, 1024x1024 each:
  shamash-robot-candle-warm.png  the attendant robot lit by the candle it tends
  shamash-candle-warm.png        the candle alone
  shamash-robot-candle-dark.png  the same robot on the deep ground, for dark UI

The warm pair sits on the terracotta of the agent's existing avatar. That is
deliberate: a lone flame on a black ground reads as a memorial candle, and this
is a working assistant, not a yahrzeit. Use the warm marks for profile pictures
and the dark one only where the surrounding UI is already dark.

Everything sits inside the central 84% so a circular crop (WhatsApp, GitHub)
never clips it. Rendered with headless Edge/Chrome — same dependency as
build_welcome.py, nothing new to install.

Usage:  python scripts/build_brand.py [size]
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "brand"

BROWSERS = [
    Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
    Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
    Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
]

DEFS = """
<defs>
  <radialGradient id="bgDark" cx="50%" cy="62%" r="72%">
    <stop offset="0%"  stop-color="#242a3d"/>
    <stop offset="60%" stop-color="#12141d"/>
    <stop offset="100%" stop-color="#0b0d12"/>
  </radialGradient>
  <!-- The terracotta of the agent's existing avatar. A candle glowing in the
       dark reads as a memorial candle; the same candle on warm terracotta
       does not. Anything used as a profile picture uses this one. -->
  <radialGradient id="bgWarm" cx="50%" cy="45%" r="78%">
    <stop offset="0%"  stop-color="#e08a63"/>
    <stop offset="55%" stop-color="#d2795b"/>
    <stop offset="100%" stop-color="#bd6748"/>
  </radialGradient>
  <radialGradient id="haloDark" cx="50%" cy="50%" r="50%">
    <stop offset="0%"   stop-color="#e8a33d" stop-opacity=".42"/>
    <stop offset="45%"  stop-color="#e8a33d" stop-opacity=".13"/>
    <stop offset="100%" stop-color="#e8a33d" stop-opacity="0"/>
  </radialGradient>
  <radialGradient id="haloWarm" cx="50%" cy="50%" r="50%">
    <stop offset="0%"   stop-color="#fff2d2" stop-opacity=".62"/>
    <stop offset="42%"  stop-color="#ffe3ad" stop-opacity=".22"/>
    <stop offset="100%" stop-color="#ffe3ad" stop-opacity="0"/>
  </radialGradient>
  <linearGradient id="flame" x1="140" y1="162" x2="140" y2="230"
                  gradientUnits="userSpaceOnUse">
    <stop stop-color="#ffe0a0"/><stop offset=".5" stop-color="#e8a33d"/>
    <stop offset="1" stop-color="#d4762a"/>
  </linearGradient>
  <linearGradient id="lit" x1="140" y1="30" x2="140" y2="154"
                  gradientUnits="userSpaceOnUse">
    <stop stop-color="#0e1016" stop-opacity=".40"/>
    <stop offset=".55" stop-color="#0e1016" stop-opacity="0"/>
    <stop offset="1" stop-color="#e8a33d" stop-opacity=".5"/>
  </linearGradient>
  <linearGradient id="wax" x1="124" y1="224" x2="156" y2="224"
                  gradientUnits="userSpaceOnUse">
    <stop stop-color="#fff6e4"/><stop offset=".55" stop-color="#f0e2c8"/>
    <stop offset="1" stop-color="#cbb99a"/>
  </linearGradient>
</defs>
"""

# Candle drawn in the same coordinate space as the welcome cover, so the two
# marks stay identical where they overlap.
CANDLE = """
<rect x="120" y="224" width="40" height="62" rx="6" fill="url(#wax)"/>
<rect x="112" y="280" width="56" height="10" rx="5" fill="#b39d7e"/>
<path d="M140 162c13 19 23 28 23 43a23 23 0 1 1-46 0c0-15 10-24 23-43z"
      fill="url(#flame)"/>
<path d="M140 188c6.5 10 11.5 15 11.5 22a11.5 11.5 0 1 1-23 0c0-7 5-12 11.5-22z"
      fill="#fff5da" opacity=".95"/>
"""

ROBOT = """
<g stroke="#14151a" stroke-width="8">
  <rect x="46" y="74" width="24" height="46" rx="12" fill="#b9bcc2"/>
  <rect x="210" y="74" width="24" height="46" rx="12" fill="#b9bcc2"/>
  <rect x="136" y="14" width="8" height="24" fill="#8d939c" stroke-width="0"/>
  <circle cx="140" cy="12" r="8.5" fill="#d64545" stroke="#8d939c" stroke-width="4"/>
  <rect x="70" y="30" width="140" height="124" rx="28" fill="#cbced3"/>
  <rect x="70" y="30" width="140" height="124" rx="28" fill="url(#lit)" stroke-width="0"/>
  <circle cx="112" cy="84" r="12" fill="#fff" stroke-width="7"/>
  <circle cx="168" cy="84" r="12" fill="#fff" stroke-width="7"/>
  <rect x="96" y="110" width="88" height="30" rx="14" fill="#fff" stroke-width="7"/>
  <path d="M118 110v30M140 110v30M162 110v30" stroke-width="7"/>
</g>
"""

# name -> (background, viewBox, halo radius+centre, body). The candle-only mark
# zooms in with a tighter viewBox rather than by rescaling the art, so the two
# marks stay pixel-identical where they overlap.
MARKS = {
    # profile-picture candidates — warm ground, unmistakably not a memorial candle
    "shamash-robot-candle-warm": (
        "warm", "20 -6 240 305", ("140", "205", "150"), ROBOT + CANDLE,
    ),
    "shamash-candle-warm": (
        "warm", "60 140 160 175", ("140", "212", "118"), CANDLE,
    ),
    # the dark mark, for the document cover / GitHub / anywhere on dark UI
    "shamash-robot-candle-dark": (
        "dark", "20 -6 240 305", ("140", "205", "150"), ROBOT + CANDLE,
    ),
}

PAGE = """<!DOCTYPE html><html><head><meta charset="utf-8"><style>
html,body{{margin:0;padding:0;background:#0b0d12;overflow:hidden}}
svg{{display:block;width:{size}px;height:{size}px}}
</style></head><body>
<svg viewBox="0 0 100 100" preserveAspectRatio="xMidYMid slice"
     xmlns="http://www.w3.org/2000/svg">
  {defs}
  <rect x="0" y="0" width="100" height="100" fill="url(#bg{ground})"/>
  <svg viewBox="{vb}" x="8" y="8" width="84" height="84" overflow="visible">
    <circle cx="{hx}" cy="{hy}" r="{hr}" fill="url(#halo{ground})"/>
    {body}
  </svg>
</svg></body></html>"""


def main() -> int:
    size = int(sys.argv[1]) if len(sys.argv) > 1 else 1024
    browser = next((b for b in BROWSERS if b.exists()), None)
    if browser is None:
        print("No Edge or Chrome found.")
        return 1

    OUT.mkdir(parents=True, exist_ok=True)
    failed = False

    for name, (ground, vb, (hx, hy, hr), body) in MARKS.items():
        html = OUT / f"{name}.html"
        png = OUT / f"{name}.png"
        html.write_text(
            PAGE.format(
                size=size, defs=DEFS, vb=vb, body=body,
                ground="Warm" if ground == "warm" else "Dark",
                hx=hx, hy=hy, hr=hr,
            ),
            encoding="utf-8",
        )
        if png.exists():
            png.unlink()
        subprocess.run(
            [str(browser), "--headless", "--disable-gpu", "--hide-scrollbars",
             f"--screenshot={png}", f"--window-size={size},{size}",
             "--force-device-scale-factor=1", html.as_uri()],
            check=True, capture_output=True, timeout=120,
        )
        html.unlink(missing_ok=True)
        if not png.exists() or png.stat().st_size < 5000:
            print(f"FAILED {png}")
            failed = True
        else:
            print(f"OK  {png}  ({png.stat().st_size // 1024} KB, {size}px)")

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
