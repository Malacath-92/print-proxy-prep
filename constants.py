import os
import typing
import configparser

from reportlab.lib.pagesizes import letter, A4, A3, legal

cwd = os.path.dirname(__file__)

page_sizes = {"Letter": letter, "A4": A4, "A3": A3, "Legal": legal}

card_size_with_bleed_inch = (2.72, 3.7)
card_size_without_bleed_inch = (2.48, 3.46)
card_ratio = card_size_without_bleed_inch[0] / card_size_without_bleed_inch[1]


GlobalConfig = typing.NamedTuple(
    "GlobalConfig",
    [
        ("VibranceBump", bool),
        ("MaxDPI", int),
        ("DefaultPageSize", str),
    ],
)


def load_config(path) -> GlobalConfig:
    config_parser = configparser.ConfigParser()
    config_parser.read(os.path.join(cwd, path))
    cfg = config_parser["DEFAULT"]
    parsed_config = GlobalConfig()
    parsed_config.VibranceBump = cfg.getboolean("Vibrance.Bump", False)
    parsed_config.MaxDPI = cfg.getint("Max.DPI", 1200)
    parsed_config.DefaultPageSize = cfg.get("Page.Size", "Letter")
    return parsed_config

CFG = load_config("config.ini")
