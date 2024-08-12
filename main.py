import os
import json
import base64
import subprocess
import configparser
import io
import re
import cv2
import numpy
from PIL import Image, ImageFilter
import PySimpleGUI as sg
import easygui
import fallback_image as fallback
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter, A4, A3, legal

import pdf
from util import *
from constants import *


sg.theme("DarkTeal2")


def popup(middle_text):
    wnd = sg.Window(
        middle_text,
        [
            [sg.Sizer(v_pixels=20)],
            [sg.Sizer(h_pixels=20), sg.Text(middle_text, key="TEXT", justification="center"), sg.Sizer(h_pixels=20)],
            [sg.Sizer(v_pixels=20)],
        ],
        no_titlebar=True,
        finalize=True,
    )
    wnd.move_to_center()
    return wnd

def make_popup_print_fn(wnd):
    def popup_print_fn(text):
        print(text)
        wnd["TEXT"].update(text)
        wnd.refresh()
        wnd.move_to_center()
        wnd.refresh()
    return popup_print_fn


loading_window = popup("Loading...")
loading_window.refresh()

image_dir = os.path.join(cwd, "images")
crop_dir = os.path.join(image_dir, "crop")
print_json = os.path.join(cwd, "print.json")
img_cache = os.path.join(cwd, "img.cache")
for folder in [image_dir, crop_dir]:
    if not os.path.exists(folder):
        os.mkdir(folder)

config = configparser.ConfigParser()
config.read(os.path.join(cwd, "config.ini"))
cfg = config["DEFAULT"]


def load_vibrance_cube():
    with open(os.path.join(cwd, "vibrance.CUBE")) as f:
        lut_raw = f.read().splitlines()[11:]
    lsize = round(len(lut_raw) ** (1 / 3))
    row2val = lambda row: tuple([float(val) for val in row.split(" ")])
    lut_table = [row2val(row) for row in lut_raw]
    lut = ImageFilter.Color3DLUT(lsize, lut_table)
    return lut


vibrance_cube = load_vibrance_cube()
del load_vibrance_cube

    
def is_window_maximized(window):
    if not sg.running_linux():
        return window.TKroot.state() == 'zoomed'
    else:
        return '-fullscreen' in window.TKroot.attributes()


def grey_out(main_window):
    the_grey = sg.Window(
        title="",
        layout=[[]],
        alpha_channel=0.0,
        titlebar_background_color="#888888",
        background_color="#888888",
        size=main_window.size,
        disable_close=True,
        location=main_window.current_location(more_accurate=True),
        finalize=True,
    )
    if is_window_maximized(main_window):
        the_grey.maximize()
    the_grey.disable()
    the_grey.set_alpha(0.6)
    the_grey.refresh()
    return the_grey


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


def need_run_cropper(folder, bleed_edge):
    has_bleed_edge = bleed_edge is not None and bleed_edge > 0

    output_dir = crop_dir
    if has_bleed_edge:
        output_dir = os.path.join(output_dir, str(bleed_edge).replace(".", "p"))

    if not os.path.exists(output_dir):
        return True

    for img_file in list_files(folder):
        if os.path.splitext(img_file)[1] in [
            ".gif",
            ".jpg",
            ".jpeg",
            ".png",
        ] and not os.path.exists(os.path.join(output_dir, img_file)):
            return True

    return False


def cropper(folder, img_dict, bleed_edge, print_fn):
    has_bleed_edge = bleed_edge is not None and bleed_edge > 0
    if has_bleed_edge:
        img_dict = cropper(folder, img_dict, None, print_fn)

    i = 0
    output_dir = crop_dir
    if has_bleed_edge:
        output_dir = os.path.join(output_dir, str(bleed_edge).replace(".", "p"))
    if not os.path.exists(output_dir):
        os.mkdir(output_dir)
    for img_file in list_files(folder):
        if os.path.splitext(img_file)[1] not in [
            ".gif",
            ".jpg",
            ".jpeg",
            ".png",
        ] or os.path.exists(os.path.join(output_dir, img_file)):
            continue
        im = read_image(os.path.join(folder, img_file))
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
        max_dpi = cfg.getint("Max.DPI")
        if dpi > max_dpi:
            new_size = (
                int(round(w * cfg.getint("Max.DPI") / dpi)),
                int(round(h * cfg.getint("Max.DPI") / dpi)),
            )
            print_fn(
                f"Cropping images...\n{img_file} - Exceeds maximum DPI {max_dpi}, resizing to {new_size[0]}x{new_size[1]}"
            )
            crop_im = cv2.resize(crop_im, new_size, interpolation=cv2.INTER_CUBIC)
            crop_im = numpy.array(
                Image.fromarray(crop_im).filter(ImageFilter.UnsharpMask(1, 20, 8))
            )
        if cfg.getboolean("Vibrance.Bump"):
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


