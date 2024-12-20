import io
from enum import Enum
from copy import deepcopy
from functools import cache

from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader

from util import *
from config import CFG
from constants import *
from image import read_image, image_to_bytes, rotate_image, Rotation


class CrossSegment(Enum):
    TopLeft = (1, -1)
    TopRight = (-1, -1)
    BottomRight = (-1, 1)
    BottomLeft = (1, 1)


def draw_line(can, c1, c2, fx, fy, tx, ty, s=1):
    dash = [s, s]
    can.setLineWidth(s)

    # First layer
    can.setDash(dash)
    can.setStrokeColorRGB(*c1)
    can.line(fx, fy, tx, ty)

    # Second layer with phase offset
    can.setDash(dash, s)
    can.setStrokeColorRGB(*c2)
    can.line(fx, fy, tx, ty)


# Draws black-white dashed cross segment at `(x, y)`, with a width of `c`, and a thickness of `s`
def draw_cross(can, c1, c2, x, y, segment, c=6, s=1):
    (dx, dy) = segment.value
    (tx, ty) = (x + c * dx, y + c * dy)

    draw_line(can, c1, c2, x, y, tx, y, s)
    draw_line(can, c1, c2, x, y, x, ty, s)


def generate(print_dict, crop_dir, size, pdf_path, print_fn):
    has_backside = print_dict["backside_enabled"]
    backside_offset = mm_to_point(float(print_dict["backside_offset"]))

    bleed_edge = float(print_dict["bleed_edge"])
    has_bleed_edge = bleed_edge > 0

    def int_to_rgb(val):
        return [
            float((val >> 16) & 0xFF) / 0xFF,
            float((val >> 8) & 0xFF) / 0xFF,
            float((val >> 0) & 0xFF) / 0xFF,
        ]

    c1 = int_to_rgb(print_dict["guide_color_a"])
    c2 = int_to_rgb(print_dict["guide_color_b"])

    b = 0
    img_dir = crop_dir
    if CFG.VibranceBump:
        img_dir = os.path.join(img_dir, "vibrance")
    if has_bleed_edge:
        b = mm_to_inch(bleed_edge)
        img_dir = os.path.join(img_dir, str(bleed_edge).replace(".", "p"))
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

    images = distribute_cards_to_pages(print_dict, cols, rows)

    extended_guides = print_dict["extended_guides"]

    @cache
    def get_img(img_path, rotation):
        if rotation is None:
            return img_path

        img = read_image(img_path)
        img = rotate_image(img, rotation)
        img = image_to_bytes(img)
        img = ImageReader(io.BytesIO(img))
        return img

    for p, page_images in enumerate(images):
        render_fmt = "Rendering page {page}...\nImage number {img_idx} - {img_name}"

        def draw_image(
            img, oversized, i, x, y, dx=0.0, dy=0.0, is_short_edge=False, backside=False
        ):
            print_fn(render_fmt.format(page=p + 1, img_idx=i + 1, img_name=img))
            img_path = os.path.join(img_dir, img)
            if os.path.exists(img_path):
                if oversized and backside:
                    x = x - 1

                rotation = get_card_rotation(backside, is_oversized, is_short_edge)
                img = get_img(img_path, rotation)

                x = rx + x * w + dx
                y = ry - y * h + dy - h
                cw = cw = 2 * w if oversized else w
                ch = h

                pages.drawImage(
                    img,
                    x,
                    y,
                    cw,
                    ch,
                )

        def draw_cross_at_grid(ix, iy, segment, dx=0.0, dy=0.0):
            x = rx + ix * w + dx
            y = ry - iy * h + dy
            draw_cross(pages, c1, c2, x, y, segment)
            if extended_guides:
                if ix == 0:
                    draw_line(pages, c1, c2, x, y, 0, y)
                if ix == cols:
                    draw_line(pages, c1, c2, x, y, pw, y)
                if iy == 0:
                    draw_line(pages, c1, c2, x, y, x, ph)
                if iy == rows:
                    draw_line(pages, c1, c2, x, y, x, 0)

        card_grid = distribute_cards_to_grid(page_images, True, cols, rows)

        i = 0
        for y in range(0, rows):
            for x in range(0, cols):
                if card := card_grid[y][x]:
                    (card_name, is_short_edge, is_oversized) = card
                    if card_name is None:
                        continue

                    draw_image(
                        card_name, is_oversized, i, x, y, is_short_edge=is_short_edge
                    )
                    i = i + 1

                    if is_oversized:
                        ob = 2 * b
                        draw_cross_at_grid(
                            x + 2, y + 0, CrossSegment.TopRight, -ob, -ob
                        )
                        draw_cross_at_grid(
                            x + 2, y + 1, CrossSegment.BottomRight, -ob, +ob
                        )
                    else:
                        ob = b
                        draw_cross_at_grid(
                            x + 1, y + 0, CrossSegment.TopRight, -ob, -ob
                        )
                        draw_cross_at_grid(
                            x + 1, y + 1, CrossSegment.BottomRight, -ob, +ob
                        )

                    draw_cross_at_grid(x, y + 0, CrossSegment.TopLeft, +ob, -ob)
                    draw_cross_at_grid(x, y + 1, CrossSegment.BottomLeft, +ob, +ob)

        # Next page
        pages.showPage()

        # Draw back-sides if requested
        if has_backside:
            render_fmt = "Rendering backside for page {page}...\nImage number {img_idx} - {img_name}"
            i = 0
            for y in range(0, rows):
                for x in range(0, cols):
                    if card := card_grid[y][x]:
                        (card_name, is_short_edge, is_oversized) = card
                        if card_name is None:
                            continue

                        print_fn(
                            render_fmt.format(
                                page=p + 1, img_idx=i + 1, img_name=card_name
                            )
                        )
                        backside = (
                            print_dict["backsides"][card_name]
                            if card_name in print_dict["backsides"]
                            else print_dict["backside_default"]
                        )
                        draw_image(
                            backside,
                            is_oversized,
                            i,
                            cols - x - 1,
                            y,
                            dx=backside_offset,
                            is_short_edge=is_short_edge,
                            backside=True,
                        )

            # Next page
            pages.showPage()

    return pages


