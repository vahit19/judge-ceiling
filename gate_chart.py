"""
Renders the gate sweep: what a quality screen reports when nothing is wrong.

One chart, one claim. The horizontal rule is the reliability the rows were
built with, so it is the only correct answer at every threshold. Both series
sit above it and climb as the screen tightens.

Design notes, so the next person does not re-litigate them:

  - Two series, so they are directly labelled at the right rather than given a
    legend. Continuous is the primary series (#2a78d6); the five-point scale is
    the same hue at lower chroma (#7fa9dd), because it is the same measurement
    on a different scale and not a different quantity.
  - The truth line is drawn in the alert colour (#a5342a) and labelled on the
    axis. It is the reference the reader has to hold, so it is the one element
    that is not blue.
  - Bootstrap intervals are drawn as a band, not as caps. Caps at six x
    positions read as a grid; a band reads as one uncertainty.
  - The x axis is threshold tightness, which runs the opposite way to the
    numbers: "off" on the left, 1.0 sd on the right. Labelled in words so the
    direction is not something the reader has to infer.

Usage:
    python gate_chart.py
"""

import io
import os

from poison import gate_sweep

HERE = os.path.dirname(os.path.abspath(__file__))

CONT      = "#2a78d6"
LIKERT    = "#7fa9dd"
TRUTH     = "#a5342a"
SURFACE   = "#fcfcfb"
TEXT      = "#0b0b0b"
TEXT_2    = "#52514e"
TEXT_MUTE = "#8a8984"
GRID      = "#e6e6e3"

W, H = 780, 430
LEFT, RIGHT, TOP, BOTTOM = 62, 188, 30, 62
Y_MIN, Y_MAX = 0.30, 0.90

Z_VALUES = (None, 3.0, 2.5, 2.0, 1.5, 1.0)
LABELS = ("off", "3.0 sd", "2.5 sd", "2.0 sd", "1.5 sd", "1.0 sd")


def _band(pts_lo, pts_hi, colour, opacity):
    d = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts_lo)
    d += " " + " ".join(f"{x:.1f},{y:.1f}" for x, y in reversed(pts_hi))
    return f'<polygon points="{d}" fill="{colour}" opacity="{opacity}"/>'


