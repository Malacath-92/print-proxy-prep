import os
import sys
import subprocess


def list_files(folder, extensions=None):
    files = [f for f in os.listdir(folder) if os.path.isfile(os.path.join(folder, f))]
    if extensions is not None and isinstance(extensions, list):
        files = [f for f in files if os.path.splitext(f)[1] in extensions]
    return files


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


def open_folder(path):
    if os.path.isdir(path):
        if sys.platform == "darwin":
            subprocess.call(["open", "--", path])
        elif sys.platform.startswith("linux"):
            subprocess.call(["xdg-open", "--", path])
        elif sys.platform == "win32":
            subprocess.call(["explorer", path])


def open_file(path):
    subprocess.Popen([path], shell=True)
