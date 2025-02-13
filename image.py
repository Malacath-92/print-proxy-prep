import io
import json
import base64
from enum import Enum

from PIL import Image as PIL_Image
from PIL import ImageFilter as PIL_ImageFilter
import pyvips

from util import *
from constants import *


vibrance_cube = None
valid_image_extensions = [
    ".gif",
    ".jpg",
    ".jpeg",
    ".png",
]


def list_image_files(dir):
    return list_files(dir, valid_image_extensions)


def init():
    with open(os.path.join(resource_path(), "vibrance.CUBE")) as f:
        lut_raw = f.read().splitlines()[11:]

    lsize = round(len(lut_raw) ** (1 / 3))
    row2val = lambda row: tuple([float(val) for val in row.split(" ")])
    lut_table = [row2val(row) for row in lut_raw]

    global vibrance_cube
    vibrance_cube = PIL_ImageFilter.Color3DLUT(lsize, lut_table)


def init_image_folder(image_dir, crop_dir):
    for folder in [image_dir, crop_dir]:
        if not os.path.exists(folder):
            os.mkdir(folder)


class Rotation(Enum):
    RotateClockwise_90 = (0,)
    RotateCounterClockwise_90 = (1,)
    Rotate_180 = (2,)


def rotate_image(img: pyvips.Image, rotation) -> pyvips.Image:
    if rotation is None:
        return img

    match rotation:
        case Rotation.RotateClockwise_90:
            rotation = img.rot90
        case Rotation.RotateCounterClockwise_90:
            rotation = img.rot270
        case Rotation.Rotate_180:
            rotation = img.rot180
    return rotation()


def read_image(path) -> pyvips.Image:
    return pyvips.Image.new_from_file(path)


def write_image(path, image: pyvips.Image):
    image.write_to_file(path)


def need_run_cropper(image_dir, crop_dir, bleed_edge, do_vibrance_bump):
    has_bleed_edge = bleed_edge is not None and bleed_edge > 0

    output_dir = crop_dir
    if do_vibrance_bump:
        output_dir = os.path.join(output_dir, "vibrance")
    if has_bleed_edge:
        output_dir = os.path.join(output_dir, str(bleed_edge).replace(".", "p"))

    if not os.path.exists(output_dir):
        return True

    input_files = list_image_files(image_dir)
    output_files = list_image_files(output_dir)
    return sorted(input_files) != sorted(output_files)


def crop_image(
    image: pyvips.Image, image_name, bleed_edge, max_dpi, print_fn=None
) -> pyvips.Image:
    print_fn = print_fn if print_fn is not None else lambda *args: args

    w, h = image.width, image.height
    (bw, bh) = card_size_with_bleed_inch
    dpi = min(w / bw, h / bh)
    c = round(0.12 * dpi)
    if bleed_edge is not None and bleed_edge > 0:
        bleed_edge_inch = mm_to_inch(bleed_edge)
        bleed_edge_pixel = dpi * bleed_edge_inch
        c = round(0.12 * min(w / bw, h / bh) - bleed_edge_pixel)
        print_fn(
            f"Cropping images...\n{image_name} - DPI calculated: {dpi}, cropping {c} pixels around frame (adjusted for bleed edge {bleed_edge}mm)"
        )
    else:
        print_fn(
            f"Cropping images...\n{image_name} - DPI calculated: {dpi}, cropping {c} pixels around frame"
        )
    cropped_image: pyvips.Image = image.crop(c, c, w - c * 2, h - c * 2)
    w, h = image.width, image.height
    if max_dpi is not None and dpi > max_dpi:
        new_w = int(round(w * max_dpi / dpi))
        new_h = int(round(h * max_dpi / dpi))

        print_fn(
            f"Cropping images...\n{image_name} - Exceeds maximum DPI {max_dpi}, resizing to {new_w}x{new_h}"
        )

        scale = max_dpi / dpi
        cropped_image = cropped_image.resize(scale, kernel=pyvips.enums.Kernel.CUBIC)
    return cropped_image


def uncrop_image(image: pyvips.Image, image_name, print_fn=None) -> pyvips.Image:
    print_fn = print_fn if print_fn is not None else lambda *args: args

    w, h = image.width, image.height
    (bw, bh) = card_size_without_bleed_inch
    dpi = min(w / bw, h / bh)
    c = round(dpi * 0.12)
    print_fn(
        f"Reinserting bleed edge...\n{image_name} - DPI calculated: {dpi}, adding {c} pixels around frame"
    )

    uncropped_image = pyvips.Image.black(w + c * 2, h + c * 2)
    return uncropped_image.insert(image, c, c)


