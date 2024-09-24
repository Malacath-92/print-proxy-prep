import os
import configparser

from reportlab.lib.pagesizes import LETTER, A5, A4, A3, LEGAL

cwd = os.path.dirname(__file__)

page_sizes = {"Letter": LETTER, "A5": A5, "A4": A4, "A3": A3, "Legal": LEGAL}

card_size_with_bleed_inch = (2.72, 3.7)
card_size_without_bleed_inch = (2.48, 3.46)
card_ratio = card_size_without_bleed_inch[0] / card_size_without_bleed_inch[1]


class GlobalConfig:
    def __init__(self):
        self.VibranceBump = False
        self.MaxDPI = 1200
        self.DefaultPageSize = "Letter"
        self.EnableUncrop = True


def load_config() -> GlobalConfig:
    cfg_path = os.path.join(cwd, "config.ini")

    config_parser = configparser.ConfigParser()
    config_parser.read(cfg_path)

    def_cfg = config_parser["DEFAULT"]
    parsed_config = GlobalConfig()
    parsed_config.VibranceBump = def_cfg.getboolean("Vibrance.Bump", False)
    parsed_config.MaxDPI = def_cfg.getint("Max.DPI", 1200)
    parsed_config.DefaultPageSize = def_cfg.get("Page.Size", "Letter")
    parsed_config.EnableUncrop = def_cfg.getboolean("Enable.Uncrop", True)

    return parsed_config


def save_config(cfg):
    cfg_path = os.path.join(cwd, "config.ini")

    config_parser = configparser.ConfigParser()

    def_cfg = config_parser["DEFAULT"]
    def_cfg["Vibrance.Bump"] = str(cfg.VibranceBump)
    def_cfg["Max.DPI"] = str(cfg.MaxDPI)
    def_cfg["Page.Size"] = cfg.DefaultPageSize
    def_cfg["Enable.Uncrop"] = str(cfg.EnableUncrop)

    with open(cfg_path, "w") as configfile:
        config_parser.write(configfile)


CFG = load_config()
