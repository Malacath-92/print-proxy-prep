from reportlab.pdfgen import canvas

from util import *
from constants import *


def draw_line(can, fx, fy, tx, ty, s=1):
    dash = [s, s]
    can.setLineWidth(s)

    # First layer
    can.setDash(dash)
    can.setStrokeColorRGB(0.75, 0.75, 0.75)
    can.line(fx, fy, tx, ty)

    # Second layer with phase offset
    can.setDash(dash, s)
    can.setStrokeColorRGB(0, 0, 0)
    can.line(fx, fy, tx, ty)


# Draws black-white dashed cross at `(x, y)`, with a width of `c`, and a thickness of `s`
def draw_cross(can, x, y, c=6, s=1):
    draw_line(can, x, y - c, x, y + c, s)
    draw_line(can, x - c, y, x + c, y, s)


def generate(print_dict, crop_dir, size, pdf_path, print_fn):
    has_backside = print_dict["backside_enabled"]
    backside_offset = 0
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
    ry = ph - ry
    images_per_page = cols * rows

    images_dict = print_dict["cards"]
    images = []
    for img, num in images_dict.items():
        images.extend([img] * num)
    images = [
        images[i : i + images_per_page] for i in range(0, len(images), images_per_page)
    ]

    extended_guides = print_dict["extended_guides"]

    for p, page_images in enumerate(images):
        render_fmt = "Rendering page {page}...\nImage number {img_idx} - {img_name}"

        def get_ith_image_coords(i, left_to_right):
            _, j = divmod(i, images_per_page)
            y, x = divmod(j, cols)
            if not left_to_right:
                x = cols - (x + 1)
            return x, y

        def draw_image(img, i, x, y, dx=0.0, dy=0.0):
            print_fn(render_fmt.format(page=p + 1, img_idx=i + 1, img_name=img))
            img_path = os.path.join(img_dir, img)
            if os.path.exists(img_path):
                pages.drawImage(
                    img_path,
                    rx + x * w + dx,
                    ry - y * h + dy - h,
                    w,
                    h,
                )

        def draw_cross_at_grid(ix, iy, dx=0.0, dy=0.0):
            x = rx + ix * w + dx
            y = ry - iy * h + dy
            draw_cross(pages, x, y)
            if extended_guides:
                if ix == 0:
                    draw_line(pages, x, y, 0, y)
                if ix == cols:
                    draw_line(pages, x, y, pw, y)
                if iy == 0:
                    draw_line(pages, x, y, x, ph)
                if iy == rows:
                    draw_line(pages, x, y, x, 0)

        # Draw front-sides
        for i, img in enumerate(page_images):
            x, y = get_ith_image_coords(i, True)
            draw_image(img, i, x, y)

            # Draw lines per image
            if has_bleed_edge:
                draw_cross_at_grid(x + 0, y + 0, +b, -b)
                draw_cross_at_grid(x + 1, y + 0, -b, -b)
                draw_cross_at_grid(x + 1, y + 1, -b, +b)
                draw_cross_at_grid(x + 0, y + 1, +b, +b)

        # Draw lines for whole page
        if not has_bleed_edge:
            for y in range(rows + 1):
                for x in range(cols + 1):
                    draw_cross_at_grid(x, y)

        # Next page
        pages.showPage()

        # Draw back-sides if requested
        if has_backside:
            render_fmt = "Rendering backside for page {page}...\nImage number {img_idx} - {img_name}"
            for i, img in enumerate(page_images):
                print_fn(render_fmt.format(page=p + 1, img_idx=i + 1, img_name=img))
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