def img_frames_refresh(max_cols):
    frame_list = []
    for card_name, number in print_dict["cards"].items():
        if not os.path.exists(os.path.join(crop_dir, card_name)):
            print(f"{card_name} not found.")
            continue

        if card_name.startswith("__"):
            # Hiding files starting with double-underscore
            continue

        img_size = img_dict[card_name]["size"]
        backside_padding = 40
        padded_size = tuple(s + backside_padding for s in img_size)

        img_layout = [
            sg.Push(),
            sg.Graph(
                canvas_size=padded_size,
                graph_bottom_left=(0, 0),
                graph_top_right=padded_size,
                key=f"GPH:{card_name}",
                enable_events=True,
                drag_submits=True,
                motion_events=True,
            ),
            sg.Push(),
        ]
        button_layout = [
            sg.Push(),
            sg.Button(
                "-",
                key=f"SUB:{card_name}",
                target=f"NUM:{card_name}",
                size=(5, 1),
                enable_events=True,
            ),
            sg.Input(number, key=f"NUM:{card_name}", size=(5, 1)),
            sg.Button(
                "+",
                key=f"ADD:{card_name}",
                target=f"NUM:{card_name}",
                size=(5, 1),
                enable_events=True,
            ),
            sg.Push(),
        ]
        frame_layout = [[sg.Sizer(v_pixels=5)], img_layout, button_layout]
        title = (
            card_name
            if len(card_name) < 35
            else card_name[:28] + "..." + card_name[card_name.rfind(".") - 1 :]
        )
        frame_list += [
            sg.Frame(
                title=f" {title} ",
                layout=frame_layout,
                title_location=sg.TITLE_LOCATION_BOTTOM,
                vertical_alignment="center",
            ),
        ]
    new_frames = [
        frame_list[i : i + max_cols] for i in range(0, len(frame_list), max_cols)
    ]
    if len(new_frames) == 0:
        return sg.Push()
    return sg.Column(
        layout=new_frames, scrollable=True, vertical_scroll_only=True, expand_y=True
    )


def img_draw_single_graph(window, card_name, has_backside):
    graph = window["GPH:" + card_name]

    img_data = eval(img_dict[card_name]["data"])
    img_size = img_dict[card_name]["size"]

    backside_padding = 40

    graph.erase()
    graph.metadata = {}
    if has_backside:
        backside = (
            print_dict["backsides"][card_name]
            if card_name in print_dict["backsides"]
            else print_dict["backside_default"]
        )
        if backside in img_dict:
            backside = backside + "_preview"
            backside_data = eval(img_dict[backside]["data"])
            backside_size = img_dict[backside]["size"]
        else:
            backside_data = fallback.data
            backside_size = fallback.size

        padded_size = tuple(s + backside_padding for s in img_size)
        graph.set_size(padded_size)
        graph.change_coordinates(graph_bottom_left=(0, 0), graph_top_right=padded_size)

        graph.metadata["back_id"] = graph.draw_image(
            data=backside_data, location=(0, backside_size[1])
        )
        graph.metadata["front_id"] = graph.draw_image(
            data=img_data, location=(backside_padding, backside_padding + img_size[1])
        )
    else:
        padded_size = (img_size[0] + backside_padding, img_size[1])
        graph.set_size(padded_size)
        graph.change_coordinates(graph_bottom_left=(0, 0), graph_top_right=padded_size)

        graph.metadata["back_id"] = 0
        graph.metadata["front_id"] = graph.draw_image(
            data=img_data, location=(backside_padding / 2, padded_size[1])
        )


def img_draw_graphs(window):
    has_backside = print_dict["backside_enabled"]

    for card_name, number in print_dict["cards"].items():
        if not os.path.exists(os.path.join(crop_dir, card_name)):
            print(f"{card_name} not found.")
            continue

        if card_name.startswith("__"):
            # Hiding files starting with double-underscore
            continue

        img_draw_single_graph(window, card_name, has_backside)