def cropper(
    image_dir,
    crop_dir,
    img_cache,
    img_dict,
    bleed_edge,
    max_dpi,
    do_vibrance_bump,
    uncrop,
    print_fn,
):
    has_bleed_edge = bleed_edge is not None and bleed_edge > 0
    if has_bleed_edge:
        cropper(
            image_dir,
            crop_dir,
            img_cache,
            img_dict,
            None,
            max_dpi,
            do_vibrance_bump,
            uncrop,
            print_fn,
        )
    elif do_vibrance_bump:
        cropper(
            image_dir,
            crop_dir,
            img_cache,
            img_dict,
            None,
            max_dpi,
            False,
            uncrop,
            print_fn,
        )

    output_dir = crop_dir
    if do_vibrance_bump:
        output_dir = os.path.join(output_dir, "vibrance")
    if has_bleed_edge:
        output_dir = os.path.join(output_dir, str(bleed_edge).replace(".", "p"))
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    input_files = list_image_files(image_dir)
    for img_file in input_files:
        if os.path.exists(os.path.join(output_dir, img_file)):
            continue

        image = read_image(os.path.join(image_dir, img_file))
        cropped_image = crop_image(image, img_file, bleed_edge, max_dpi, print_fn)
        if do_vibrance_bump:
            cropped_image = pyvips.Image.new_from_array(
                PIL_Image.fromarray(cropped_image.numpy()).filter(vibrance_cube)
            )
        write_image(os.path.join(output_dir, img_file), cropped_image)

    extra_files = []

    output_files = list_image_files(output_dir)
    for img_file in output_files:
        if not os.path.exists(os.path.join(image_dir, img_file)):
            extra_files.append(img_file)

    if uncrop and not has_bleed_edge:
        for extra_img in extra_files:
            image = read_image(os.path.join(output_dir, extra_img))
            uncropped_image = uncrop_image(image, extra_img, print_fn)
            write_image(os.path.join(image_dir, extra_img), uncropped_image)
    else:
        for extra in extra_files:
            os.remove(os.path.join(output_dir, extra))

    if need_cache_previews(crop_dir, img_dict):
        cache_previews(img_cache, image_dir, crop_dir, print_fn, img_dict)


def image_from_bytes(bytes) -> pyvips.Image:
    img: pyvips.Image = None
    try:
        dataBytesIO = io.BytesIO(base64.b64decode(bytes))
        buffer = dataBytesIO.getvalue()
        img = pyvips.Image.new_from_buffer(buffer, options="")
    except Exception as e:
        pass

    if img is None:
        dataBytesIO = io.BytesIO(bytes)
        buffer = dataBytesIO.getvalue()
        img = pyvips.Image.new_from_buffer(buffer, options="")

    return img


def image_to_bytes(img: pyvips.Image):
    buffer = img.write_to_buffer(".png")
    bio = io.BytesIO(buffer)
    return bio.getvalue()


def to_bytes(file_or_bytes, resize=None):
    if isinstance(file_or_bytes, pyvips.Image):
        img = file_or_bytes
    elif isinstance(file_or_bytes, str):
        img = read_image(file_or_bytes)
    else:
        img = image_from_bytes(file_or_bytes)

    cur_width, cur_height = img.width, img.height
    if resize:
        new_width, new_height = resize
        scale = new_width / cur_width
        img = img.resize(
            scale,
            kernel=pyvips.enums.Kernel.NEAREST,
        )
        cur_width, cur_height = new_width, new_height
    return image_to_bytes(img), (cur_width, cur_height)


def need_cache_previews(crop_dir, img_dict):
    crop_list = list_image_files(crop_dir)

    for img in crop_list:
        if img not in img_dict.keys():
            return True

    for img, value in img_dict.items():
        if (
            "size" not in value
            or "thumb" not in value
            or "uncropped" not in value
            or img not in crop_list
        ):
            return True

    return False


def cache_previews(file, image_dir, crop_dir, print_fn, data):
    deleted_cards = []
    for img in data.keys():
        fn = os.path.join(crop_dir, img)
        if not os.path.exists(fn):
            deleted_cards.append(img)

    for img in deleted_cards:
        del data[img]

    for f in list_files(crop_dir, valid_image_extensions):
        has_img = f in data
        img_dict = data[f] if has_img else None

        has_size = has_img and "size" in img_dict
        has_thumbnail = has_img and "thumb" in img_dict
        need_img = not all([has_img, has_size, has_thumbnail])

        if need_img:
            img = read_image(os.path.join(crop_dir, f))
            w, h = img.width, img.height
            scale = 248 / w
            preview_size = (round(w * scale), round(h * scale))

            if not has_img or not has_size:
                print_fn(f"Caching preview for image {f}...\n")

                image_data, image_size = to_bytes(img, preview_size)
                data[f] = {
                    "data": str(image_data),
                    "size": image_size,
                }
                img_dict = data[f]

            if not has_thumbnail:
                print_fn(f"Caching thumbnail for image {f}...\n")

                thumb_data, thumb_size = to_bytes(
                    img, (preview_size[0] * 0.45, preview_size[1] * 0.45)
                )
                img_dict["thumb"] = {
                    "data": str(thumb_data),
                    "size": thumb_size,
                }

    for f in list_files(image_dir, valid_image_extensions):
        if f in data:
            img_dict = data[f]
            has_img = "uncropped" in img_dict
            if not has_img:
                img = read_image(os.path.join(image_dir, f))
                w, h = img.width, img.height
                scale = 186 / w
                uncropped_size = (round(w * scale), round(h * scale))

                if not has_img or not has_size:
                    print_fn(f"Caching uncropped preview for image {f}...\n")

                    image_data, image_size = to_bytes(img, uncropped_size)
                    img_dict["uncropped"] = {
                        "data": str(image_data),
                        "size": image_size,
                    }

    with open(file, "w") as fp:
        json.dump(data, fp, ensure_ascii=False)
