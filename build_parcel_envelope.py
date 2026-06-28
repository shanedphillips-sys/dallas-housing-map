#!/usr/bin/env python3
"""Generate a scaled SVG comparing rectangular parcels, each with a uniform-setback building
envelope, stacked vertically (largest on top) and left-aligned to a common datum.

For each lot it draws the property line, the buildable envelope produced by an equal setback on
all four sides, overall (double-arrow) width/depth dimensions, and four inward setback arrows.
The envelope's own size is labeled inside it (the full label if it fits, otherwise just the
square footage); the whole lot's square footage is captioned beneath the parcel. A shared legend
sits at the bottom with swatches that mirror the diagram (white outlined rect = property line,
blue dashed rect = buildable envelope). Output is a self-contained .svg (hardcoded colors +
a dark-mode media query) that renders in any browser / Illustrator / Inkscape.

The buffer between stacked figures is a *layout* measure (inches of paper), converted at --dpi.

Default reproduces Shane's comparison: a 110' x 65' lot above a 90' x 40' lot, both 15' setbacks.

Usage:
    python build_parcel_envelope.py
    python build_parcel_envelope.py --parcels 110x65,90x40 --setback 15
    python build_parcel_envelope.py --parcels 100x50 --gap-inches 0.5 --out lot.svg
"""
import argparse

# --- Colors (light defaults; dark-mode swaps via media query) ---
TXT, DIM, LOT_BORDER = "#1a1a1a", "#6b6b6b", "#555555"
ENV_FILL, ENV_LINE, SURFACE = "#cfe2f3", "#2b6cb0", "#ffffff"
FONT = "system-ui, -apple-system, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif"

SCALE_DEFAULT = 3.0      # pixels per foot
TOP_PAD = 32             # px above a parcel for its width dimension + label
MARGIN = 30              # canvas margin
LEFT_X = 64              # shared left edge of every parcel (room left for the depth dim)
OUTER_GAP_TOP = 11       # px between the top (width) arrow and the property line
OUTER_GAP_LEFT = 11.5    # px between the left (depth) arrow and the property line
WIDTH_LABEL_GAP = 10     # px between a width label and its arrow (the reference distance)
DEPTH_LABEL_GAP = 16     # px between a depth label's center and its arrow (~equal visual gap)
LEGEND_GAP = 12          # px between the last figure and the legend


def fmt(x):
    """Trim trailing .0 so 80.0 -> '80', 7.5 -> '7.5'."""
    return f"{x:g}"


def dim_line(x1, y1, x2, y2, both=False):
    ends = ' marker-start="url(#ar)"' if both else ""
    return (
        f'  <line x1="{fmt(x1)}" y1="{fmt(y1)}" x2="{fmt(x2)}" y2="{fmt(y2)}" '
        f'stroke="{DIM}" stroke-width="1" marker-end="url(#ar)"{ends}/>'
    )


def envelope_rows(ew, eh, ewf, edf, env_sq):
    """Pick the interior envelope label that fits the envelope's px size.
    Returns a list of (text-class, font-weight-or-None, text)."""
    dims = f"{fmt(ewf)}\' &#215; {fmt(edf)}\'"
    sqft = f"{env_sq:,.0f} sq ft"
    if eh >= 58 and ew >= 170:          # title on one line + dims + sqft
        return [("t", "500", "Buildable envelope"), ("ts", None, dims), ("ts", None, sqft)]
    if eh >= 78 and ew >= 80:           # narrow+tall: stack the title onto two lines
        return [("t", "500", "Buildable"), ("t", "500", "envelope"),
                ("ts", None, dims), ("ts", None, sqft)]
    if eh >= 20 and ew >= 65:           # short+wide: just the square footage
        return [("ts", None, sqft)]
    return []


