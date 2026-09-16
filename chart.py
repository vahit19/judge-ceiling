"""
Renders the bounds as an SVG bar chart.

Colour note: the series colour is #2a78d6. A darker teal (#0f6f65) was tried
first and rejected -- it falls below the chroma floor for a data mark and
reads as grey. Single series, so no legend; every bar is directly labelled.
"""

import io
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))

SERIES    = "#2a78d6"
SURFACE   = "#fcfcfb"
TEXT      = "#0b0b0b"
TEXT_2    = "#52514e"
TEXT_MUTE = "#8a8984"
GRID      = "#e6e6e3"

W, LEFT, RIGHT = 760, 232, 78
BAR, GAP, TOP, BOTTOM = 20, 12, 16, 38
AXIS_MAX = 0.55

SHORTEN = {
    "Extended Long-Form Speaker Stability": "Extended Long-Form Stability",
    "Long-form Speaker Stability": "Long-form Stability",
}


def render(out_name="ceiling_chart.svg"):
    data = json.load(io.open(os.path.join(HERE, "leaderboard.json"), encoding="utf-8"))
    rows = []
    for name, judges in data.items():
        r = max(x["score"] for x in judges)
        rows.append((SHORTEN.get(name, name), r, r * r))
    rows.sort(key=lambda x: -x[2])

    plot = W - LEFT - RIGHT
    H = TOP + len(rows) * (BAR + GAP) - GAP + BOTTOM
    x = lambda v: LEFT + v / AXIS_MAX * plot

    # xmlns is required for a standalone file. Without it the chart renders
    # when pasted inline into HTML and silently fails when loaded through an
    # <img>, which is how a README shows it. Explicit width and height give
    # the image the intrinsic size a percentage width does not.
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" '
         f'width="{W}" height="{H}" role="img" '
         f'aria-label="Lower bound on single-rater reliability implied by each '
         f'dimension\'s best published judge score" '
         f'style="max-width:100%;height:auto;'
         f'font-family:Consolas,ui-monospace,monospace">',
         f'<rect width="{W}" height="{H}" fill="{SURFACE}"/>']

    t = 0.0
    while t <= AXIS_MAX + 1e-9:
        gx = x(t)
        o.append(f'<line x1="{gx:.1f}" y1="{TOP-6}" x2="{gx:.1f}" y2="{H-BOTTOM+4}" '
                 f'stroke="{GRID}" stroke-width="1"/>')
        o.append(f'<text x="{gx:.1f}" y="{H-BOTTOM+20}" fill="{TEXT_MUTE}" '
                 f'font-size="10.5" text-anchor="middle">{t:.1f}</text>')
        t += 0.1

    for i, (name, r, bound) in enumerate(rows):
        y = TOP + i * (BAR + GAP)
        w = x(bound) - LEFT
        # 4px rounded data end, anchored to the baseline
        o.append(f'<path d="M{LEFT} {y} h{max(w-4,0):.1f} a4,4 0 0 1 4,4 '
                 f'v{BAR-8} a4,4 0 0 1 -4,4 H{LEFT} Z" fill="{SERIES}"/>')
        o.append(f'<text x="{LEFT-12}" y="{y+BAR-6}" fill="{TEXT}" font-size="12" '
                 f'text-anchor="end">{name}</text>')
        o.append(f'<text x="{x(bound)+8:.1f}" y="{y+BAR-6}" fill="{TEXT}" '
                 f'font-size="12" font-weight="600">{bound:.3f}</text>')
        o.append(f'<text x="{LEFT-12}" y="{y+BAR+5}" fill="{TEXT_MUTE}" font-size="9" '
                 f'text-anchor="end">published r = {r:.4f}</text>')

    o.append(f'<line x1="{LEFT}" y1="{TOP-6}" x2="{LEFT}" y2="{H-BOTTOM+4}" '
             f'stroke="{TEXT_2}" stroke-width="1.5"/>')
    o.append(f'<text x="{LEFT + plot/2:.0f}" y="{H-6}" fill="{TEXT_2}" font-size="11" '
             f'text-anchor="middle">LOWER BOUND on single-rater reliability '
             f'&#961;&#8321; (= r&#178;)</text>')
    o.append("</svg>")

    svg = "\n".join(o)
    io.open(os.path.join(HERE, out_name), "w", encoding="utf-8").write(svg)
    print(f"wrote {out_name}  ({len(rows)} dimensions, {W}x{H})")
    return svg


if __name__ == "__main__":
    render()