def distribute_cards_to_pages(print_dict, columns, rows):
    images_per_page = columns * rows
    oversized_images_per_page = (columns // 2) * rows

    short_edge_dict = print_dict["backside_short_edge"]
    oversized_dict = print_dict["oversized"] if print_dict["oversized_enabled"] else {}

    # throw all images n times into a list
    images = []
    for img, num in print_dict["cards"].items():
        is_short_edge = short_edge_dict[img] if img in short_edge_dict else False
        is_oversized = oversized_dict[img] if img in oversized_dict else False
        images.extend([(img, is_short_edge, is_oversized)] * num)

    # favor filling up with oversized cards first
    images = sorted(images, key=lambda x: not x[1])

    def page_has_space(page, oversized):
        oversized_cards = len(page["oversized"])
        regular_cards = len(page["regular"])
        single_spaces = regular_cards + oversized_cards * 2
        free_single_spaces = images_per_page - single_spaces
        if oversized:
            free_double_spaces = oversized_images_per_page - oversized_cards
            return free_double_spaces > 0 and free_single_spaces > 1
        else:
            return free_single_spaces > 0

    def is_page_full(page):
        return page_has_space(page, False) == False

    empty_page = {"regular": [], "oversized": []}
    pages = []

    unfinished_pages = []
    for img, is_short_edge, is_oversized in images:
        # get a page that can fit this card
        page_with_space = next(
            filter(lambda x: page_has_space(x, is_oversized), unfinished_pages),
            None,
        )

        # or start a new page if none is available
        if page_with_space is None:
            unfinished_pages.append(deepcopy(empty_page))
            page_with_space = unfinished_pages[-1]

        # add the image to the page
        page_with_space["oversized" if is_oversized else "regular"].append(
            (img, is_short_edge)
        )

        # push full page into final list
        if is_page_full(page_with_space):
            pages.append(page_with_space)
            unfinished_pages.remove(page_with_space)

    # push all unfinished pages into final list
    pages.extend(unfinished_pages)
    return pages


def make_backside_pages(print_dict, pages):
    back_dict = print_dict["backsides"]

    def backside_of_img(img_pair):
        (img, is_short_edge) = img_pair
        return (
            (back_dict[img] if img in back_dict else print_dict["backside_default"]),
            is_short_edge,
        )

    backside_pages = deepcopy(pages)
    for page in backside_pages:
        page["regular"] = [backside_of_img(img) for img in page["regular"]]
        page["oversized"] = [backside_of_img(img) for img in page["oversized"]]

    return backside_pages


def distribute_cards_to_grid(cards, left_to_right, columns, rows):
    def get_coord(i):
        return get_grid_coords(i, columns, left_to_right)

    card_grid = [[None] * columns for i in range(rows)]

    k = 0
    for card_name, is_short_edge in cards["oversized"]:
        x, y = get_coord(k)

        # find slot that fits an oversized card
        while y + 1 >= columns or card_grid[x][y + 1] is not None:
            k = k + 1
            x, y = get_coord(k)

        card_grid[x][y] = (card_name, is_short_edge, True)
        card_grid[x][y + 1] = (None, None, None)
        k = k + 2
    del k

    i = 0
    for card_name, is_short_edge in cards["regular"]:
        x, y = get_coord(i)

        # find slot that is free for single card
        while card_grid[x][y] is not None:
            i = i + 1
            x, y = get_coord(i)

        card_grid[x][y] = (card_name, is_short_edge, False)
        i = i + 1
    del i

    return card_grid


def get_grid_coords(idx, columns, left_to_right):
    x, y = divmod(idx, columns)
    if not left_to_right:
        y = columns - y - 1
    return x, y


def get_card_rotation(backside, is_oversized, is_short_edge):
    if backside:
        if is_short_edge:
            if is_oversized:
                return Rotation.RotateClockwise_90
            else:
                return Rotation.Rotate_180
        elif is_oversized:
            return Rotation.RotateCounterClockwise_90
    elif is_oversized:
        return Rotation.RotateClockwise_90

    return None