def figure(px, py, w, d, setback, scale):
    """Return (svg_parts, content_top_y, content_bottom_y, parcel_width_px) for one parcel
    drawn with its top-left at (px, py)."""
    inset = setback * scale
    pw, ph = w * scale, d * scale
    ex, ey = px + inset, py + inset
    ew, eh = pw - 2 * inset, ph - 2 * inset
    cx, cy = px + pw / 2, py + ph / 2
    ecx, ecy = ex + ew / 2, ey + eh / 2
    ewf, edf = w - 2 * setback, d - 2 * setback

    out = [
        f'  <rect class="parcel" x="{fmt(px)}" y="{fmt(py)}" width="{fmt(pw)}" '
        f'height="{fmt(ph)}" rx="2" stroke-width="1.5"/>',
        f'  <rect class="env" x="{fmt(ex)}" y="{fmt(ey)}" width="{fmt(ew)}" '
        f'height="{fmt(eh)}" rx="2" stroke-width="1" stroke-dasharray="5 4"/>',
    ]

    # Interior envelope label, vertically centered in the envelope.
    rows = envelope_rows(ew, eh, ewf, edf, ewf * edf)
    spacing = 20
    start = ecy - (len(rows) - 1) * spacing / 2 + 5
    for i, (cls, wt, txt) in enumerate(rows):
        wattr = f' font-weight="{wt}"' if wt else ""
        out.append(f'  <text class="{cls}" x="{fmt(ecx)}" y="{fmt(start + i * spacing)}" '
                   f'text-anchor="middle"{wattr}>{txt}</text>')

    # Whole-lot square footage, captioned beneath the parcel.
    cap_y = py + ph + 20
    out.append(f'  <text class="t" x="{fmt(cx)}" y="{fmt(cap_y)}" text-anchor="middle">'
               f'{w * d:,.0f} sq ft</text>')

    # Overall width dimension (top) and depth dimension (left).
    ty = py - OUTER_GAP_TOP
    out.append(dim_line(px, ty, px + pw, ty, both=True))
    out.append(f'  <text class="ts" x="{fmt(cx)}" y="{fmt(ty - WIDTH_LABEL_GAP)}" '
               f'text-anchor="middle">{fmt(w)}\'</text>')
    lx = px - OUTER_GAP_LEFT
    dlx = lx - DEPTH_LABEL_GAP
    out.append(dim_line(lx, py, lx, py + ph, both=True))
    out.append(f'  <text class="ts" x="{fmt(dlx)}" y="{fmt(cy)}" text-anchor="middle" '
               f'transform="rotate(-90 {fmt(dlx)} {fmt(cy)})">{fmt(d)}\'</text>')

    # Four inward setback arrows (tail at property line -> head at envelope edge).
    out.append(dim_line(cx, py + 1, cx, ey))
    out.append(f'  <text class="ts" x="{fmt(cx + 10)}" y="{fmt(py + inset / 2 + 5)}" '
               f'text-anchor="start">{fmt(setback)}\'</text>')
    out.append(dim_line(cx, py + ph - 1, cx, ey + eh))
    out.append(f'  <text class="ts" x="{fmt(cx + 10)}" y="{fmt(py + ph - inset / 2 + 5)}" '
               f'text-anchor="start">{fmt(setback)}\'</text>')
    out.append(dim_line(px + 1, cy, ex, cy))
    out.append(f'  <text class="ts" x="{fmt(px + inset / 2)}" y="{fmt(cy - 8)}" '
               f'text-anchor="middle">{fmt(setback)}\'</text>')
    out.append(dim_line(px + pw - 1, cy, ex + ew, cy))
    out.append(f'  <text class="ts" x="{fmt(px + pw - inset / 2)}" y="{fmt(cy - 8)}" '
               f'text-anchor="middle">{fmt(setback)}\'</text>')

    return out, py - TOP_PAD, cap_y + 6, pw


