import os
import re
import sys
import math
import json
import subprocess

import PyQt6.QtCore as QtCore
from PyQt6.QtGui import QPixmap, QIntValidator
from PyQt6.QtWidgets import QApplication, QMainWindow, QWidget, QLabel, QPushButton, QLineEdit, QGridLayout, QVBoxLayout, QHBoxLayout, QScrollArea, QStyle, QCommonStyle, QSizePolicy

import pdf
import image
from util import *
from constants import *
import fallback_image as fallback


def init():
    app = QApplication(sys.argv)
    return app


def is_window_maximized(window):
    return window.isMaximized()


def popup(middle_text):
    class window_stub:
        def refresh(self):
            pass
        def close(self):
            pass
    return window_stub()


def make_popup_print_fn(popup): 
    return print


def grey_out(main_window):
    pass


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("PDF Proxy Printer")

        self.loadState()
    
    def close(self):
        self.saveSettings()

    def saveSettings(self):
        settings = QtCore.QSettings("Proxy", self.windowTitle())
        settings.setValue('version', '1.0.0')
        settings.setValue('geometry', self.saveGeometry())
        settings.setValue('state', self.saveState())

    def loadState(self):
        settings = QtCore.QSettings("Proxy", self.windowTitle())
        if settings.contains("version"):
            self.restoreGeometry(settings.value('geometry'))
            self.restoreState(settings.value('state'))


class CardImage(QLabel):
    def __init__(self, img_data, _):
        super().__init__()

        self.img_pixmap = QPixmap()
        self.img_pixmap.loadFromData(img_data, "PNG")

        card_size_minimum_width_pixels = 110

        self.setPixmap(self.img_pixmap)
        self.setSizePolicy(QSizePolicy.Policy.MinimumExpanding, QSizePolicy.Policy.MinimumExpanding)
        self.setScaledContents(True)
        self.setMinimumWidth(card_size_minimum_width_pixels)

    def heightForWidth(self, width):
        return int(width / card_ratio)


class CardWidget(QWidget):
    def __init__(self, print_dict, img_dict, card_name):
        super().__init__()

        img_data = eval(img_dict[card_name]["data"])
        img_size = img_dict[card_name]["size"]
        img = CardImage(img_data, img_size)

        number_edit = QLineEdit()
        number_edit.setValidator(QIntValidator(0, 100, self))
        number_edit.setText(str(print_dict["cards"][card_name]))
        number_edit.setFixedWidth(40)

        style = QCommonStyle()

        left_arrow = QPushButton()
        left_arrow.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_ArrowLeft))

        right_arrow = QPushButton()
        right_arrow.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_ArrowRight))

        number_layout = QHBoxLayout()
        number_layout.addStretch()
        number_layout.addWidget(left_arrow)
        number_layout.addWidget(number_edit)
        number_layout.addWidget(right_arrow)
        number_layout.addStretch()
        number_layout.setContentsMargins(0, 0, 0, 0)

        number_area = QWidget()
        number_area.setLayout(number_layout)
        number_area.setFixedHeight(20)

        layout = QVBoxLayout()
        layout.addWidget(img)
        layout.addWidget(number_area)

        self.setLayout(layout)

        palette = self.palette()
        palette.setColor(self.backgroundRole(), 0x111111)
        self.setPalette(palette)
        self.setAutoFillBackground(True)

        self._img_widget = img
        self._number_area = number_area

        def apply_number(number):
            number_edit.setText(str(number))
            print_dict["cards"][card_name] = number

        def edit_number():
            number = int(number_edit.text())
            number = max(number, 0)
            apply_number(number)

        def dec_number():
            number = print_dict["cards"][card_name] - 1
            number = max(number, 0)
            apply_number(number)

        def inc_number():
            number = print_dict["cards"][card_name] + 1
            number = min(number, 999)
            apply_number(number)

        number_edit.editingFinished.connect(edit_number)
        left_arrow.clicked.connect(dec_number)
        right_arrow.clicked.connect(inc_number)

        margins = self.layout().contentsMargins()
        minimum_img_width = img.minimumWidth()
        minimum_width = minimum_img_width + margins.left() + margins.right()
        self.setMinimumSize(minimum_width, self.heightForWidth(minimum_width))

    def heightForWidth(self, width):
        margins = self.layout().contentsMargins()
        spacing = self.layout().spacing()

        img_width = width - margins.left() - margins.right()
        img_height = self._img_widget.heightForWidth(img_width)

        number_height = self._number_area.height()

        return img_height + number_height + margins.top() + margins.bottom() + spacing
        

class CardGrid(QWidget):
    def __init__(self, print_dict, img_dict):
        super().__init__()

        grid_layout = QGridLayout()

        i = 0
        cols = print_dict["columns"]
        for card_name, _ in print_dict["cards"].items():
            if card_name.startswith("__"):
                continue

            x = i // cols
            y = i % cols
            grid_layout.addWidget(CardWidget(print_dict, img_dict, card_name), x, y)
            i = i + 1

        self._first_item = grid_layout.itemAt(0).widget()
        self._cols = cols
        self._rows = i % cols
        self._nested_resize = False

        self.setLayout(grid_layout)
        self.setMinimumWidth(self.totalWidthFromItemWidth(self._first_item.minimumWidth()))
        self.setMinimumHeight(self._first_item.heightForWidth(self._first_item.minimumWidth()))

    def totalWidthFromItemWidth(self, item_width):
        margins = self.layout().contentsMargins()
        spacing = self.layout().spacing()

        return item_width * self._cols + margins.left() + margins.right() + spacing * (self._cols - 1)

    def heightForWidth(self, width):
        margins = self.layout().contentsMargins()
        spacing = self.layout().spacing()

        item_width = int((width - margins.left() - margins.right() - spacing * (self._cols - 1)) / self._cols)
        item_height = self._first_item.heightForWidth(item_width)
        height = item_height * self._rows + margins.top() + margins.bottom() + spacing * (self._rows - 1)

        return int(height)

    def resizeEvent(self, event):
        width = event.size().width()
        height = self.heightForWidth(width)
        self.setFixedHeight(height)


class CardScrollArea(QScrollArea):
    def __init__(self, card_grid):
        super().__init__()

        self.setWidgetResizable(True)
        self.setWidget(card_grid)
        
        self.setMinimumWidth(card_grid.minimumWidth() + self.verticalScrollBar().width())
        self.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOn)

        self._card_grid = card_grid


def window_setup(image_dir, crop_dir, print_dict, img_dict):
    grid = CardGrid(print_dict, img_dict)
    scroll_area = CardScrollArea(grid)
    window_area = QWidget()
    window_area.setLayout(QVBoxLayout())
    window_area.layout().addWidget(scroll_area)

    window = MainWindow()
    window.setCentralWidget(window_area)
    window.show()
    return window


def event_loop(app, window, image_dir, crop_dir, print_json, print_dict, img_dict, img_cache):
    app.exec()
