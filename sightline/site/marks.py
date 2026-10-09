"""Screenshot visual annotation and numbered badge drawing using Pillow."""

from pathlib import Path
from typing import Union

from PIL import Image, ImageDraw, ImageFont

from sightline.models import Element, Finding, PageSnapshot

# Color palette for annotations
DEFAULT_MARK_COLOR = (37, 99, 235)  # Royal Blue for interactive element marks

SEVERITY_COLORS = {
    "high": (220, 38, 38),     # Red
    "medium": (234, 88, 12),   # Orange / Amber
    "low": (37, 99, 235),      # Blue
}


def _get_font(size: int = 12) -> ImageFont.ImageFont:
    """Load a truetype font if available, falling back to PIL's default font."""
    candidates = [
        "arial.ttf",
        "segoeui.ttf",
        "DejaVuSans.ttf",
        "LiberationSans-Regular.ttf",
    ]
    for font_name in candidates:
        try:
            return ImageFont.truetype(font_name, size=size)
        except OSError:
            continue
    try:
        return ImageFont.load_default()
    except Exception:
        return ImageFont.load_default()


def _is_interactive(element: Element) -> bool:
    """Check if an element is an interactive control."""
    kind = element.meta.get("kind") if element.meta else None
    if kind == "interactive":
        return True
    if kind in ("text", "image"):
        return False

    # Fallback heuristics for tags and roles
    interactive_tags = {"a", "button", "input", "select", "textarea"}
    if element.tag in interactive_tags:
        return True
    if element.meta and element.meta.get("role") == "button":
        return True
    return False


def _draw_badge(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    text: str,
    font: ImageFont.ImageFont,
    bg_color: tuple[int, int, int],
    text_color: tuple[int, int, int] = (255, 255, 255),
    padding_x: int = 4,
    padding_y: int = 2,
    max_w: int = 10000,
    max_h: int = 10000,
) -> None:
    """Draw a solid colored badge with readable text."""
    bbox = draw.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]

    badge_w = text_w + padding_x * 2
    badge_h = text_h + padding_y * 2

    # Clamp badge coordinates inside image bounds
    bx0 = max(0, min(x, max_w - badge_w))
    by0 = max(0, min(y, max_h - badge_h))
    bx1 = min(max_w, bx0 + badge_w)
    by1 = min(max_h, by0 + badge_h)

    # Draw solid badge background
    draw.rectangle([bx0, by0, bx1, by1], fill=bg_color)

    # Draw text centered in badge
    tx = bx0 + padding_x - bbox[0]
    ty = by0 + padding_y - bbox[1]
    draw.text((tx, ty), text, fill=text_color, font=font)


def mark_elements(
    snapshot: PageSnapshot,
    out_path: Union[str, Path],
    max_height: int = 1800,
) -> str:
    """Draw a box and a number label on every interactive element in the first max_height pixels.

    Crops the screenshot to min(height, max_height) and saves the marked image to out_path.
    """
    img = Image.open(snapshot.screenshot_path).convert("RGB")
    target_height = min(img.height, max_height)
    cropped = img.crop((0, 0, img.width, target_height))

    draw = ImageDraw.Draw(cropped)
    font = _get_font(12)

    for el in snapshot.elements:
        if not _is_interactive(el):
            continue

        # Skip elements positioned entirely beyond the crop boundary or invalid boxes
        if el.box.y >= max_height or el.box.w <= 0 or el.box.h <= 0:
            continue

        x0 = max(0, int(round(el.box.x)))
        y0 = max(0, int(round(el.box.y)))
        x1 = min(cropped.width - 1, int(round(el.box.x + el.box.w)))
        y1 = min(target_height - 1, int(round(el.box.y + el.box.h)))

        if x1 <= x0 or y1 <= y0:
            continue

        # Draw bounding box outline
        draw.rectangle([x0, y0, x1, y1], outline=DEFAULT_MARK_COLOR, width=2)

        # Draw number badge
        badge_text = str(el.number)
        badge_bbox = draw.textbbox((0, 0), badge_text, font=font)
        badge_h = (badge_bbox[3] - badge_bbox[1]) + 4

        # Place badge above box if space permits, else inside top-left
        badge_y = y0 - badge_h if y0 >= badge_h else y0
        _draw_badge(
            draw=draw,
            x=x0,
            y=badge_y,
            text=badge_text,
            font=font,
            bg_color=DEFAULT_MARK_COLOR,
            text_color=(255, 255, 255),
            max_w=cropped.width,
            max_h=target_height,
        )

    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    cropped.save(out)
    return str(out)


def annotate(
    snapshot: PageSnapshot,
    findings: list[Finding],
    out_path: Union[str, Path],
) -> str:
    """Draw boxes on flagged elements coloured by severity with finding numbers.

    Page-level findings receive no box. Annotations are drawn on the full uncropped screenshot.
    """
    img = Image.open(snapshot.screenshot_path).convert("RGB")
    draw = ImageDraw.Draw(img)
    font = _get_font(12)

    element_map = {el.number: el for el in snapshot.elements}

    for idx, finding in enumerate(findings, start=1):
        # Page-level findings get no box
        if finding.element_number is None and finding.box is None:
            continue

        box = None
        if finding.box is not None:
            box = finding.box
        elif finding.element_number is not None and finding.element_number in element_map:
            box = element_map[finding.element_number].box

        if box is None or box.w <= 0 or box.h <= 0:
            continue

        x0 = max(0, int(round(box.x)))
        y0 = max(0, int(round(box.y)))
        x1 = min(img.width - 1, int(round(box.x + box.w)))
        y1 = min(img.height - 1, int(round(box.y + box.h)))

        if x1 <= x0 or y1 <= y0:
            continue

        color = SEVERITY_COLORS.get(finding.severity, (234, 88, 12))

        # Draw bounding box outline
        draw.rectangle([x0, y0, x1, y1], outline=color, width=3)

        # Draw finding number badge
        badge_text = str(idx)
        badge_bbox = draw.textbbox((0, 0), badge_text, font=font)
        badge_h = (badge_bbox[3] - badge_bbox[1]) + 4

        badge_y = y0 - badge_h if y0 >= badge_h else y0
        _draw_badge(
            draw=draw,
            x=x0,
            y=badge_y,
            text=badge_text,
            font=font,
            bg_color=color,
            text_color=(255, 255, 255),
            max_w=img.width,
            max_h=img.height,
        )

    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out)
    return str(out)