def build_svg(parcels, setback, scale, gap_px):
    body, max_right, last_bottom = [], 0, 0
    y = MARGIN
    for w, d in parcels:
        py = y + TOP_PAD
        parts, _ctop, cbottom, pw = figure(LEFT_X, py, w, d, setback, scale)
        body += parts
        max_right = max(max_right, LEFT_X + pw)
        last_bottom = cbottom
        y = cbottom + gap_px
    canvas_w = max_right + MARGIN

    # Shared legend -- swatches mirror the diagram (outlined rect / blue dashed rect).
    sw, sh = 34, 18
    ly = last_bottom + LEGEND_GAP
    legend = [
        f'  <rect class="parcel" x="{fmt(LEFT_X)}" y="{fmt(ly)}" width="{sw}" height="{sh}" '
        f'rx="2" stroke-width="1.5"/>',
        f'  <text class="ts" x="{fmt(LEFT_X + sw + 10)}" y="{fmt(ly + 13)}" '
        f'text-anchor="start">Property line</text>',
        f'  <rect class="env" x="{fmt(LEFT_X)}" y="{fmt(ly + 26)}" width="{sw}" height="{sh}" '
        f'rx="2" stroke-width="1" stroke-dasharray="5 4"/>',
        f'  <text class="ts" x="{fmt(LEFT_X + sw + 10)}" y="{fmt(ly + 39)}" '
        f'text-anchor="start">Buildable envelope with {fmt(setback)}\' setbacks</text>',
    ]
    canvas_h = ly + 26 + sh + 20

    desc = "; ".join(
        f"a {fmt(w)} by {fmt(d)} foot lot with a {fmt(w - 2 * setback)} by "
        f"{fmt(d - 2 * setback)} foot envelope" for w, d in parcels
    )
    head = [
        f'<svg width="100%" viewBox="0 0 {fmt(canvas_w)} {fmt(canvas_h)}" role="img" '
        'xmlns="http://www.w3.org/2000/svg">',
        '  <title>Parcel building envelopes</title>',
        f'  <desc>Parcels with {fmt(setback)} foot setbacks on all four sides: {desc}.</desc>',
        '  <defs>',
        f'  <marker id="ar" markerWidth="9" markerHeight="9" refX="4.5" refY="4.5" '
        f'orient="auto"><path d="M1,1.5 L5,4.5 L1,7.5" fill="none" stroke="{DIM}" '
        f'stroke-width="1"/></marker>',
        '  </defs>',
        '  <style>',
        f'    .t  {{ font-family: {FONT}; font-size: 17px; fill: {TXT}; }}',
        f'    .ts {{ font-family: {FONT}; font-size: 14px; fill: {DIM}; }}',
        f'    .parcel {{ fill: {SURFACE}; stroke: {LOT_BORDER}; }}',
        f'    .env    {{ fill: {ENV_FILL}; stroke: {ENV_LINE}; }}',
        '    @media (prefers-color-scheme: dark) {',
        '      .t  { fill: #ededed; }',
        '      .ts { fill: #b0b0b0; }',
        '      .parcel { fill: #2a2a2a; stroke: #888888; }',
        '      .env    { fill: #243b53; stroke: #63a4e0; }',
        '    }',
        '  </style>',
        '',
    ]
    return "\n".join(head + body + [''] + legend + ['</svg>'])


def parse_parcels(s):
    out = []
    for tok in s.split(","):
        w, d = tok.lower().split("x")
        out.append((float(w), float(d)))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--parcels", default="110x65,90x40",
                    help="comma-separated WIDTHxDEPTH lots in feet, largest first "
                         "(default 110x65,90x40)")
    ap.add_argument("--setback", type=float, default=15,
                    help="uniform setback on all four sides, feet (default 15)")
    ap.add_argument("--scale", type=float, default=SCALE_DEFAULT, help="pixels per foot (default 3)")
    ap.add_argument("--gap-inches", type=float, default=0.15,
                    help="buffer between stacked figures, inches of paper (default 0.15)")
    ap.add_argument("--dpi", type=float, default=96, help="px per inch for the buffer (default 96)")
    ap.add_argument("--out", default="parcel_envelope.svg", help="output SVG path")
    args = ap.parse_args()

    parcels = parse_parcels(args.parcels)
    gap_px = args.gap_inches * args.dpi
    svg = build_svg(parcels, args.setback, args.scale, gap_px)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(svg)

    print(f"Wrote {args.out}  ({args.gap_inches}\" buffer = {fmt(gap_px)} px @ {fmt(args.dpi)} dpi)")
    for w, d in parcels:
        ew, ed = w - 2 * args.setback, d - 2 * args.setback
        print(f"  Lot {fmt(w)}' x {fmt(d)}' = {w*d:,.0f} sq ft  ->  envelope {fmt(ew)}' x {fmt(ed)}'"
              f" = {ew*ed:,.0f} sq ft ({ew*ed/(w*d)*100:.0f}% coverage)")


if __name__ == "__main__":
    main()
