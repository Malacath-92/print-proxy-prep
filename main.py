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

sw, sh = sg.Window.get_screen_size()
sg.theme("DarkTeal2")


def popup(middle_text):
    return sg.Window(
        middle_text,
        [
            [sg.Sizer(v_pixels=20)],
            [sg.Sizer(h_pixels=20), sg.Text(middle_text), sg.Sizer(h_pixels=20)],
            [sg.Sizer(v_pixels=20)],
        ],
        no_titlebar=True,
        finalize=True,
    )


loading_window = popup("Loading...")
loading_window.refresh()
stroke = True
cwd = os.path.dirname(__file__)
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

card_size_with_bleed_inch = (2.72, 3.7)
card_size_without_bleed_inch = (2.48, 3.46)


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


def list_files(folder):
    return [f for f in os.listdir(folder) if os.path.isfile(os.path.join(folder, f))]


def mm_to_inch(mm):
    return mm * 0.0393701


def mm_to_point(mm):
    return inch_to_point(mm_to_inch(mm))


def inch_to_mm(inch):
    return inch / 0.0393701


def inch_to_point(inch):
    return inch * 72


def is_number_string(str):
    return str.replace(".", "", 1).isdigit()


def cap_bleed_edge_str(bleed_edge):
    if is_number_string(bleed_edge):
        bleed_edge_num = float(bleed_edge)
        max_bleed_edge = inch_to_mm(0.12)
        if bleed_edge_num > max_bleed_edge:
            bleed_edge_num = min(bleed_edge_num, max_bleed_edge)
            bleed_edge = "{:.2f}".format(bleed_edge_num)
    return bleed_edge


def cap_offset_str(offset):
    if is_number_string(offset):
        offset_num = float(offset)
        max_offset = 10.0
        if offset_num > max_offset:
            offset_num = min(offset_num, max_offset)
            offset = "{:.2f}".format(offset_num)
    return offset


def grey_out(main_window):
    the_grey = sg.Window(
        title="",
        layout=[[]],
        alpha_channel=0.6,
        titlebar_background_color="#888888",
        background_color="#888888",
        size=main_window.size,
        disable_close=True,
        location=main_window.current_location(more_accurate=True),
        finalize=True,
    )
    the_grey.disable()
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


# Draws black-white dashed cross at `x`, `y`
def draw_cross(can, x, y, c=6, s=1):
    dash = [s, s]
    can.setLineWidth(s)

    # First layer
    can.setDash(dash)
    can.setStrokeColorRGB(255, 255, 255)
    can.line(x, y - c, x, y + c)
    can.setStrokeColorRGB(0, 0, 0)
    can.line(x - c, y, x + c, y)

    # Second layer with phase offset
    can.setDash(dash, s)
    can.setStrokeColorRGB(0, 0, 0)
    can.line(x, y - c, x, y + c)
    can.setStrokeColorRGB(255, 255, 255)
    can.line(x - c, y, x + c, y)


