import os
import json

import util
import image
from config import *
from constants import *


def load(print_dict, img_dict, json_path, print_fn):
    if os.path.exists(json_path):
        with open(json_path, "r") as fp:
            loaded_print_dict = json.load(fp)
            print_dict.clear()
            for key, value in loaded_print_dict.items():
                print_dict[key] = value
    else:
        return

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
        # pdf generation options
        "pagesize": (
            default_page_size if default_page_size in page_sizes else "Letter"
        ),
        "extended_guides": True,
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

    # Get all image files in the crop directory
    crop_list = image.list_image_files(crop_dir)

    # Check that we have all our cards accounted for
    for img in crop_list:
        if img not in print_dict["cards"].keys():
            print_dict["cards"][img] = 0 if img.startswith("__") else 1

    # And also check we don't have stale cards in here
    stale_images = []
    for img in print_dict["cards"].keys():
        if img not in crop_list:
            stale_images.append(img)
    for img in stale_images:
        del print_dict["cards"][img]

    # Make sure we have a sensible bleed edge
    bleed_edge = str(print_dict["bleed_edge"])
    bleed_edge = util.cap_bleed_edge_str(bleed_edge)
    if not util.is_number_string(bleed_edge):
        bleed_edge = "0"
    print_dict["bleed_edge"] = bleed_edge

    # Initialize the image amount
    for img in crop_list:
        if img not in print_dict["cards"].keys():
            print_dict["cards"][img] = 1

    # deselect images starting with __
    for img in crop_list:
        print_dict["cards"][img] = (
            0 if img.startswith("__") else print_dict["cards"][img]
        )

    image.init_image_folder(image_dir, crop_dir)

    img_cache = print_dict["img_cache"]

    if os.path.exists(img_cache):
        with open(img_cache, "r") as fp:
            loaded_img_dict = json.load(fp)
            img_dict.clear()
            for key, value in loaded_img_dict.items():
                img_dict[key] = value

    if image.need_cache_previews(crop_dir, img_dict):
        image.cache_previews(img_cache, image_dir, crop_dir, print_fn, img_dict)
