import io
import cv2
import json
import numpy
import base64

from PIL import Image, ImageFilter

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


def init(image_dir, crop_dir):
    for folder in [image_dir, crop_dir]:
        if not os.path.exists(folder):
            os.mkdir(folder)

    def load_vibrance_cube():
        with open(os.path.join(cwd, "vibrance.CUBE")) as f:
            lut_raw = f.read().splitlines()[11:]
        lsize = round(len(lut_raw) ** (1 / 3))
        row2val = lambda row: tuple([float(val) for val in row.split(" ")])
        lut_table = [row2val(row) for row in lut_raw]
        lut = ImageFilter.Color3DLUT(lsize, lut_table)
        return lut

    global vibrance_cube
    vibrance_cube = load_vibrance_cube()


def read_image(path):
    with open(path, "rb") as f:
        bytes = bytearray(f.read())
        numpyarray = numpy.asarray(bytes, dtype=numpy.uint8)
        image = cv2.imdecode(numpyarray, cv2.IMREAD_UNCHANGED)
        return image


def write_image(path, image):
    with open(path, "wb") as f:
        _, bytes = cv2.imencode(".png", image)
        bytes.tofile(f)


def need_run_cropper(image_dir, crop_dir, bleed_edge):
    has_bleed_edge = bleed_edge is not None and bleed_edge > 0

    output_dir = crop_dir
    if has_bleed_edge:
        output_dir = os.path.join(output_dir, str(bleed_edge).replace(".", "p"))

    if not os.path.exists(output_dir):
        return True

    input_files = list_image_files(image_dir)
    output_files = list_image_files(output_dir)
    return sorted(input_files) != sorted(output_files)


def crop_image(image, image_name, bleed_edge, max_dpi, print_fn=None):
    print_fn = print_fn if print_fn is not None else lambda *args: args

    (h, w, _) = image.shape
    (bw, bh) = card_size_with_bleed_inch
    c = round(0.12 * min(w / bw, h / bh))
    dpi = c * (1 / 0.12)
    if bleed_edge > 0:
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
    cropped_image = image[c : h - c, c : w - c]
    (h, w, _) = cropped_image.shape
    if max_dpi is not None and dpi > max_dpi:
        new_size = (
            int(round(w * max_dpi / dpi)),
            int(round(h * max_dpi / dpi)),
        )
        print_fn(
            f"Cropping images...\n{image_name} - Exceeds maximum DPI {max_dpi}, resizing to {new_size[0]}x{new_size[1]}"
        )
        cropped_image = cv2.resize(
            cropped_image, new_size, interpolation=cv2.INTER_CUBIC
        )
        cropped_image = numpy.array(
            Image.fromarray(cropped_image).filter(ImageFilter.UnsharpMask(1, 20, 8))
        )
    return cropped_image


def cropper(
    image_dir,
    crop_dir,
    img_cache,
    img_dict,
    bleed_edge,
    max_dpi,
    do_vibrance_bump,
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
            print_fn,
        )

    output_dir = crop_dir
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
            cropped_image = numpy.array(
                Image.fromarray(cropped_image).filter(vibrance_cube)
            )
        write_image(os.path.join(output_dir, img_file), cropped_image)

    output_files = list_image_files(output_dir)
    for img_file in output_files:
        if not os.path.exists(os.path.join(image_dir, img_file)):
            os.remove(os.path.join(output_dir, img_file))

    if need_cache_previews(crop_dir, img_dict):
        cache_previews(img_cache, image_dir, crop_dir, print_fn, img_dict)


def image_from_bytes(bytes):
    try:
        dataBytesIO = io.BytesIO(base64.b64decode(bytes))
        buffer = dataBytesIO.getbuffer()
        img = cv2.imdecode(numpy.frombuffer(buffer, numpy.uint8), -1)
    except Exception as e:
        pass
    if img is None:
        dataBytesIO = io.BytesIO(bytes)
        buffer = dataBytesIO.getbuffer()
        img = cv2.imdecode(numpy.frombuffer(buffer, numpy.uint8), -1)
    return img


def to_bytes(file_or_bytes, resize=None):
    if isinstance(file_or_bytes, numpy.ndarray):
        img = file_or_bytes
    elif isinstance(file_or_bytes, str):
        img = read_image(file_or_bytes)
    else:
        img = image_from_bytes(file_or_bytes)

    (cur_height, cur_width, _) = img.shape
    if resize:
        new_width, new_height = resize
        scale = min(new_height / cur_height, new_width / cur_width)
        img = cv2.resize(
            img,
            (int(cur_width * scale), int(cur_height * scale)),
            interpolation=cv2.INTER_AREA,
        )
        cur_height, cur_width = new_height, new_width
    _, buffer = cv2.imencode(".png", img)
    bio = io.BytesIO(buffer)
    return bio.getvalue(), (cur_width, cur_height)


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
            (h, w, _) = img.shape
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
                (h, w, _) = img.shape
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