def pdf_gen(p_dict, size):
    rgx = re.compile(r"\W")
    img_dict = p_dict["cards"]
    has_backside = print_dict["backside_enabled"]
    backside_offset = mm_to_point(float(p_dict["backside_offset"]))
    bleed_edge = float(p_dict["bleed_edge"])
    has_bleed_edge = bleed_edge > 0
    if has_bleed_edge:
        b = mm_to_inch(bleed_edge)
        img_dir = os.path.join(crop_dir, str(bleed_edge).replace(".", "p"))
    else:
        b = 0
        img_dir = crop_dir
    (w, h) = card_size_without_bleed_inch
    w, h = inch_to_point((w + 2 * b)), inch_to_point((h + 2 * b))
    b = inch_to_point(b)
    rotate = bool(p_dict["orient"] == "Landscape")
    size = tuple(size[::-1]) if rotate else size
    pw, ph = size
    pdf_fp = os.path.join(
        cwd,
        (
            f"{re.sub(rgx, '', p_dict['filename'])}.pdf"
            if len(p_dict["filename"]) > 0
            else "_printme.pdf"
        ),
    )
    pages = canvas.Canvas(pdf_fp, pagesize=size)
    cols, rows = int(pw // w), int(ph // h)
    rx, ry = round((pw - (w * cols)) / 2), round((ph - (h * rows)) / 2)
    ry = ph - ry - h
    images_per_page = cols * rows

    images = []
    for img in img_dict.keys():
        images.extend([img] * img_dict[img])
    images = [
        images[i : i + images_per_page] for i in range(0, len(images), images_per_page)
    ]

    for page_images in images:

        def get_ith_image_coords(i):
            _, j = divmod(i, images_per_page)
            y, x = divmod(j, cols)
            return x, y

        def draw_image(img, x, y, dx=0.0, dy=0.0):
            img_path = os.path.join(img_dir, img)
            if os.path.exists(img_path):
                pages.drawImage(
                    img_path,
                    x * w + rx + dx,
                    ry - y * h + dy,
                    w,
                    h,
                )

        # Draw front-sides
        for i, img in enumerate(page_images):
            x, y = get_ith_image_coords(i)
            draw_image(img, x, y)
        
            if stroke: 
                # Draw lines per image
                if has_bleed_edge:
                        draw_cross(pages, (x + 0) * w + b + rx, ry - (y + 0) * h + b)
                        draw_cross(pages, (x + 1) * w - b + rx, ry - (y + 0) * h + b)
                        draw_cross(pages, (x + 1) * w - b + rx, ry - (y - 1) * h - b)
                        draw_cross(pages, (x + 0) * w + b + rx, ry - (y - 1) * h - b)

            
        # Draw lines for whole page
        if stroke:
            if not has_bleed_edge:
                for cy in range(rows + 1):
                    for cx in range(cols + 1):
                        draw_cross(pages, rx + w * cx, ry - h * (cy - 1))

        # Next page
        pages.showPage()

        # Draw back-sides if requested
        if has_backside:
            for i, img in enumerate(page_images):
                backside = (
                    print_dict["backsides"][img]
                    if img in print_dict["backsides"]
                    else print_dict["backside_default"]
                )
                x, y = get_ith_image_coords(i)
                draw_image(backside, x, y, backside_offset, 0)

            # Next page
            pages.showPage()

    saving_window = popup("Saving...")
    saving_window.refresh()
    pages.save()
    saving_window.close()
    try:
        subprocess.Popen([pdf_fp], shell=True)
    except Exception as e:
        print(e)


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


def cropper(folder, img_dict, bleed_edge):
    has_bleed_edge = bleed_edge is not None and bleed_edge > 0
    if has_bleed_edge:
        img_dict = cropper(folder, img_dict, None)

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
            print(
                f"{img_file} - DPI calculated: {dpi}, cropping {c} pixels around frame (adjusted for bleed edge)"
            )
        else:
            print(
                f"{img_file} - DPI calculated: {dpi}, cropping {c} pixels around frame"
            )
        crop_im = im[c : h - c, c : w - c]
        (h, w, _) = crop_im.shape
        max_dpi = cfg.getint("Max.DPI")
        if dpi > max_dpi:
            new_size = (
                int(round(w * cfg.getint("Max.DPI") / dpi)),
                int(round(h * cfg.getint("Max.DPI") / dpi)),
            )
            print(
                f"{img_file} - Exceeds maximum DPI {max_dpi}, resizing to {new_size[0]}x{new_size[1]}"
            )
            crop_im = cv2.resize(crop_im, new_size, interpolation=cv2.INTER_CUBIC)
            crop_im = numpy.array(
                Image.fromarray(crop_im).filter(ImageFilter.UnsharpMask(1, 20, 8))
            )
        if cfg.getboolean("Vibrance.Bump"):
            crop_im = numpy.array(Image.fromarray(crop_im).filter(vibrance_cube))
        write_image(os.path.join(output_dir, img_file), crop_im)

    if i > 0 and not has_bleed_edge:
        return cache_previews(img_cache, output_dir)
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


def cache_previews(file, folder, data={}):
    for f in list_files(folder):
        if f in data.keys():
            continue

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
            sg.Checkbox("STROKE",key="STROKE", default=True,),
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
        resizable=True,
        finalize=True,
        element_justification="center",
        enable_close_attempted_event=True,
        size=print_dict["size"],
    )
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


