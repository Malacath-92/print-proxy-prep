import io
import cv2
import json
import numpy
import base64

from PIL import Image, ImageFilter

from util import *
from constants import *


vibrance_cube = None


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

    for img_file in list_files(image_dir):
        if os.path.splitext(img_file)[1] in [
            ".gif",
            ".jpg",
            ".jpeg",
            ".png",
        ] and not os.path.exists(os.path.join(output_dir, img_file)):
            return True

    return False


def cropper(image_dir, crop_dir, img_cache, img_dict, bleed_edge, max_dpi, do_vibrance_bump, print_fn):
    has_bleed_edge = bleed_edge is not None and bleed_edge > 0
    if has_bleed_edge:
        img_dict = cropper(image_dir, crop_dir, img_cache, img_dict, None, max_dpi, do_vibrance_bump, print_fn)

    i = 0
    output_dir = crop_dir
    if has_bleed_edge:
        output_dir = os.path.join(output_dir, str(bleed_edge).replace(".", "p"))
    if not os.path.exists(output_dir):
        os.mkdir(output_dir)
    for img_file in list_files(image_dir):
        if os.path.splitext(img_file)[1] not in [
            ".gif",
            ".jpg",
            ".jpeg",
            ".png",
        ] or os.path.exists(os.path.join(output_dir, img_file)):
            continue
        im = read_image(os.path.join(image_dir, img_file))
        i += 1
        (h, w, _) = im.shape
        (bw, bh) = card_size_with_bleed_inch
        c = round(0.12 * min(w / bw, h / bh))
        dpi = c * (1 / 0.12)
        if has_bleed_edge:
            bleed_edge_inch = mm_to_inch(bleed_edge)
            bleed_edge_pixel = dpi * bleed_edge_inch
            c = round(0.12 * min(w / bw, h / bh) - bleed_edge_pixel)
            print_fn(
                f"Cropping images...\n{img_file} - DPI calculated: {dpi}, cropping {c} pixels around frame (adjusted for bleed edge)"
            )
        else:
            print_fn(
                f"Cropping images...\n{img_file} - DPI calculated: {dpi}, cropping {c} pixels around frame"
            )
        crop_im = im[c : h - c, c : w - c]
        (h, w, _) = crop_im.shape
        if dpi > max_dpi:
            new_size = (
                int(round(w * max_dpi / dpi)),
                int(round(h * max_dpi / dpi)),
            )
            print_fn(
                f"Cropping images...\n{img_file} - Exceeds maximum DPI {max_dpi}, resizing to {new_size[0]}x{new_size[1]}"
            )
            crop_im = cv2.resize(crop_im, new_size, interpolation=cv2.INTER_CUBIC)
            crop_im = numpy.array(
                Image.fromarray(crop_im).filter(ImageFilter.UnsharpMask(1, 20, 8))
            )
        if do_vibrance_bump:
            crop_im = numpy.array(Image.fromarray(crop_im).filter(vibrance_cube))
        write_image(os.path.join(output_dir, img_file), crop_im)

    if i > 0 and not has_bleed_edge:
        return cache_previews(img_cache, output_dir, print_fn)
    else:
        return img_dict


def to_bytes(file_or_bytes, resize=None):
    """
    Will convert into bytes and optionally resize an image that is a file or a base64 bytes object.
    Turns into PNG format in the process so that can be displayed by tkinter
    :param file_or_bytes: either a string filename or a bytes base64 image object
    :param resize:  optional new size
    :return: (bytes) a byte-string object
    """
    if isinstance(file_or_bytes, str):
        img = read_image(file_or_bytes)
    else:
        try:
            dataBytesIO = io.BytesIO(base64.b64decode(file_or_bytes))
            buffer = dataBytesIO.getbuffer()
            img = cv2.imdecode(numpy.frombuffer(buffer, numpy.uint8), -1)
        except Exception as e:
            dataBytesIO = io.BytesIO(file_or_bytes)
            buffer = dataBytesIO.getbuffer()
            img = cv2.imdecode(numpy.frombuffer(buffer, numpy.uint8), -1)

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
    del img
    return bio.getvalue(), (cur_width, cur_height)


def cache_previews(file, folder, print_fn, data={}):
    for f in list_files(folder):
        if f in data.keys() and 'size' in data[f]:
            continue
        print_fn(f"Caching previews...\n{f}")

        fn = os.path.join(folder, f)
        im = read_image(fn)
        (h, w, _) = im.shape
        del im
        r = 248 / w
        image_data, image_size = to_bytes(fn, (round(w * r), round(h * r)))
        data[f] = {
            "data": str(image_data),
            "size": image_size,
        }
        preview_data, preview_size = to_bytes(
            fn, (image_size[0] * 0.45, image_size[1] * 0.45)
        )
        data[f + "_preview"] = {
            "data": str(preview_data),
            "size": preview_size,
        }

    with open(file, "w") as fp:
        json.dump(data, fp, ensure_ascii=False)
    return data
