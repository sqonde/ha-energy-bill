"""Render the brand icons with resvg-py==0.5.0 (script-only dependency).

The PyPI manylinux x86_64 wheel SHA-256 is
84f2378ecc7a8e38b03429efaefc816daec1b1970114909a6f973393b297c91b.
"""

from pathlib import Path

import resvg_py

root = Path(__file__).resolve().parents[1]
svg = (root / "brand-src/icon.svg").read_text(encoding="utf-8")
brand = root / "custom_components/energy_bill/brand"
for name, size in (("icon.png", 256), ("icon@2x.png", 512)):
    (brand / name).write_bytes(
        resvg_py.svg_to_bytes(svg_string=svg, width=size, height=size, skip_system_fonts=True)
    )