crop_list = list_files(crop_dir)
img_dict = {}
if os.path.exists(img_cache):
    with open(img_cache, "r") as fp:
        img_dict = json.load(fp)
if len(img_dict.keys()) < len(crop_list):
    img_dict = cache_previews(img_cache, crop_dir, img_dict)
img_dict = cropper(image_dir, img_dict, None)

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
else:
    # Initialize our values
    print_dict = {
        "cards": {},
        # program window settings
        "size": (1480, 920),
        "columns": 5,
        # backside options
        "backside_enabled": False,
        "backside_default": "__back.png",
        "backside_offset": "0",
        "backsides": {},
        # pdf generation options
        "pagesize": "Letter",
        "page_sizes": ["Letter", "A4", "A3", "Legal"],
        "orient": "Portrait",
        "bleed_edge": "0",
        "filename": "_printme",
    }
    for img in list_files(crop_dir):
        print_dict["cards"][img] = 0 if img.startswith("__") else 1

bleed_edge = float(print_dict["bleed_edge"])
if need_run_cropper(image_dir, bleed_edge):
    cropper(image_dir, img_dict, bleed_edge)

window = window_setup(print_dict["columns"])
old_size = window.size
for k in window.key_dict.keys():
    if "CRD:" in str(k):
        window[k].bind("<Button-1>", "-LEFT")
        window[k].bind("<Button-3>", "-RIGHT")
loading_window.close()
hover_backside = False

while True:
    event, values = window.read()
    stroke = values['STROKE']
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
        oldwindow = window
        oldwindow.disable()
        grey_window = grey_out(window)

        bleed_edge = float(print_dict["bleed_edge"])
        img_dict = cropper(image_dir, img_dict, bleed_edge)
        for img in list_files(crop_dir):
            if img not in print_dict["cards"].keys():
                print(f"{img} found and added to list.")
                print_dict["cards"][img] = 1

        window = window_setup(print_dict["columns"])
        window.enable()
        window.bring_to_front()
        oldwindow.close()
        grey_window.close()
        window.refresh()
        for k in window.key_dict.keys():
            if "CRD:" in str(k):
                window[k].bind("<Button-1>", "-LEFT")
                window[k].bind("<Button-3>", "-RIGHT")

    if "RENDER" in event:
        window.disable()
        grey_window = grey_out(window)
        render_window = popup("Rendering...")
        render_window.refresh()
        lookup = {"Letter": letter, "A4": A4, "A3": A3, "Legal": legal}
        pdf_gen(print_dict, lookup[print_dict["pagesize"]])
        render_window.close()
        grey_window.close()
        window.enable()
        window.bring_to_front()
        window.refresh()

    if "SELECT" in event:
        for card_name in print_dict["cards"].keys():
            print_dict["cards"][card_name] = 1
            window[f"NUM:{card_name}"].update("1")

    if "UNSELECT" in event:
        for card_name in print_dict["cards"].keys():
            print_dict["cards"][card_name] = 0
            window[f"NUM:{card_name}"].update("0")

    if event in ["DEFAULT_BACKSIDE"]:
        if path := easygui.fileopenbox(default="images/*"):
            print_dict["backside_default"] = os.path.relpath(
                path, os.path.abspath("images")
            )
            img_draw_graphs(window)

    if event and print_dict["size"] != window.size:
        print_dict["size"] = window.size

with open(print_json, "w") as fp:
    json.dump(print_dict, fp)
window.close()
