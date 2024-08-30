import os
import json

import image
import gui_qt
from util import *
from constants import *


gui = gui_qt

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
        crop_list = list_files(crop_dir)
        img_dict = {}
        if os.path.exists(img_cache):
            with open(img_cache, "r") as fp:
                img_dict = json.load(fp)
        img_cache_needs_refresh = len(img_dict.keys()) < len(crop_list)
        if not img_cache_needs_refresh:
            for _, value in img_dict.items():
                if "size" not in value:
                    img_cache_needs_refresh = True
                    break
        if img_cache_needs_refresh:
            print_fn = (
                gui.make_popup_print_fn(loading_window)
                if loading_window is not None
                else print
            )
            image.cache_previews(img_cache, crop_dir, print_fn, img_dict)
        return img_dict

    img_dict = load_img_dict()
    image.cropper(
        image_dir,
        crop_dir,
        img_cache,
        img_dict,
        None,
        CFG.getint("Max.DPI"),
        CFG.getboolean("Vibrance.Bump"),
        gui.make_popup_print_fn(loading_window),
    )

    def load_print_dict():
        print_dict = {}
        if os.path.exists(print_json):
            with open(print_json, "r") as fp:
                print_dict = json.load(fp)
            # Check that we have all our cards accounted for
            if len(print_dict["cards"].items()) < len(list_files(crop_dir)):
                for img in list_files(crop_dir):
                    if img not in print_dict["cards"].keys():
                        print_dict["cards"][img] = 0 if img.startswith("__") else 1
            # Make sure we have a sensible bleed edge
            bleed_edge = print_dict["bleed_edge"]
            bleed_edge = cap_bleed_edge_str(bleed_edge)
            if not is_number_string(bleed_edge):
                bleed_edge = "0"
            print_dict["bleed_edge"] = bleed_edge

        default_page_size = CFG.get("Paper.Size", "Letter")
        default_print_dict = {
            "cards": { "dummy": 1 },
            # program window settings
            "size": (None, None),  # only used by the PySimpleGui implementation
            "columns": 5,
            # backside options
            "backside_enabled": False,
            "backside_default": "__back.png",
            "backside_offset": "0",
            "backsides": {},
            # pdf generation options
            "pagesize": (
                default_page_size if default_page_size in page_sizes else "Letter"
            ),
            "page_sizes": list(page_sizes.keys()),
            "orient": "Portrait",
            "bleed_edge": "0",
            "filename": "_printme",
        }

        # Initialize our values
        for key, value in default_print_dict.items():
            if key not in print_dict:
                print_dict[key] = value

        # Make sure the size is a tuple, not a list
        print_dict["size"] = tuple(print_dict["size"])

        # Initialize the image amount
        for img in list_files(crop_dir):
            if img not in print_dict["cards"].keys():
                print_dict["cards"][img] = 1

        # deselect images starting with __
        for img in list_files(crop_dir):
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
            CFG.getint("Max.DPI"),
            CFG.getboolean("Vibrance.Bump"),
            gui.make_popup_print_fn(loading_window),
        )


app = gui.init()

loading_window = gui.popup(None, "Loading...")
loading_window.show_during_work(init)
del loading_window

window = gui.window_setup(
    image_dir, crop_dir, print_json, print_dict, img_dict, img_cache
)

gui.event_loop(
    app, window, image_dir, crop_dir, print_json, print_dict, img_dict, img_cache
)

with open(print_json, "w") as fp:
    json.dump(print_dict, fp)
window.close()
