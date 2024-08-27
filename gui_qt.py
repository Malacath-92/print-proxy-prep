import os
import re
import sys
import math
import json
import subprocess

import PyQt6.QtCore as QtCore
from PyQt6.QtGui import QPixmap, QIntValidator, QPainter, QPainterPath
from PyQt6.QtWidgets import QApplication, QMainWindow, QWidget, QLabel, QPushButton, QLineEdit, QGridLayout, QVBoxLayout, QHBoxLayout, QScrollArea, QStyle, QCommonStyle, QSizePolicy, QGroupBox, QComboBox, QDialog, QDoubleSpinBox, QFrame, QToolTip

import pdf
import image
import constants
from util import *
from constants import *
import fallback_image as fallback


def init():
    app = QApplication(sys.argv)
    return app


def is_window_maximized(window):
    return window.isMaximized()


def popup(middle_text):
    class PopupWindow(QDialog):
        def __init__(self, text):
            super().__init__()

            text_widget = QLabel(text)
            layout = QVBoxLayout()
            layout.addWidget(text_widget)
            self.setLayout(layout)
            self.setWindowFlags(QtCore.Qt.WindowType.FramelessWindowHint | QtCore.Qt.WindowType.WindowStaysOnTopHint)

            palette = self.palette()
            palette.setColor(self.backgroundRole(), 0x111111)
            self.setPalette(palette)
            self.setAutoFillBackground(True)

            self._text = text_widget

        def show_during_work(self, work):
            class WorkThread(QtCore.QThread):
                def run(self):
                    work()
            work_thread = WorkThread()

            self.open()
            work_thread.finished.connect(lambda: self.close())
            work_thread.start()
            self.exec()

    return PopupWindow(middle_text)


def make_popup_print_fn(popup):
    def popup_print_fn(text):
        print(text)
        popup.adjustSize()
        popup._text.setText(text)
        popup.adjustSize()
    return popup_print_fn


def grey_out(main_window):
    pass


class WidgetWithLabel(QWidget):
    def __init__(self, label_text, widget):
        super().__init__()

        label = QLabel(label_text + ':')
        if '&' in label_text:
            label.setBuddy(widget)
        
        layout = QHBoxLayout()
        layout.addWidget(label)
        layout.addWidget(widget)
        layout.setContentsMargins(0, 0, 0, 0)

        self.setLayout(layout)

        self._widget = widget


class ComboBoxWithLabel(WidgetWithLabel):
    def __init__(self, label_text, options, default_option = None):
        combo = QComboBox()
        for option in options:
            combo.addItem(option)

        if default_option is not None and default_option in options:
            combo.setCurrentIndex(options.index(default_option))

        super().__init__(label_text, combo)


class LineEditWithLabel(WidgetWithLabel):
    def __init__(self, label_text, default_text = None):
        text = QLineEdit(default_text)
        super().__init__(label_text, text)


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
    def __init__(self, img_data, img_size):
        super().__init__()

        raw_pixmap = QPixmap()
        raw_pixmap.loadFromData(img_data, "PNG")

        card_size_minimum_width_pixels = 110
        card_corner_radius_inch = 1 / 8
        card_corner_radius_pixels = card_corner_radius_inch * img_size[0] / card_size_without_bleed_inch[0]

        clipped_pixmap = QPixmap(img_size[0], img_size[1])
        clipped_pixmap.fill(QtCore.Qt.GlobalColor.transparent)

        path = QPainterPath()
        path.addRoundedRect(QtCore.QRectF(raw_pixmap.rect()), card_corner_radius_pixels, card_corner_radius_pixels)
        
        painter = QPainter(clipped_pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

        painter.setClipPath(path)
        painter.drawPixmap(0, 0, raw_pixmap)
        del painter

        self.setPixmap(clipped_pixmap)
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
        left_arrow.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_ArrowDown))

        right_arrow = QPushButton()
        right_arrow.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_ArrowUp))

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
        self.setLayout(grid_layout)
        self.refresh(print_dict, img_dict)

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

    def refresh(self, print_dict, img_dict):
        grid_layout = self.layout()
        for i in reversed(range(grid_layout.count())): 
            grid_layout.removeWidget(grid_layout.itemAt(i).widget())

        i = 0
        cols = print_dict["columns"]
        for card_name, _ in print_dict["cards"].items():
            if card_name.startswith("__") or card_name not in img_dict:
                continue

            x = i // cols
            y = i % cols
            grid_layout.addWidget(CardWidget(print_dict, img_dict, card_name), x, y)
            i = i + 1

        self._first_item = grid_layout.itemAt(0).widget()
        self._cols = cols
        self._rows = math.ceil(i / cols)
        self._nested_resize = False

        self.setMinimumWidth(self.totalWidthFromItemWidth(self._first_item.minimumWidth()))
        self.setMinimumHeight(self._first_item.heightForWidth(self._first_item.minimumWidth()))


class CardScrollArea(QScrollArea):
    def __init__(self, card_grid):
        super().__init__()

        self.setWidgetResizable(True)
        self.setWidget(card_grid)
        
        self.setMinimumWidth(card_grid.minimumWidth() + self.verticalScrollBar().width())
        self.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOn)

        self._card_grid = card_grid

    def refresh(self, print_dict, img_dict):
        self._card_grid.refresh(print_dict, img_dict)
        self._card_grid.adjustSize() # forces recomputing size


