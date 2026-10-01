"""Generate PWA icon PNGs from the favicon design (blue tile + CRM text)."""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "app" / "static"

FONT_CANDIDATES = [
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]

BACKGROUND = "#2563eb"
FOREGROUND = "#ffffff"


def find_font(size):
    for candidate in FONT_CANDIDATES:
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, size)
    return ImageFont.load_default()


def rounded_mask(size, radius_ratio=0.22):
    mask = Image.new("L", (size, size), 0)
    draw = ImageDraw.Draw(mask)
    radius = int(size * radius_ratio)
    draw.rounded_rectangle((0, 0, size, size), radius=radius, fill=255)
    return mask


def render_icon(size, text="CRM"):
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    tile = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    tile_draw = ImageDraw.Draw(tile)
    tile_draw.rounded_rectangle(
        (0, 0, size, size),
        radius=int(size * 0.22),
        fill=BACKGROUND,
    )
    image.paste(tile, (0, 0), rounded_mask(size))

    draw = ImageDraw.Draw(image)
    font = find_font(int(size * 0.28))
    bbox = draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    draw.text(
        (
            (size - text_width) / 2 - bbox[0],
            (size - text_height) / 2 - bbox[1],
        ),
        text,
        font=font,
        fill=FOREGROUND,
    )
    return image


def main():
    icons = {
        "icon-192.png": 192,
        "icon-512.png": 512,
    }

    for filename, size in icons.items():
        render_icon(size).save(STATIC / filename)
        print(f"wrote {filename}")

    apple = render_icon(180)
    solid = Image.new("RGBA", (180, 180), BACKGROUND)
    solid.paste(apple, (0, 0), apple)
    solid.convert("RGB").save(STATIC / "apple-touch-icon.png")
    print("wrote apple-touch-icon.png")


if __name__ == "__main__":
    main()
