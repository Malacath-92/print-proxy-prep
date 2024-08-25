import os
import configparser

from reportlab.lib.pagesizes import letter, A4, A3, legal

cwd = os.path.dirname(__file__)

page_sizes = {
    "Letter": letter,
    "A4": A4,
    "A3": A3,
    "Legal": legal
}

card_size_with_bleed_inch = (2.72, 3.7)
card_size_without_bleed_inch = (2.48, 3.46)
card_ratio = card_size_without_bleed_inch[0] / card_size_without_bleed_inch[1]

def load_config(path):
    config_parser = configparser.ConfigParser()
    config_parser.read(os.path.join(cwd, path))
    return config_parser["DEFAULT"]

CFG = load_config("config.ini")