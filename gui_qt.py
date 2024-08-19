import os
import re
import sys
import json
import subprocess

import PyQt6.QtCore as QtCore
from PyQt6.QtGui import QPixmap, QIntValidator
from PyQt6.QtWidgets import QApplication, QMainWindow, QWidget, QLabel, QPushButton, QLineEdit, QGridLayout, QVBoxLayout, QHBoxLayout, QScrollArea, QStyle, QCommonStyle

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


class CardWidget(QWidget):
    def __init__(self, print_dict, img_dict, card_name):
        super().__init__()

        img_data = eval(img_dict[card_name]["data"])
        img_size = img_dict[card_name]["size"]
        img = self.img_widget_from_bytes(img_data, img_size)

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

        number_area = QWidget()
        number_area.setLayout(number_layout)

        layout = QVBoxLayout()
        layout.addWidget(img)
        layout.setAlignment(img, QtCore.Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(number_area)

        self.setLayout(layout)

        palette = self.palette()
        palette.setColor(self.backgroundRole(), 0x111111)
        self.setPalette(palette)
        self.setAutoFillBackground(True)

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
    
    def img_widget_from_bytes(self, img_data, _):
        img_pixmap = QPixmap()
        img_pixmap.loadFromData(img_data, "PNG")

        img_widget = QLabel()
        img_widget.setPixmap(img_pixmap)
        return img_widget


class CardGrid(QGridLayout):
    def __init__(self, print_dict, img_dict):
        super().__init__()

        cols = print_dict["columns"]
        i = 0
        for card_name, _ in print_dict["cards"].items():
            if card_name.startswith("__"):
                continue

            x = i // cols
            y = i % cols
            self.addWidget(CardWidget(print_dict, img_dict, card_name), x, y)
            i = i + 1


def window_setup(image_dir, crop_dir, print_dict, img_dict):
    window = MainWindow()

    grid = QWidget()
    grid.setLayout(CardGrid(print_dict, img_dict))

    scroll_area = QScrollArea()
    scroll_area.setWidgetResizable(True)
    scroll_area.setWidget(grid)

    window_area = QWidget()
    window_area.setLayout(QVBoxLayout())
    window_area.layout().addWidget(scroll_area)

    window.setCentralWidget(window_area)
    window.show()
    return window


def event_loop(app, window, image_dir, crop_dir, print_json, print_dict, img_dict, img_cache):
    app.exec()
