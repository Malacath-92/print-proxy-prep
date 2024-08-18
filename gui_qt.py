import os
import re
import sys
import json
import subprocess

import PyQt6.QtCore as QtCore
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import QApplication, QMainWindow, QWidget, QLabel, QGridLayout, QVBoxLayout, QScrollArea

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


def img_widget_from_bytes(img_data, img_size):
    img_pixmap = QPixmap()
    img_pixmap.loadFromData(img_data, "PNG")

    img_widget = QLabel()
    img_widget.setPixmap(img_pixmap)
    return img_widget


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


class CardGrid(QGridLayout):
    def __init__(self, print_dict, img_dict):
        super().__init__()

        cols = print_dict["columns"]
        for i, (card_name, number) in enumerate(print_dict["cards"].items()):
            img_data = eval(img_dict[card_name]["data"])
            img_size = img_dict[card_name]["size"]
            img = img_widget_from_bytes(img_data, img_size)

            x = i // cols
            y = i % cols
            self.addWidget(img, x, y)


def window_setup(image_dir, crop_dir, print_dict, img_dict):
    window = MainWindow()

    grid = QWidget()
    grid.setLayout(CardGrid(print_dict, img_dict))

    scroll_area = QScrollArea()
    scroll_area.setWidgetResizable(True)
    scroll_area.setWidget(grid)

    window_area = QWidget()
    window_area.setLayout(QVBoxLayout())
    window_area.layout().addWidget(scroll_area);

    window.setCentralWidget(window_area)
    window.show()
    return window


def event_loop(app, window, image_dir, crop_dir, print_json, print_dict, img_dict, img_cache):
    app.exec()
