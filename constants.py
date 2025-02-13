import os

from pymupdf import paper_sizes

cwd = os.getcwd()

page_sizes = {
    "Letter": paper_sizes()["letter"],
    "A5": paper_sizes()["a5"],
    "A4": paper_sizes()["a4"],
    "A3": paper_sizes()["a3"],
    "Legal": paper_sizes()["legal"],
}

card_size_with_bleed_inch = (2.72, 3.7)
card_size_without_bleed_inch = (2.48, 3.46)
card_ratio = card_size_without_bleed_inch[0] / card_size_without_bleed_inch[1]
