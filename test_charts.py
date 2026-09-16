"""
Tests for the rendered figures.

    python test_charts.py            # built-in runner, no dependencies
    python -m pytest test_charts.py  # if pytest is available

These exist because of a failure that passed every other check. Both charts
were generated without an XML namespace on the root element. Pasted inline
into an HTML page they rendered perfectly, because the HTML parser assumes the
SVG namespace; loaded through an `<img>` tag -- which is how a README shows a
figure -- the browser reported a natural size of 0x0 and drew nothing.

So the figures were absent from the repository front page while every file was
present, every URL returned 200 with `image/svg+xml`, and an inline preview
looked correct. Nothing in the test suite could see it.

The tests below check the three properties a standalone SVG needs to survive
being loaded as a file, and one more: that the figure and the saved results do
not drift apart.
"""

import io
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

SVG_NS = "http://www.w3.org/2000/svg"
CHARTS = ("gate_chart.svg", "ceiling_chart.svg")


def read(name):
    path = os.path.join(HERE, name)
    assert os.path.exists(path), f"{name} has not been generated"
    return io.open(path, encoding="utf-8").read()


def root(name):
    s = read(name)
    m = re.match(r"\s*<svg\b[^>]*>", s)
    assert m, f"{name} does not start with an svg element"
    return m.group(0)


def test_every_chart_declares_the_svg_namespace():
    """
    The check that would have caught it. An SVG without xmlns renders inline
    and fails as a file, so this cannot be verified by looking at a preview.
    """
    for name in CHARTS:
        tag = root(name)
        assert f'xmlns="{SVG_NS}"' in tag, f"{name}: no xmlns on the root element"


def test_every_chart_has_an_intrinsic_size():
    """
    An `<img>` needs a width and a height in absolute units. A percentage width
    alone gives the element no intrinsic size, which is a second, independent
    way for a figure to collapse to nothing.
    """
    for name in CHARTS:
        tag = root(name)
        for attr in ("width", "height"):
            m = re.search(rf'\b{attr}="([^"]+)"', tag)
            assert m, f"{name}: no {attr} on the root element"
            assert not m.group(1).endswith("%"), (
                f"{name}: {attr} is a percentage, which is not an intrinsic size")
            assert float(m.group(1)) > 0, f"{name}: {attr} is {m.group(1)}"


def test_the_declared_size_matches_the_view_box():
    """A mismatch scales the drawing silently rather than failing."""
    for name in CHARTS:
        tag = root(name)
        vb = re.search(r'viewBox="0 0 ([\d.]+) ([\d.]+)"', tag)
        assert vb, f"{name}: no viewBox"
        w = float(re.search(r'\bwidth="([\d.]+)"', tag).group(1))
        h = float(re.search(r'\bheight="([\d.]+)"', tag).group(1))
        assert (w, h) == (float(vb.group(1)), float(vb.group(2))), (
            f"{name}: {w}x{h} against viewBox {vb.group(1)}x{vb.group(2)}")


def test_every_chart_carries_a_text_alternative():
    """The figure states the result; a reader who cannot see it needs it too."""
    for name in CHARTS:
        tag = root(name)
        m = re.search(r'aria-label="([^"]+)"', tag)
        assert m, f"{name}: no aria-label"
        assert len(m.group(1)) > 40, f"{name}: aria-label is too short to say anything"


def test_both_charts_regenerate_byte_identically():
    """A figure that drifts from its generator is a screenshot, not an output."""
    import chart
    import gate_chart

    for name, module in (("ceiling_chart.svg", chart),
                         ("gate_chart.svg", gate_chart)):
        before = read(name)
        module.render()
        after = read(name)
        assert before == after, f"{name} changed when regenerated"


def test_the_figure_and_the_saved_results_agree():
    """
    Cross-file consistency. The chart draws the built reliability as the one
    correct answer and labels it; `gate_results.json` records the same value.
    Two files carrying the same number will separate eventually unless
    something compares them.
    """
    data = json.load(io.open(os.path.join(HERE, "gate_results.json"),
                             encoding="utf-8"))
    built = data["built_rho_1"]
    svg = read("gate_chart.svg")
    assert f"built at {built}" in svg, (
        f"chart does not label the built value {built}")

    # And the end-of-line percentages the chart prints must match the sweep.
    for key, rows in (("sweep_continuous", data["sweep_continuous"]),
                      ("sweep_five_point", data["sweep_five_point"])):
        last = rows[-1]
        assert last["threshold"] == 1.0, key
        shown = f"{last['overstated']:+.0%} at 1.0 sd"
        assert shown in svg, f"{key}: chart does not show '{shown}'"


# ------------------------------------------------------------ built-in runner

if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  PASS  {name}")
        except AssertionError as e:
            print(f"  FAIL  {name}  -> {e}")
            failed += 1
        except Exception as e:
            print(f"  ERROR {name}  -> {type(e).__name__}: {e}")
            failed += 1
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
