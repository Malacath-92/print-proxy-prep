import re
import subprocess

from reportlab.pdfgen import canvas

from util import *
from constants import *


# Draws black-white dashed cross at `x`, `y`
def draw_cross(can, x, y, c=6, s=1):
    dash = [s, s]
    can.setLineWidth(s)

    # First layer
    can.setDash(dash)
    can.setStrokeColorRGB(255, 255, 255)
    can.line(x, y - c, x, y + c)
    can.setStrokeColorRGB(0, 0, 0)
    can.line(x - c, y, x + c, y)

    # Second layer with phase offset
    can.setDash(dash, s)
    can.setStrokeColorRGB(0, 0, 0)
    can.line(x, y - c, x, y + c)
    can.setStrokeColorRGB(255, 255, 255)
    can.line(x - c, y, x + c, y)


def generate(print_dict, crop_dir, size, pdf_path, print_fn):
    images_dict = print_dict["cards"]
    has_backside = print_dict["backside_enabled"]
    backside_offset = mm_to_point(float(print_dict["backside_offset"]))
    bleed_edge = float(print_dict["bleed_edge"])
    has_bleed_edge = bleed_edge > 0
    if has_bleed_edge:
        b = mm_to_inch(bleed_edge)
        img_dir = os.path.join(crop_dir, str(bleed_edge).replace(".", "p"))
    else:
        b = 0
        img_dir = crop_dir
    (w, h) = card_size_without_bleed_inch
    w, h = inch_to_point((w + 2 * b)), inch_to_point((h + 2 * b))
    b = inch_to_point(b)
    rotate = bool(print_dict["orient"] == "Landscape")
    size = tuple(size[::-1]) if rotate else size
    pw, ph = size
    pages = canvas.Canvas(pdf_path, pagesize=size)
    cols, rows = int(pw // w), int(ph // h)
    rx, ry = round((pw - (w * cols)) / 2), round((ph - (h * rows)) / 2)
    ry = ph - ry - h
    images_per_page = cols * rows

    images = []
    for img in images_dict.keys():
        images.extend([img] * images_dict[img])
    images = [
        images[i : i + images_per_page] for i in range(0, len(images), images_per_page)
    ]

    for p, page_images in enumerate(images):
        render_fmt = "Rendering page {page}...\nImage number {img_idx} - {img_name}"

        def get_ith_image_coords(i, left_to_right):
            _, j = divmod(i, images_per_page)
            y, x = divmod(j, cols)
            if not left_to_right:
                x = cols - (x + 1)
            return x, y

        def draw_image(img, i, x, y, dx=0.0, dy=0.0):
            print_fn(render_fmt.format(page=p+1, img_idx=i+1, img_name=img))
            img_path = os.path.join(img_dir, img)
            if os.path.exists(img_path):
                pages.drawImage(
                    img_path,
                    x * w + rx + dx,
                    ry - y * h + dy,
                    w,
                    h,
                )

        # Draw front-sides
        for i, img in enumerate(page_images):
            x, y = get_ith_image_coords(i, True)
            draw_image(img, i, x, y)

            # Draw lines per image
            if has_bleed_edge:
                draw_cross(pages, (x + 0) * w + b + rx, ry - (y + 0) * h + b)
                draw_cross(pages, (x + 1) * w - b + rx, ry - (y + 0) * h + b)
                draw_cross(pages, (x + 1) * w - b + rx, ry - (y - 1) * h - b)
                draw_cross(pages, (x + 0) * w + b + rx, ry - (y - 1) * h - b)

        # Draw lines for whole page
        if not has_bleed_edge:
            for cy in range(rows + 1):
                for cx in range(cols + 1):
                    draw_cross(pages, rx + w * cx, ry - h * (cy - 1))

        # Next page
        pages.showPage()

        # Draw back-sides if requested
        if has_backside:
            render_fmt = "Rendering backside for page {page}...\nImage number {img_idx} - {img_name}"
            for i, img in enumerate(page_images):
                print_fn(render_fmt.format(page=p+1, img_idx=i+1, img_name=img))
                backside = (
                    print_dict["backsides"][img]
                    if img in print_dict["backsides"]
                    else print_dict["backside_default"]
                )
                x, y = get_ith_image_coords(i, False)
                draw_image(backside, i, x, y, backside_offset, 0)

            # Next page
            pages.showPage()

    return pages