def render(out_name="gate_chart.svg", built=0.45, seeds=12, resamples=300):
    cont = gate_sweep(z_values=Z_VALUES, rho_1=built, seeds=seeds,
                      resamples=resamples)
    lik = gate_sweep(z_values=Z_VALUES, rho_1=built, seeds=seeds,
                     scale=(1, 5), resamples=resamples)

    plot_w = W - LEFT - RIGHT
    plot_h = H - TOP - BOTTOM
    n = len(Z_VALUES)
    px = lambda i: LEFT + (i / (n - 1)) * plot_w
    py = lambda v: TOP + plot_h - (v - Y_MIN) / (Y_MAX - Y_MIN) * plot_h

    o = [f'<svg viewBox="0 0 {W} {H}" width="100%" role="img" '
         f'aria-label="Reported single-rater reliability against outlier-screen '
         f'tightness, on clean data, with the built value marked" '
         f'style="font-family:Consolas,ui-monospace,monospace">',
         f'<rect width="{W}" height="{H}" fill="{SURFACE}"/>']

    # horizontal grid and y labels
    v = Y_MIN
    while v <= Y_MAX + 1e-9:
        gy = py(v)
        o.append(f'<line x1="{LEFT}" y1="{gy:.1f}" x2="{LEFT+plot_w}" y2="{gy:.1f}" '
                 f'stroke="{GRID}" stroke-width="1"/>')
        o.append(f'<text x="{LEFT-10}" y="{gy+4:.1f}" fill="{TEXT_MUTE}" '
                 f'font-size="10.5" text-anchor="end">{v:.1f}</text>')
        v += 0.1

    # the only correct answer
    ty = py(built)
    o.append(f'<line x1="{LEFT}" y1="{ty:.1f}" x2="{LEFT+plot_w}" y2="{ty:.1f}" '
             f'stroke="{TRUTH}" stroke-width="1.6" stroke-dasharray="5 4"/>')
    o.append(f'<text x="{LEFT+plot_w+10}" y="{ty+4:.1f}" fill="{TRUTH}" '
             f'font-size="11.5" font-weight="600">built at {built}</text>')
    o.append(f'<text x="{LEFT+plot_w+10}" y="{ty+19:.1f}" fill="{TRUTH}" '
             f'font-size="10">the only correct answer</text>')

    # Series labels sit at each line's right-hand end, which collide when the
    # two series finish close together -- they do here, 0.818 against 0.802.
    # Push them apart around their midpoint rather than nudging one, so neither
    # label ends up further from its own line than the other.
    ends = {"cont": py(cont[-1]["reported"]), "lik": py(lik[-1]["reported"])}
    need = 34.0
    if abs(ends["cont"] - ends["lik"]) < need:
        mid = (ends["cont"] + ends["lik"]) / 2
        hi_key = min(ends, key=ends.get)          # smaller y = higher up
        lo_key = max(ends, key=ends.get)
        ends[hi_key] = mid - need / 2
        ends[lo_key] = mid + need / 2

    for rows, colour, name, op, key in (
            (lik, LIKERT, "five-point scale", 0.16, "lik"),
            (cont, CONT, "continuous scores", 0.14, "cont")):
        lo = [(px(i), py(r["lo"])) for i, r in enumerate(rows) if r.get("lo")]
        hi = [(px(i), py(r["hi"])) for i, r in enumerate(rows) if r.get("hi")]
        if len(lo) == len(rows):
            o.append(_band(lo, hi, colour, op))

        pts = " ".join(f"{px(i):.1f},{py(r['reported']):.1f}"
                       for i, r in enumerate(rows))
        o.append(f'<polyline points="{pts}" fill="none" stroke="{colour}" '
                 f'stroke-width="2.4" stroke-linejoin="round"/>')
        for i, r in enumerate(rows):
            o.append(f'<circle cx="{px(i):.1f}" cy="{py(r["reported"]):.1f}" '
                     f'r="3.4" fill="{colour}"/>')

        last = rows[-1]
        ly = ends[key]
        # A leader line, because the label has been moved off its own endpoint.
        if abs(ly - py(last["reported"])) > 1.0:
            o.append(f'<path d="M{LEFT+plot_w+3:.1f} {py(last["reported"]):.1f} '
                     f'L{LEFT+plot_w+7:.1f} {ly:.1f}" stroke="{colour}" '
                     f'stroke-width="1" fill="none" opacity="0.55"/>')
        o.append(f'<text x="{LEFT+plot_w+10}" y="{ly+4:.1f}" '
                 f'fill="{colour}" font-size="11.5" font-weight="600">{name}</text>')
        over = last["reported"] / built - 1.0
        o.append(f'<text x="{LEFT+plot_w+10}" y="{ly+18:.1f}" '
                 f'fill="{TEXT_MUTE}" font-size="10">{over:+.0%} at 1.0 sd</text>')

    # x labels, with how much each threshold deletes
    for i, label in enumerate(LABELS):
        o.append(f'<text x="{px(i):.1f}" y="{H-BOTTOM+20}" fill="{TEXT}" '
                 f'font-size="11" text-anchor="middle">{label}</text>')
        o.append(f'<text x="{px(i):.1f}" y="{H-BOTTOM+34}" fill="{TEXT_MUTE}" '
                 f'font-size="9.5" text-anchor="middle">'
                 f'&#8722;{cont[i]["dropped"]:.0%}</text>')

    o.append(f'<line x1="{LEFT}" y1="{TOP}" x2="{LEFT}" y2="{H-BOTTOM}" '
             f'stroke="{TEXT_2}" stroke-width="1.5"/>')
    o.append(f'<line x1="{LEFT}" y1="{H-BOTTOM}" x2="{LEFT+plot_w}" y2="{H-BOTTOM}" '
             f'stroke="{TEXT_2}" stroke-width="1.5"/>')
    o.append(f'<text x="{LEFT}" y="{TOP-12}" fill="{TEXT_2}" font-size="11">'
             f'REPORTED &#961;&#8321; on data with nothing wrong with it '
             f'&#8212; band: 95% bootstrap over items</text>')
    o.append(f'<text x="{LEFT+plot_w/2:.0f}" y="{H-10}" fill="{TEXT_2}" '
             f'font-size="11" text-anchor="middle">OUTLIER SCREEN, from off to '
             f'aggressive &#8212; below each label, the share of ratings deleted</text>')
    o.append("</svg>")

    svg = "\n".join(o)
    io.open(os.path.join(HERE, out_name), "w", encoding="utf-8").write(svg)
    print(f"wrote {out_name}  ({W}x{H}, {seeds} seeds, {resamples} resamples)")
    return svg


if __name__ == "__main__":
    render()
