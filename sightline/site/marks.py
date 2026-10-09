"""Screenshot visual annotation and numbered badge drawing using Pillow."""

from pathlib import Path
from typing import Any, Union

from PIL import Image, ImageDraw, ImageFont

from sightline.models import Box, Element, Finding, PageSnapshot

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


def _draw_dashed_rect(
    draw: ImageDraw.ImageDraw,
    x0: int,
    y0: int,
    x1: int,
    y1: int,
    color: tuple[int, int, int],
    width: int = 3,
    dash_len: int = 6,
    gap_len: int = 4,
) -> None:
    """Draw a dashed rectangular outline for color-blind safe representation."""
    # Top and bottom
    x = x0
    while x < x1:
        x_end = min(x + dash_len, x1)
        draw.line([(x, y0), (x_end, y0)], fill=color, width=width)
        draw.line([(x, y1), (x_end, y1)], fill=color, width=width)
        x += dash_len + gap_len
    # Left and right
    y = y0
    while y < y1:
        y_end = min(y + dash_len, y1)
        draw.line([(x0, y), (x0, y_end)], fill=color, width=width)
        draw.line([(x1, y), (x1, y_end)], fill=color, width=width)
        y += dash_len + gap_len


def compose_comparison(
    before_img: Image.Image,
    after_img: Image.Image,
    before_box: Any,
    after_box: Any,
    rule: str,
    note: str | None = None,
    aria_label: str | None = None,
) -> Image.Image | None:
    """Compose a side-by-side comparison image: Before (red dashed) vs After (green solid).

    Returns a new PIL Image with headers, marked boxes, and a bottom caption strip.
    Returns None without raising if boxes are invalid, zero-size, or outside image bounds.
    """
    try:
        if before_img is None or after_img is None:
            return None

        # Extract (x, y, w, h)
        def _extract(b: Any) -> tuple[float, float, float, float] | None:
            if b is None:
                return None
            if isinstance(b, Box):
                return (b.x, b.y, b.w, b.h)
            if isinstance(b, (tuple, list)) and len(b) >= 4:
                return (float(b[0]), float(b[1]), float(b[2]), float(b[3]))
            if isinstance(b, dict):
                return (
                    float(b.get("x", 0)),
                    float(b.get("y", 0)),
                    float(b.get("w", b.get("width", 0))),
                    float(b.get("h", b.get("height", 0))),
                )
            return None

        bbox = _extract(before_box)
        abox = _extract(after_box)
        if bbox is None or abox is None:
            return None

        bx, by, bw, bh = bbox
        ax, ay, aw, ah = abox

        # Zero or negative size check
        if bw <= 0 or bh <= 0 or aw <= 0 or ah <= 0:
            return None

        # Box outside image bounds check
        if bx >= before_img.width or by >= before_img.height:
            return None
        if ax >= after_img.width or ay >= after_img.height:
            return None
        if bx + bw <= 0 or by + bh <= 0:
            return None
        if ax + aw <= 0 or ay + ah <= 0:
            return None

        b_panel = before_img.convert("RGB").copy()
        a_panel = after_img.convert("RGB").copy()

        font = _get_font(12)
        header_font = _get_font(13)
        caption_font = _get_font(12)

        draw_b = ImageDraw.Draw(b_panel)
        draw_a = ImageDraw.Draw(a_panel)

        red_color = (220, 38, 38)
        green_color = (22, 163, 74)

        # Draw red dashed box on before panel
        bx0 = max(0, min(int(round(bx)), b_panel.width - 1))
        by0 = max(0, min(int(round(by)), b_panel.height - 1))
        bx1 = max(bx0 + 1, min(int(round(bx + bw)), b_panel.width - 1))
        by1 = max(by0 + 1, min(int(round(by + bh)), b_panel.height - 1))
        _draw_dashed_rect(draw_b, bx0, by0, bx1, by1, color=red_color, width=3)

        if rule == "missing-name":
            _draw_badge(
                draw=draw_b,
                x=bx0,
                y=max(0, by0 - 18),
                text="No accessible name",
                font=font,
                bg_color=red_color,
                text_color=(255, 255, 255),
                max_w=b_panel.width,
                max_h=b_panel.height,
            )

        # Draw green solid box on after panel
        ax0 = max(0, min(int(round(ax)), a_panel.width - 1))
        ay0 = max(0, min(int(round(ay)), a_panel.height - 1))
        ax1 = max(ax0 + 1, min(int(round(ax + aw)), a_panel.width - 1))
        ay1 = max(ay0 + 1, min(int(round(ay + ah)), a_panel.height - 1))
        draw_a.rectangle([ax0, ay0, ax1, ay1], outline=green_color, width=3)

        if rule == "missing-name" and aria_label:
            clean_label = str(aria_label).strip()[:40]
            _draw_badge(
                draw=draw_a,
                x=ax0,
                y=max(0, ay0 - 18),
                text=clean_label,
                font=font,
                bg_color=green_color,
                text_color=(255, 255, 255),
                max_w=a_panel.width,
                max_h=a_panel.height,
            )

        # Side-by-side composition
        panel_w = max(b_panel.width, a_panel.width)
        panel_h = max(b_panel.height, a_panel.height)

        header_h = 28
        divider_w = 2
        caption_h = 32 if note else 0
        total_w = panel_w * 2 + divider_w
        total_h = header_h + panel_h + caption_h

        composed = Image.new("RGB", (total_w, total_h), color=(248, 250, 252))
        draw_comp = ImageDraw.Draw(composed)

        # Top headers
        # "Before" header on left
        draw_comp.text((12, 6), "Before", fill=(185, 28, 28), font=header_font)
        # "After" header on right
        draw_comp.text(
            (panel_w + divider_w + 12, 6), "After", fill=(21, 128, 61), font=header_font
        )

        # Divider between panels
        draw_comp.line([(panel_w, 0), (panel_w, total_h)], fill=(226, 232, 240), width=divider_w)

        # Paste left and right panels
        composed.paste(b_panel, (0, header_h))
        composed.paste(a_panel, (panel_w + divider_w, header_h))

        # Bottom caption strip if note provided
        if note:
            cap_y = header_h + panel_h
            draw_comp.rectangle([0, cap_y, total_w, total_h], fill=(241, 245, 249))
            draw_comp.text((12, cap_y + 8), str(note), fill=(30, 41, 59), font=caption_font)

        return composed

    except Exception:
        return None
