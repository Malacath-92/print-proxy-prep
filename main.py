import os
import json

import image
import gui_qt
from util import *
from constants import *

image_dir = os.path.join(cwd, "images")
crop_dir = os.path.join(image_dir, "crop")
print_json = os.path.join(cwd, "print.json")
img_cache = os.path.join(cwd, "img.cache")

app = None
window = None
img_dict = None
print_dict = None


def init():
    global img_dict
    global print_dict

    image.init(image_dir, crop_dir)

    def load_img_dict():
        img_dict = {}
        if os.path.exists(img_cache):
            with open(img_cache, "r") as fp:
                img_dict = json.load(fp)

        if image.need_cache_previews(crop_dir, img_dict):
            print_fn = (
                gui_qt.make_popup_print_fn(loading_window)
                if loading_window is not None
                else print
            )
            image.cache_previews(img_cache, image_dir, crop_dir, print_fn, img_dict)

        return img_dict

    img_dict = load_img_dict()
    image.cropper(
        image_dir,
        crop_dir,
        img_cache,
        img_dict,
        None,
        CFG.MaxDPI,
        CFG.VibranceBump,
        CFG.EnableUncrop,
        gui_qt.make_popup_print_fn(loading_window),
    )

    def load_print_dict():
        # Get all image files in the crop directory
        crop_list = image.list_image_files(crop_dir)

        print_dict = {}
        if os.path.exists(print_json):
            with open(print_json, "r") as fp:
                print_dict = json.load(fp)

            # Check that we have all our cards accounted for
            for img in crop_list:
                if img not in print_dict["cards"].keys():
                    print_dict["cards"][img] = 0 if img.startswith("__") else 1

            # Make sure we have a sensible bleed edge
            bleed_edge = str(print_dict["bleed_edge"])
            bleed_edge = cap_bleed_edge_str(bleed_edge)
            if not is_number_string(bleed_edge):
                bleed_edge = "0"
            print_dict["bleed_edge"] = bleed_edge

        default_page_size = CFG.DefaultPageSize
        default_print_dict = {
            # list of all cards
            "cards": {"dummy": 1},
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

        # Initialize our values
        for key, value in default_print_dict.items():
            if key not in print_dict:
                print_dict[key] = value
        for key, value in default_print_dict["cards"].items():
            if key not in print_dict["cards"]:
                print_dict["cards"][key] = value

        # Make sure the size is a tuple, not a list
        print_dict["size"] = tuple(print_dict["size"])

        # Initialize the image amount
        for img in crop_list:
            if img not in print_dict["cards"].keys():
                print_dict["cards"][img] = 1

        # deselect images starting with __
        for img in crop_list:
            print_dict["cards"][img] = (
                0 if img.startswith("__") else print_dict["cards"][img]
            )

        return print_dict

    print_dict = load_print_dict()

    bleed_edge = float(print_dict["bleed_edge"])
    if image.need_run_cropper(image_dir, crop_dir, bleed_edge):
        image.cropper(
            image_dir,
            crop_dir,
            img_cache,
            img_dict,
            bleed_edge,
            CFG.MaxDPI,
            CFG.VibranceBump,
            CFG.EnableUncrop,
            gui_qt.make_popup_print_fn(loading_window),
        )


app = gui_qt.init()

loading_window = gui_qt.popup(None, "Loading...")
loading_window.show_during_work(init)
del loading_window

window = gui_qt.window_setup(
    image_dir, crop_dir, print_json, print_dict, img_dict, img_cache
)

gui_qt.event_loop(
    app, window, image_dir, crop_dir, print_json, print_dict, img_dict, img_cache
)

with open(print_json, "w") as fp:
    json.dump(print_dict, fp)
window.close()
