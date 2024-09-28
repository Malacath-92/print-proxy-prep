import os
import json

import image
import gui_qt
import project
from util import *
from config import *
from constants import *

app = None
window = None
img_dict = {}
print_dict = {}
print_json = os.path.join(cwd, "print.json")

def init():
    global img_dict
    global print_dict

    image.init()

    print_fn = (
        gui_qt.make_popup_print_fn(loading_window)
        if loading_window is not None
        else print
    )

    project.load(print_dict, img_dict, print_json, print_fn)

    image_dir = print_dict["image_dir"]
    crop_dir = os.path.join(image_dir, "crop")
    img_cache = print_dict["img_cache"]

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
            gui_qt.make_popup_print_fn(loading_window),
        )


app = gui_qt.init()

loading_window = gui_qt.popup(None, "Loading...")
loading_window.show_during_work(init)
del loading_window

window = gui_qt.window_setup(print_json, print_dict, img_dict)

gui_qt.event_loop(app)

with open(print_json, "w") as fp:
    json.dump(print_dict, fp)
window.close()
