import os
import re
import sys
import json
import subprocess

import PyQt6.QtCore as QtCore
from PyQt6.QtWidgets import QApplication, QMainWindow

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
    def __init__(self, print_dict):
        super().__init__()

        self.print_dict = print_dict

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


def window_setup(image_dir, crop_dir, print_dict, img_dict):
    window = MainWindow(print_dict)
    window.show()
    return window


def event_loop(app, window, image_dir, crop_dir, print_json, print_dict, img_dict, img_cache):
    app.exec()