def window_setup(cols):
    column_layout = [
        [
            sg.Button(button_text=" Config ", size=(10, 1), key="CONFIG"),
            sg.Text("Paper Size:"),
            sg.Combo(
                print_dict["page_sizes"],
                default_value=print_dict["pagesize"],
                readonly=True,
                key="PAPER",
            ),
            sg.VerticalSeparator(),
            sg.Text("Orientation:"),
            sg.Combo(
                ["Portrait", "Landscape"],
                default_value=print_dict["orient"],
                readonly=True,
                key="ORIENT",
            ),
            sg.VerticalSeparator(),
            sg.Text("Bleed Edge (mm):"),
            sg.Input(
                print_dict["bleed_edge"], size=(6, 1), key="BLEED", enable_events=True
            ),
            sg.VerticalSeparator(),
            sg.Button(button_text=" Select All ", size=(10, 1), key="SELECT"),
            sg.Button(button_text=" Unselect All ", size=(10, 1), key="UNSELECT"),
            sg.VerticalSeparator(),
            sg.Text("PDF Filename:"),
            sg.Input(
                print_dict["filename"], size=(20, 1), key="FILENAME", enable_events=True
            ),
            sg.Push(),
            sg.Button(button_text=" Run Cropper ", size=(10, 1), key="CROP"),
            sg.Button(button_text=" Save Project ", size=(10, 1), key="SAVE"),
            sg.Button(button_text=" Render PDF ", size=(10, 1), key="RENDER"),
        ],
        [
            sg.Checkbox(
                "Backside",
                key="ENABLE_BACKSIDE",
                default=print_dict["backside_enabled"],
            ),
            sg.Button(
                button_text=" Default ",
                size=(10, 1),
                key="DEFAULT_BACKSIDE",
                disabled=not print_dict["backside_enabled"],
            ),
            sg.Text("Offset (mm):"),
            sg.Input(
                print_dict["backside_offset"],
                size=(6, 1),
                key="OFFSET_BACKSIDE",
                enable_events=True,
            ),
            sg.Push(),
        ],
        [
            sg.Frame(
                title="Card Images",
                layout=[[img_frames_refresh(cols)]],
                expand_y=True,
                expand_x=True,
            ),
        ],
    ]
    layout = [
        [
            sg.Column(layout=column_layout, expand_y=True),
        ],
    ]
    window = sg.Window(
        "PDF Proxy Printer",
        layout,
        alpha_channel=0.0,
        resizable=True,
        finalize=True,
        element_justification="center",
        enable_close_attempted_event=True,
        size=print_dict["size"],
    )

    window.maximize()
    window.timer_start(100, repeating=False)

    img_draw_graphs(window)

    for card_name in print_dict["cards"].keys():
        if card_name.startswith("__"):
            continue

        def make_number_callback(key):
            def number_callback(var, index, mode):
                window.write_event_value(key, window[key].TKStringVar.get())

            return number_callback

        window[f"NUM:{card_name}"].TKStringVar.trace(
            "w", make_number_callback(f"NUM:{card_name}")
        )

    def make_combo_callback(key):
        def combo_callback(var, index, mode):
            window.write_event_value(key, window[key].TKStringVar.get())

        return combo_callback

    window["PAPER"].TKStringVar.trace("w", make_combo_callback("PAPER"))
    window["ORIENT"].TKStringVar.trace("w", make_combo_callback("ORIENT"))

    def reset_button(button):
        button.set_tooltip(None)
        button.update(disabled=False)

    def crop_callback(var, index, mode):
        reset_button(window["RENDER"])

    window["CROP"].TKStringVar.trace("w", crop_callback)

    def bleed_callback(var, index, mode):
        bleed_input = window["BLEED"]
        bleed_edge = bleed_input.TKStringVar.get()
        bleed_edge = cap_bleed_edge_str(bleed_edge)
        if bleed_edge != bleed_input.TKStringVar.get():
            bleed_input.update(bleed_edge)

        if is_number_string(bleed_edge):
            reset_button(window["RENDER"])
            reset_button(window["CROP"])

            bleed_edge_num = float(bleed_edge)
            if bleed_edge != print_dict["bleed_edge"] and need_run_cropper(
                image_dir, bleed_edge_num
            ):
                render_button = window["RENDER"]
                render_button.set_tooltip("Bleed edge changed, re-run cropper first...")
                render_button.update(disabled=True)
        else:

            def set_invalid_bleed_edge_tooltip(button):
                button.set_tooltip("Bleed edge not a valid number...")
                button.update(disabled=True)

            set_invalid_bleed_edge_tooltip(window["RENDER"])
            set_invalid_bleed_edge_tooltip(window["CROP"])

    window["BLEED"].TKStringVar.trace("w", bleed_callback)

    def enable_backside_callback(var, index, mode):
        default_backside_button = window["DEFAULT_BACKSIDE"]
        offset_backside_button = window["OFFSET_BACKSIDE"]
        backside_enabled = window["ENABLE_BACKSIDE"].TKIntVar.get() != 0
        print_dict["backside_enabled"] = backside_enabled
        if backside_enabled:
            reset_button(default_backside_button)
            reset_button(offset_backside_button)
        else:
            default_backside_button.update(disabled=True)
            offset_backside_button.update(disabled=True)
        img_draw_graphs(window)

    window["ENABLE_BACKSIDE"].TKIntVar.trace("w", enable_backside_callback)

    def backside_offset_callback(var, index, mode):
        offset_input = window["OFFSET_BACKSIDE"]
        offset = offset_input.TKStringVar.get()
        offset = cap_offset_str(offset)
        if offset != offset_input.TKStringVar.get():
            offset_input.update(offset)

        render_button = window["RENDER"]
        if is_number_string(offset):
            print_dict["backside_offset"] = offset
            reset_button(render_button)
        else:
            render_button.set_tooltip("Backside offset not a valid number...")
            render_button.update(disabled=True)

    window["OFFSET_BACKSIDE"].TKStringVar.trace("w", backside_offset_callback)

    window.bind("<Configure>", "Event")

    for card_name, _ in print_dict["cards"].items():
        if card_name.startswith("__") or not os.path.exists(
            os.path.join(crop_dir, card_name)
        ):
            continue
        window["GPH:" + card_name].bind("<Leave>", f"-Leave")

    return window


