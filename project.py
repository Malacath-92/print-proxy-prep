import os
import json
import time

import util
import image
from config import *
from constants import *


def init_dict(print_dict, img_dict):
    default_page_size = CFG.DefaultPageSize
    default_print_dict = {
        # project options
        "image_dir": "images",
        "img_cache": "img.cache",
        # list of all cards
        "cards": {},
        # backside options
        "backside_enabled": False,
        "backside_default": "__back.png",
        "backside_offset": "0",
        "backsides": {},
        "backside_short_edge": {},
        # oversized options
        "oversized_enabled": False,
        "oversized": {},
        # pdf generation options
        "pagesize": (
            default_page_size if default_page_size in page_sizes else "Letter"
        ),
        "enable_guides": True,
        "extended_guides": True,
        "guide_color_a": 0xBFBFBF,
        "guide_color_b": 0x000000,
        "orient": "Portrait",
        "bleed_edge": "0",
        "filename": "_printme",
    }

    # Initialize our default values
    for key, value in default_print_dict.items():
        if key not in print_dict:
            print_dict[key] = value

    # Get project folders
    image_dir = print_dict["image_dir"]
    crop_dir = os.path.join(image_dir, "crop")
    image.init_image_folder(image_dir, crop_dir)

    # Get all image files in the crop and/or images directory
    images = image.list_image_files(image_dir)
    if CFG.EnableUncrop:
        crop_images = image.list_image_files(image_dir)
        crop_images = [img for img in crop_images if img not in images]
        images.extend(crop_images)

    # Check that we have all our cards accounted for
    for img in images:
        if img not in print_dict["cards"].keys():
            print_dict["cards"][img] = 0 if img.startswith("__") else 1

    # And also check we don't have stale cards in here
    stale_images = []
    for img in print_dict["cards"].keys():
        if img not in images:
            stale_images.append(img)
    for img in stale_images:
        del print_dict["cards"][img]
        if img in print_dict["backsides"]:
            del print_dict["backsides"][img]
        if img in print_dict["backside_short_edge"]:
            del print_dict["backside_short_edge"][img]
        if img in print_dict["oversized"]:
            del print_dict["oversized"][img]

    # Make sure we have a sensible bleed edge
    bleed_edge = str(print_dict["bleed_edge"])
    bleed_edge = util.cap_bleed_edge_str(bleed_edge)
    if not util.is_number_string(bleed_edge):
        bleed_edge = "0"
    print_dict["bleed_edge"] = bleed_edge

    # Initialize the image amount
    for img in images:
        if img not in print_dict["cards"].keys():
            print_dict["cards"][img] = 1

    # Deselect images starting with __
    for img in images:
        print_dict["cards"][img] = (
            0 if img.startswith("__") else print_dict["cards"][img]
        )

    # Initialize image cache
    img_cache = print_dict["img_cache"]
    if os.path.exists(img_cache):
        with open(img_cache, "r") as fp:
            loaded_img_dict = json.load(fp)
            img_dict.clear()
            for key, value in loaded_img_dict.items():
                img_dict[key] = value


def init_images(print_dict, img_dict, print_fn):
    image_dir = print_dict["image_dir"]
    crop_dir = os.path.join(image_dir, "crop")
    img_cache = print_dict["img_cache"]

    # setup crops
    bleed_edge = float(print_dict["bleed_edge"])
    if image.need_run_cropper(image_dir, crop_dir, bleed_edge, CFG.VibranceBump):
        image.cropper(
            image_dir,
            crop_dir,
            img_cache,
            img_dict,
            bleed_edge,
            CFG.MaxDPI,
            CFG.VibranceBump,
            CFG.EnableUncrop,
            print_fn,
        )

    # setup image previews
    img_cache = print_dict["img_cache"]
    if image.need_cache_previews(crop_dir, img_dict):
        image.cache_previews(img_cache, image_dir, crop_dir, print_fn, img_dict)


def load(print_dict, img_dict, json_path, print_fn):
    try:
        with open(json_path, "r") as fp:
            loaded_print_dict = json.load(fp)
            for key, value in loaded_print_dict.items():
                print_dict[key] = value
    except:
        print_fn("Error: Failed loading project... Resetting...")
        time.sleep(1)
        print_dict.clear()

    init_dict(print_dict, img_dict)
    init_images(print_dict, img_dict, print_fn)
