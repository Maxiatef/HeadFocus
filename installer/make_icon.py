"""Turn a square logo render (tile on a white background) into the app's
assets: assets/logo.png (1024px, transparent) and assets/icon.ico (16-256px).

    python installer/make_icon.py path/to/source-image
"""

import sys
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
SIZE = 1024
PADDING = 0.03  # breathing room around the tile, as a fraction of the size
ICO_SIZES = [16, 24, 32, 48, 64, 128, 256]
EDGE_INSET = 4  # source pixels trimmed off the tile edge


def tile_bbox(img):
    """Bounding box of the coloured tile: saturated pixels only, so the white
    background and the grey drop shadow are ignored."""
    r, g, b = img.split()
    spread = ImageChops.subtract(ImageChops.lighter(ImageChops.lighter(r, g), b),
                                 ImageChops.darker(ImageChops.darker(r, g), b))
    mask = spread.point(lambda v: 255 if v > 60 else 0)
    return mask.getbbox()


def corner_radius(img, box):
    """Measure the tile's corner rounding along its top edge."""
    left, top, right, _ = box
    row = top + 2
    for x in range(left, right):
        r, g, b = img.getpixel((x, row))
        if max(r, g, b) - min(r, g, b) > 60:
            return max(8, x - left)
    return (right - left) // 5


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    src = Image.open(sys.argv[1]).convert("RGB")
    box = tile_bbox(src)
    if not box:
        sys.exit("Couldn't find the icon tile in that image.")
    # Squash rounding error so the tile stays square.
    side = min(box[2] - box[0], box[3] - box[1])
    box = (box[0], box[1], box[0] + side, box[1] + side)
    radius = corner_radius(src, box) * 1.15

    tile = src.crop(box).convert("RGBA")
    # Rounded-rect alpha mask, drawn 4x larger then shrunk for smooth edges.
    # Inset a few pixels: the source's edge pixels are blended with the white
    # background and would show as a light halo on dark taskbars.
    big = Image.new("L", (side * 4, side * 4), 0)
    inset = EDGE_INSET * 4
    ImageDraw.Draw(big).rounded_rectangle(
        (inset, inset, side * 4 - 1 - inset, side * 4 - 1 - inset), radius=(radius - EDGE_INSET) * 4, fill=255
    )
    tile.putalpha(big.resize((side, side), Image.LANCZOS))

    inner = round(SIZE * (1 - 2 * PADDING))
    logo = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    offset = (SIZE - inner) // 2
    logo.paste(tile.resize((inner, inner), Image.LANCZOS), (offset, offset))

    ASSETS.mkdir(exist_ok=True)
    logo.save(ASSETS / "logo.png", optimize=True)
    logo.save(ASSETS / "icon.ico", sizes=[(s, s) for s in ICO_SIZES])
    print(f"tile {box} radius {radius:.0f}px -> {ASSETS / 'logo.png'}, {ASSETS / 'icon.ico'}")


if __name__ == "__main__":
    main()