def load_img_dict():
    crop_list = list_files(crop_dir)
    img_dict = {}
    if os.path.exists(img_cache):
        with open(img_cache, "r") as fp:
            img_dict = json.load(fp)
    img_cache_needs_refresh = len(img_dict.keys()) < len(crop_list)
    if not img_cache_needs_refresh:
        for _, value in img_dict.items():
            if 'size' not in value:
                img_cache_needs_refresh = True
                break
    if img_cache_needs_refresh:
        print_fn = make_popup_print_fn(loading_window) if loading_window is not None else print
        img_dict = cache_previews(img_cache, crop_dir, print_fn, img_dict)
    return img_dict
img_dict = cropper(image_dir, load_img_dict(), None, make_popup_print_fn(loading_window))


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

    default_page_size = cfg.get("Paper.Size", "Letter")
    default_print_dict = {
        "cards": {},
        # program window settings
        "size": (None, None),
        "columns": 5,
        # backside options
        "backside_enabled": False,
        "backside_default": "__back.png",
        "backside_offset": "0",
        "backsides": {},
        # pdf generation options
        "pagesize": default_page_size if default_page_size in page_sizes else "Letter",
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
    print_dict['size'] = tuple(print_dict['size'])

    # deselect images starting with __
    for img in list_files(crop_dir):
        print_dict["cards"][img] = 0 if img.startswith("__") else 1
    
    return print_dict
print_dict = load_print_dict()

bleed_edge = float(print_dict["bleed_edge"])
if need_run_cropper(image_dir, bleed_edge):
    cropper(image_dir, img_dict, bleed_edge, make_popup_print_fn(loading_window))

window = window_setup(print_dict["columns"])
for k in window.key_dict.keys():
    if "CRD:" in str(k):
        window[k].bind("<Button-1>", "-LEFT")
        window[k].bind("<Button-3>", "-RIGHT")
loading_window.close()
loading_window = None
hover_backside = False

while True:
    event, values = window.read()

    if event == sg.WIN_CLOSED or event == sg.WINDOW_CLOSE_ATTEMPTED_EVENT:
        break

    def get_card_name_from_event(event):
        name = event[4:]
        name = name.replace("+MOVE", "")
        name = name.replace("+UP", "")
        if "-RIGHT" in name:
            name = name.replace("-RIGHT", "")
            e = "SUB:"
        elif "-LEFT" in name:
            name = name.replace("-LEFT", "")
            e = "ADD:"
        else:
            e = event[:4]
        return name, e

    if "GPH:" in event:
        if "-Leave" in event:
            key = event[:-6]
            graph = window[key]
            graph.bring_figure_to_front(graph.metadata["front_id"])

        elif "+MOVE" in event:
            name, e = get_card_name_from_event(event)
            key = "GPH:" + name
            pos = values[key]

            graph = window[key]
            if graph.metadata:
                figures = graph.get_figures_at_location(pos)
                if graph.metadata["back_id"] in figures:
                    hover_backside = True
                    graph.bring_figure_to_front(graph.metadata["back_id"])
                else:
                    hover_backside = False
                    graph.bring_figure_to_front(graph.metadata["front_id"])

        elif hover_backside:
            if path := easygui.fileopenbox(default="images/*"):
                path = os.path.relpath(path, os.path.abspath("images"))
                name, e = get_card_name_from_event(event)
                print_dict["backsides"][name] = path

                has_backside = print_dict["backside_enabled"]
                img_draw_single_graph(window, name, has_backside)

    if event[:4] in ("ADD:", "SUB:"):
        name, e = get_card_name_from_event(event)
        key = "NUM:" + name
        num = int(values[key])
        num += 1 if "ADD" in e else 0 if num <= 0 else -1
        print_dict["cards"][name] = num
        window[key].update(str(num))

    if "NUM:" in event:
        name, e = get_card_name_from_event(event)
        if is_number_string(values[event]):
            print_dict["cards"][name] = int(values[event])

    if "ORIENT" in event:
        print_dict["orient"] = values[event]

    if "PAPER" in event:
        print_dict["pagesize"] = values[event]

    if "BLEED" in event:
        print_dict["bleed_edge"] = window["BLEED"].get()

    if "FILENAME" in event:
        print_dict["filename"] = window["FILENAME"].get()

    if "CONFIG" in event:
        subprocess.Popen(["config.ini"], shell=True)

    if "SAVE" in event:
        with open(print_json, "w") as fp:
            json.dump(print_dict, fp)

    if event in ["CROP", "RENDER"]:
        config.read(os.path.join(cwd, "config.ini"))
        cfg = config["DEFAULT"]

    if "CROP" in event:
        bleed_edge = float(print_dict["bleed_edge"])
        if need_run_cropper(image_dir, bleed_edge):
            window.disable()
            grey_window = grey_out(window)

            crop_window = popup("Rendering...")
            crop_window.refresh()
            img_dict = cropper(image_dir, img_dict, bleed_edge, make_popup_print_fn(crop_window))
            crop_window.close()

            needs_rebuild = False
            for img in list_files(crop_dir):
                if img not in print_dict["cards"].keys():
                    print(f"{img} found and added to list.")
                    print_dict["cards"][img] = 1
                    needs_rebuild = True

            grey_window.close()

            if needs_rebuild:
                old_window = window
                window = window_setup(print_dict["columns"])
                window.enable()
                window.bring_to_front()
                old_window.close()

                for k in window.key_dict.keys():
                    if "CRD:" in str(k):
                        window[k].bind("<Button-1>", "-LEFT")
                        window[k].bind("<Button-3>", "-RIGHT")
            else:
                window.enable()
                window.bring_to_front()
            window.refresh()
        else:
            print("Not running cropper, no need...")

    if "RENDER" in event:
        rgx = re.compile(r"\W")
        pdf_path = os.path.join(
            cwd,
            (
                f"{re.sub(rgx, '', print_dict['filename'])}.pdf"
                if len(print_dict["filename"]) > 0
                else "_printme.pdf"
            ),
        )
        
        window.disable()
        grey_window = grey_out(window)

        render_window = popup("Rendering...")
        render_window.refresh()
        pages = pdf.generate(print_dict, crop_dir, page_sizes[print_dict["pagesize"]], pdf_path, make_popup_print_fn(render_window))
        render_window.close()

        saving_window = popup("Saving...")
        saving_window.refresh()
        pages.save()
        saving_window.close()

        grey_window.close()
        window.enable()
        window.bring_to_front()
        window.refresh()
        
        try:
            subprocess.Popen([pdf_path], shell=True)
        except Exception as e:
            print(e)

    if "UNSELECT" in event:
        for card_name in print_dict["cards"].keys():
            print_dict["cards"][card_name] = 0
            if not card_name.startswith("__"):
                window[f"NUM:{card_name}"].update("0")
    elif "SELECT" in event:
        for card_name in print_dict["cards"].keys():
            print_dict["cards"][card_name] = 1
            if not card_name.startswith("__"):
                window[f"NUM:{card_name}"].update("1")

    if event in ["DEFAULT_BACKSIDE"]:
        if path := easygui.fileopenbox(default="images/*"):
            print_dict["backside_default"] = os.path.relpath(
                path, os.path.abspath("images")
            )
            img_draw_graphs(window)

    if is_window_maximized(window):
        print_dict["size"] = (None, None)
    else:
        print_dict["size"] = window.size
    
    if event == sg.EVENT_TIMER:
        window.set_alpha(1)

with open(print_json, "w") as fp:
    json.dump(print_dict, fp)
window.close()