class ActionsWidget(QGroupBox):
    def __init__(self, card_scroll_area, image_dir, crop_dir, print_json, print_dict, img_dict, img_cache):
        super().__init__()

        self.setTitle("Actions")

        cropper_button = QPushButton("Run Cropper")
        render_button = QPushButton("Render Document")
        save_button = QPushButton("Save Project")
        load_button = QPushButton("Load Project")

        buttons = [cropper_button, render_button, save_button, load_button]
        minimum_width = max(map(lambda x: x.sizeHint().width(), buttons))
        
        layout = QGridLayout()
        layout.setColumnMinimumWidth(0, minimum_width + 10)
        layout.setColumnMinimumWidth(1, minimum_width + 10)
        layout.addWidget(cropper_button, 0, 0)
        layout.addWidget(render_button, 0, 1)
        layout.addWidget(save_button, 1, 0)

        # TODO: Missing this feature
        # layout.addWidget(load_button, 1, 1)

        self.setLayout(layout)

        def run_cropper():
            bleed_edge = float(print_dict["bleed_edge"])
            if image.need_run_cropper(image_dir, crop_dir, bleed_edge):

                self._rebuild_after_cropper = False

                def cropper_work():
                    image.cropper(image_dir, crop_dir, img_cache, img_dict, bleed_edge, CFG.getint("Max.DPI"), CFG.getboolean("Vibrance.Bump"), make_popup_print_fn(crop_window))

                    for img in list_files(crop_dir):
                        if img not in print_dict["cards"].keys():
                            print(f"{img} found and added to list.")
                            print_dict["cards"][img] = 1
                            self._rebuild_after_cropper = True

                    deleted_images = []
                    for img in print_dict["cards"].keys():
                        if img not in img_dict.keys():
                            print(f"{img} not found and removed from list.")
                            deleted_images.append(img)
                            self._rebuild_after_cropper = True
                    for img in deleted_images:
                        del print_dict["cards"][img]
                
                self.window().setEnabled(False)
                crop_window = popup("Cropping images...")
                crop_window.show_during_work(cropper_work)
                del crop_window
                if self._rebuild_after_cropper:
                    card_scroll_area.refresh(print_dict, img_dict)
                self.window().setEnabled(True)
            else:
                QToolTip.showText(cropper_button.mapToGlobal(QtCore.QPoint()), "All images are already cropped")

        def save_project():
            with open(print_json, "w") as fp:
                json.dump(print_dict, fp)

        cropper_button.released.connect(run_cropper)
        save_button.released.connect(save_project)

        self._cropper_button = cropper_button
        self._rebuild_after_cropper = False
        self._img_dict = img_dict


class PrintOptionsWidget(QGroupBox):
    def __init__(self, print_dict):
        super().__init__()

        self.setTitle("Print Options")

        print_output = LineEditWithLabel("PDF &Filename", print_dict["filename"])
        paper_sizes = ComboBoxWithLabel("Paper &Size", print_dict["page_sizes"], print_dict["pagesize"])
        orientation = ComboBoxWithLabel("&Orientation", ["Landscape", "Portrait"], print_dict["orient"])

        layout = QVBoxLayout()
        layout.addWidget(print_output)
        layout.addWidget(paper_sizes)
        layout.addWidget(orientation)

        self.setLayout(layout)

        def change_output(t):
            print_dict["filename"] = t

        def change_papersize(t):
            print_dict["pagesize"] = t

        def change_orientation(t):
            print_dict["orient"] = t

        print_output._widget.textChanged.connect(change_output)
        paper_sizes._widget.currentTextChanged.connect(change_papersize)
        orientation._widget.currentTextChanged.connect(change_orientation)


class CardOptionsWidget(QGroupBox):
    def __init__(self, print_dict):
        super().__init__()

        self.setTitle("Card Options")

        bleed_edge_spin = QDoubleSpinBox()
        bleed_edge_spin.setDecimals(2)
        bleed_edge_spin.setRange(0, inch_to_mm(0.12))
        bleed_edge_spin.setSingleStep(0.1)
        bleed_edge = WidgetWithLabel("&Bleed Edge", bleed_edge_spin)
        
        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setFrameShadow(QFrame.Shadow.Sunken)

        layout = QVBoxLayout()
        layout.addWidget(bleed_edge)
        layout.addWidget(divider)

        self.setLayout(layout)

        def change_bleed_edge(t):
            print_dict["bleed_edge"] = t

        bleed_edge_spin.textChanged.connect(change_bleed_edge)


class OptionsWidget(QWidget):
    def __init__(self, card_scroll_area, image_dir, crop_dir, print_json, print_dict, img_dict, img_cache):
        super().__init__()

        actions_widget = ActionsWidget(card_scroll_area, image_dir, crop_dir, print_json, print_dict, img_dict, img_cache)
        print_options = PrintOptionsWidget(print_dict)
        card_options = CardOptionsWidget(print_dict)

        layout = QVBoxLayout()
        layout.addWidget(actions_widget)
        layout.addWidget(print_options)
        layout.addWidget(card_options)
        layout.addStretch()

        self.setLayout(layout)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)


def window_setup(image_dir, crop_dir, print_json, print_dict, img_dict, img_cache):
    card_grid = CardGrid(print_dict, img_dict)
    scroll_area = CardScrollArea(card_grid)

    options = OptionsWidget(scroll_area, image_dir, crop_dir, print_json, print_dict, img_dict, img_cache)

    window_layout = QHBoxLayout()
    window_layout.addWidget(scroll_area)
    window_layout.addWidget(options)
    
    window_area = QWidget()
    window_area.setLayout(window_layout)

    window = MainWindow()
    window.setCentralWidget(window_area)
    window.show()
    return window


def event_loop(app, window, image_dir, crop_dir, print_json, print_dict, img_dict, img_cache):
    app.exec()
