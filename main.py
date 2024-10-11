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


def init():
    global img_dict
    global print_dict

    image.init()

    print_fn = (
        gui_qt.make_popup_print_fn(loading_window)
        if loading_window is not None
        else print
    )

    project.load(print_dict, img_dict, app.json_path(), print_fn)


app = gui_qt.init()

loading_window = gui_qt.popup(None, "Loading...")
loading_window.show_during_work(init)
del loading_window

window = gui_qt.window_setup(app, print_dict, img_dict)

gui_qt.event_loop(app)

with open(app.json_path(), "w") as fp:
    json.dump(print_dict, fp)

app.close()
