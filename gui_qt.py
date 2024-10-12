import os
import re
import sys
import math
import json
import functools
import subprocess
from enum import Enum
from copy import deepcopy

import PyQt6.QtCore as QtCore
from PyQt6.QtGui import (
    QPixmap,
    QIntValidator,
    QPainter,
    QPainterPath,
    QCursor,
    QIcon,
    QTransform,
)
from PyQt6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QLabel,
    QPushButton,
    QLineEdit,
    QGridLayout,
    QVBoxLayout,
    QHBoxLayout,
    QStackedLayout,
    QStackedWidget,
    QScrollArea,
    QStyle,
    QCommonStyle,
    QSizePolicy,
    QGroupBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFrame,
    QToolTip,
    QCheckBox,
    QTabWidget,
    QFileDialog,
)

import pdf
import image
import project
from util import *
from config import *
from constants import *
import fallback_image as fallback


class PrintProxyPrepApplication(QApplication):
    def __init__(self, argv):
        super().__init__(argv)

        self._json_path = os.path.join(cwd, "print.json")
        self._settings_loaded = False

        self.load()

    def close(self):
        self.save()

    def set_window(self, window):
        self._window = window
        if self._settings_loaded:
            window.restoreGeometry(self._window_geometry)
            window.restoreState(self._window_state)
            self._window_geometry = None
            self._window_state = None

    def json_path(self):
        return self._json_path

    def set_json_path(self, json_path):
        self._json_path = json_path

    def save(self):
        settings = QtCore.QSettings("Proxy", "PDF Proxy Printer")
        settings.setValue("version", "1.0.0")
        settings.setValue("geometry", self._window.saveGeometry())
        settings.setValue("state", self._window.saveState())
        settings.setValue("json", self._json_path)

    def load(self):
        settings = QtCore.QSettings("Proxy", "PDF Proxy Printer")
        if settings.contains("version"):
            self._window_geometry = settings.value("geometry")
            self._window_state = settings.value("state")
            if settings.contains("json"):
                self._json_path = settings.value("json")

            self._settings_loaded = True


def init():
    return PrintProxyPrepApplication(sys.argv)


def popup(window, middle_text):
    class PopupWindow(QDialog):
        def __init__(self, parent, text):
            super().__init__(parent)

            text_widget = QLabel(text)
            layout = QVBoxLayout()
            layout.addWidget(text_widget)
            self.setLayout(layout)
            self.setWindowFlags(
                QtCore.Qt.WindowType.FramelessWindowHint
                | QtCore.Qt.WindowType.WindowStaysOnTopHint
            )

            palette = self.palette()
            palette.setColor(self.backgroundRole(), 0x111111)
            self.setPalette(palette)
            self.setAutoFillBackground(True)

            self._text = text_widget
            self._thread = None

            self.update_text_impl(text)

        def update_text(self, text, force_this_thread=False):
            if self._thread is None or force_this_thread:
                self.update_text_impl(text)
            else:
                self._thread._refresh.emit(text)

        @QtCore.pyqtSlot(str)
        def update_text_impl(self, text):
            self.adjustSize()
            self._text.setText(text)
            self.adjustSize()

            self.recenter()

        def recenter(self):
            parent = self.parentWidget()
            if parent is not None:
                center = self.rect().center()
                parent_half_size = parent.rect().size() / 2
                offset = (
                    QtCore.QPoint(parent_half_size.width(), parent_half_size.height())
                    - center
                )
                self.move(offset)

        def show_during_work(self, work):
            class WorkThread(QtCore.QThread):
                _refresh = QtCore.pyqtSignal(str)

                def run(self):
                    import debugpy

                    debugpy.debug_this_thread()

                    work()

            work_thread = WorkThread()

            self.open()
            work_thread.finished.connect(lambda: self.close())
            work_thread._refresh.connect(self.update_text_impl)
            work_thread.start()
            self._thread = work_thread
            self.exec()
            self._thread = None

        def showEvent(self, event):
            super().showEvent(event)
            self.recenter()

        def resizeEvent(self, event):
            super().resizeEvent(event)
            self.recenter()
            self.recenter()
            self.recenter()

    return PopupWindow(window, middle_text)


def make_popup_print_fn(popup):
    def popup_print_fn(text):
        print(text)
        popup.update_text(text)

    return popup_print_fn


def folder_dialog(parent=None):
    choice = QFileDialog.getExistingDirectory(
        parent,
        "Choose Folder",
        ".",
        QFileDialog.Option.ShowDirsOnly | QFileDialog.Option.DontResolveSymlinks,
    )
    if choice != "":
        return os.path.basename(choice)
    else:
        return None


class FileDialogType(Enum):
    Open = 0
    Save = 1


def file_dialog(parent, title, root, filter, type):
    function = (
        QFileDialog.getOpenFileName
        if type == FileDialogType.Open
        else QFileDialog.getSaveFileName
    )
    choice = function(
        parent,
        title,
        root,
        filter,
    )[0]
    if choice != "":
        return os.path.basename(choice)
    else:
        return None


def project_file_dialog(parent, type):
    return file_dialog(parent, "Open Project", ".", "Json Files (*.json)", type)


def image_file_dialog(parent, folder):
    return file_dialog(
        parent,
        "Open Image",
        folder,
        f"Image Files ({' '.join(image.valid_image_extensions).replace('.', '*.')})",
        FileDialogType.Open,
    )


class WidgetWithLabel(QWidget):
    def __init__(self, label_text, widget):
        super().__init__()

        label = QLabel(label_text + ":")
        if "&" in label_text:
            label.setBuddy(widget)

        layout = QHBoxLayout()
        layout.addWidget(label)
        layout.addWidget(widget)
        layout.setContentsMargins(0, 0, 0, 0)

        self.setLayout(layout)

        self._widget = widget


class ComboBoxWithLabel(WidgetWithLabel):
    def __init__(self, label_text, options, default_option=None):
        combo = QComboBox()
        for option in options:
            combo.addItem(option)

        if default_option is not None and default_option in options:
            combo.setCurrentIndex(options.index(default_option))

        super().__init__(label_text, combo)


class LineEditWithLabel(WidgetWithLabel):
    def __init__(self, label_text, default_text=None):
        text = QLineEdit(default_text)
        super().__init__(label_text, text)


class MainWindow(QMainWindow):
    def __init__(self, tabs, scroll_area, options, print_preview):
        super().__init__()

        self.setWindowTitle("PDF Proxy Printer")

        icon = QIcon("proxy.png")
        self.setWindowIcon(icon)
        if sys.platform == "win32":
            import ctypes

            myappid = "proxy.printer"  # arbitrary string
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)

        window_layout = QHBoxLayout()
        window_layout.addWidget(tabs)
        window_layout.addWidget(options)

        window_area = QWidget()
        window_area.setLayout(window_layout)

        self.setCentralWidget(window_area)

        self._scroll_area = scroll_area
        self._options = options
        self._print_preview = print_preview

    def refresh_widgets(self, print_dict):
        self._options.refresh_widgets(print_dict)

    def refresh(self, print_dict, img_dict):
        self._scroll_area.refresh(print_dict, img_dict)
        self._options.refresh(print_dict, img_dict)
        self.refresh_preview(print_dict, img_dict)

    def refresh_preview(self, print_dict, img_dict):
        self._print_preview.refresh(print_dict, img_dict)


class CardImage(QLabel):
    def __init__(
        self, img_data, img_size, round_corners=True, rotate=False, flipped=False
    ):
        super().__init__()

        raw_pixmap = QPixmap()
        raw_pixmap.loadFromData(img_data, "PNG")
        pixmap = raw_pixmap

        card_size_minimum_width_pixels = 130

        if round_corners:
            card_corner_radius_inch = 1 / 8
            card_corner_radius_pixels = (
                card_corner_radius_inch * img_size[0] / card_size_without_bleed_inch[0]
            )

            clipped_pixmap = QPixmap(int(img_size[0]), int(img_size[1]))
            clipped_pixmap.fill(QtCore.Qt.GlobalColor.transparent)

            path = QPainterPath()
            path.addRoundedRect(
                QtCore.QRectF(pixmap.rect()),
                card_corner_radius_pixels,
                card_corner_radius_pixels,
            )

            painter = QPainter(clipped_pixmap)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

            painter.setClipPath(path)
            painter.drawPixmap(0, 0, pixmap)
            del painter

            pixmap = clipped_pixmap

        if rotate:
            transform = QTransform()
            transform.rotate(-90 if flipped else 90)
            pixmap = pixmap.transformed(transform)
        elif flipped:
            transform = QTransform()
            transform.rotate(180)
            pixmap = pixmap.transformed(transform)

        self.setPixmap(pixmap)

        self.setSizePolicy(
            QSizePolicy.Policy.MinimumExpanding, QSizePolicy.Policy.MinimumExpanding
        )
        self.setScaledContents(True)
        self.setMinimumWidth(card_size_minimum_width_pixels)

        self._rotated = rotate

    def heightForWidth(self, width):
        if self._rotated:
            return int(width * card_ratio)
        else:
            return int(width / card_ratio)


class BacksideImage(CardImage):
    def __init__(self, backside_name, img_dict):
        if backside_name in img_dict:
            backside_data = eval(img_dict[backside_name]["data"])
            backside_size = img_dict[backside_name]["size"]
        else:
            backside_data = fallback.data
            backside_size = fallback.size

        super().__init__(backside_data, backside_size)


class StackedCardBacksideView(QStackedWidget):
    _backside_reset = QtCore.pyqtSignal()
    _backside_clicked = QtCore.pyqtSignal()

    def __init__(self, img: QWidget, backside: QWidget):
        super().__init__()

        style = QCommonStyle()

        reset_button = QPushButton()
        reset_button.setIcon(
            style.standardIcon(QStyle.StandardPixmap.SP_DialogResetButton)
        )
        reset_button.setToolTip("Reset Backside to Default")
        reset_button.setFixedWidth(20)
        reset_button.setFixedHeight(20)
        reset_button.clicked.connect(self._backside_reset)

        backside.setToolTip("Choose individual Backside")

        backside_layout = QHBoxLayout()
        backside_layout.addStretch()
        backside_layout.addWidget(
            reset_button, alignment=QtCore.Qt.AlignmentFlag.AlignBottom
        )
        backside_layout.addWidget(
            backside, alignment=QtCore.Qt.AlignmentFlag.AlignBottom
        )
        backside_layout.setContentsMargins(0, 0, 0, 0)

        backside_container = QWidget(self)
        backside_container.setLayout(backside_layout)

        img.setMouseTracking(True)
        backside.setMouseTracking(True)
        backside_container.setMouseTracking(True)
        self.setMouseTracking(True)

        self.addWidget(img)
        self.addWidget(backside_container)
        self.layout().setStackingMode(QStackedLayout.StackingMode.StackAll)
        self.layout().setAlignment(
            backside,
            QtCore.Qt.AlignmentFlag.AlignBottom | QtCore.Qt.AlignmentFlag.AlignRight,
        )

        self._img = img
        self._backside = backside
        self._backside_container = backside_container

    def refresh_backside(self, new_backside):
        new_backside.setMouseTracking(True)

        layout = self._backside_container.layout()
        self._backside.setParent(None)
        layout.addWidget(new_backside)
        layout.addWidget(new_backside, alignment=QtCore.Qt.AlignmentFlag.AlignBottom)
        self._backside = new_backside

        self.refresh_sizes(self.rect().size())

    def refresh_sizes(self, size):
        width = size.width()
        height = size.height()

        img_width = int(width * 0.9)
        img_height = int(height * 0.9)

        backside_width = int(width * 0.45)
        backside_height = int(height * 0.45)

        self._img.setFixedWidth(img_width)
        self._img.setFixedHeight(img_height)
        self._backside.setFixedWidth(backside_width)
        self._backside.setFixedHeight(backside_height)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.refresh_sizes(event.size())

    def mouseMoveEvent(self, event):
        super().mouseMoveEvent(event)

        x = event.pos().x()
        y = event.pos().y()

        neg_backside_width = self.rect().width() - self._backside.rect().size().width()
        neg_backside_height = (
            self.rect().height() - self._backside.rect().size().height()
        )

        if x >= neg_backside_width and y >= neg_backside_height:
            self.setCurrentWidget(self._backside_container)
        else:
            self.setCurrentWidget(self._img)

    def leaveEvent(self, event):
        super().leaveEvent(event)

        self.setCurrentWidget(self._img)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)

        if self.currentWidget() == self._backside_container:
            self._backside_clicked.emit()


class CardWidget(QWidget):
    def __init__(self, print_dict, img_dict, card_name):
        super().__init__()

        if card_name in img_dict:
            img_data = eval(img_dict[card_name]["data"])
            img_size = img_dict[card_name]["size"]
        else:
            img_data = fallback.data
            img_size = fallback.size
        img = CardImage(img_data, img_size)

        backside_img = None
        if print_dict["backside_enabled"]:
            backside_name = (
                print_dict["backsides"][card_name]
                if card_name in print_dict["backsides"]
                else print_dict["backside_default"]
            )
            backside_img = BacksideImage(backside_name, img_dict)

        initial_number = print_dict["cards"][card_name] if card_name is not None else 1

        number_edit = QLineEdit()
        number_edit.setValidator(QIntValidator(0, 100, self))
        number_edit.setText(str(initial_number))
        number_edit.setFixedWidth(40)

        decrement_button = QPushButton("➖")
        increment_button = QPushButton("➕")

        decrement_button.setToolTip("Remove one")
        increment_button.setToolTip("Add one")

        number_layout = QHBoxLayout()
        number_layout.addStretch()
        number_layout.addWidget(decrement_button)
        number_layout.addWidget(number_edit)
        number_layout.addWidget(increment_button)
        number_layout.addStretch()
        number_layout.setContentsMargins(0, 0, 0, 0)

        number_area = QWidget()
        number_area.setLayout(number_layout)
        number_area.setFixedHeight(20)

        if backside_img is not None:
            card_widget = StackedCardBacksideView(img, backside_img)

            def backside_reset():
                if card_name in print_dict["backsides"]:
                    del print_dict["backsides"][card_name]
                    new_backside_img = BacksideImage(
                        print_dict["backside_default"], img_dict
                    )
                    card_widget.refresh_backside(new_backside_img)

            def backside_choose():
                backside_choice = image_file_dialog(self, print_dict["image_dir"])
                if backside_choice is not None and (
                    card_name not in print_dict["backsides"]
                    or backside_choice != print_dict["backsides"][card_name]
                ):
                    print_dict["backsides"][card_name] = backside_choice
                    new_backside_img = BacksideImage(backside_choice, img_dict)
                    card_widget.refresh_backside(new_backside_img)

            card_widget._backside_reset.connect(backside_reset)
            card_widget._backside_clicked.connect(backside_choose)
        else:
            card_widget = img

        layout = QVBoxLayout()
        layout.addWidget(card_widget)
        layout.addWidget(number_area)

        if print_dict["oversized_enabled"]:
            is_oversized = (
                print_dict["oversized"][card_name]
                if card_name in print_dict["oversized"]
                else False
            )
            oversized_button = QCheckBox("Oversized")
            oversized_button.setChecked(is_oversized)
            oversized_button.setToolTip("Oversized")
            oversized_button.setFixedHeight(20)
            oversized_button.checkStateChanged.connect(
                functools.partial(self.toggle_oversized, print_dict)
            )
            self._oversized_button = oversized_button
            layout.addWidget(oversized_button)
        else:
            self._oversized_button = None

        self.setLayout(layout)

        palette = self.palette()
        palette.setColor(self.backgroundRole(), 0x111111)
        self.setPalette(palette)
        self.setAutoFillBackground(True)

        self._img_widget = img
        self._number_area = number_area

        number_edit.editingFinished.connect(
            functools.partial(self.edit_number, print_dict)
        )
        decrement_button.clicked.connect(functools.partial(self.dec_number, print_dict))
        increment_button.clicked.connect(functools.partial(self.inc_number, print_dict))

        margins = self.layout().contentsMargins()
        minimum_img_width = img.minimumWidth()
        minimum_width = minimum_img_width + margins.left() + margins.right()
        self.setMinimumSize(minimum_width, self.heightForWidth(minimum_width))

        self._number_edit = number_edit
        self._card_name = card_name

    def heightForWidth(self, width):
        margins = self.layout().contentsMargins()
        spacing = self.layout().spacing()

        img_width = width - margins.left() - margins.right()
        img_height = self._img_widget.heightForWidth(img_width)

        additional_widgets = self._number_area.height() + spacing

        if self._oversized_button:
            additional_widgets += self._oversized_button.height() + spacing

        return img_height + additional_widgets + margins.top() + margins.bottom()

    def apply_number(self, print_dict, number):
        self._number_edit.setText(str(number))
        print_dict["cards"][self._card_name] = number

    def edit_number(self, print_dict):
        number = int(self._number_edit.text())
        number = max(number, 0)
        self.apply_number(print_dict, number)

    def dec_number(self, print_dict):
        number = print_dict["cards"][self._card_name] - 1
        number = max(number, 0)
        self.apply_number(print_dict, number)

    def inc_number(self, print_dict):
        number = print_dict["cards"][self._card_name] + 1
        number = min(number, 999)
        self.apply_number(print_dict, number)

    def toggle_oversized(self, print_dict, s):
        print_dict["oversized"][self._card_name] = s == QtCore.Qt.CheckState.Checked


class DummyCardWidget(CardWidget):
    def __init__(self, print_dict, img_dict):
        super().__init__(print_dict, img_dict, None)
        self._card_name = "__dummy"

    def apply_number(self, print_dict, number):
        pass

    def edit_number(self, print_dict):
        pass

    def dec_number(self, print_dict):
        pass

    def inc_number(self, print_dict):
        pass

    def toggle_oversized(self, print_dict, s):
        pass


class CardGrid(QWidget):
    def __init__(self, print_dict, img_dict):
        super().__init__()

        self._cards = {}

        grid_layout = QGridLayout()
        grid_layout.setContentsMargins(9, 9, 9, 9)
        self.setLayout(grid_layout)
        self.refresh(print_dict, img_dict)

    def totalWidthFromItemWidth(self, item_width):
        margins = self.layout().contentsMargins()
        spacing = self.layout().spacing()

        return (
            item_width * self._cols
            + margins.left()
            + margins.right()
            + spacing * (self._cols - 1)
        )

    def heightForWidth(self, width):
        margins = self.layout().contentsMargins()
        spacing = self.layout().spacing()

        item_width = int(
            (width - margins.left() - margins.right() - spacing * (self._cols - 1))
            / self._cols
        )
        item_height = self._first_item.heightForWidth(item_width)
        height = (
            item_height * self._rows
            + margins.top()
            + margins.bottom()
            + spacing * (self._rows - 1)
        )

        return int(height)

    def resizeEvent(self, event):
        width = event.size().width()
        height = self.heightForWidth(width)
        self.setFixedHeight(height)

    def refresh(self, print_dict, img_dict):
        for card in self._cards.values():
            card.setParent(None)
        self._cards = {}

        grid_layout = self.layout()

        i = 0
        cols = CFG.DisplayColumns
        for card_name, _ in print_dict["cards"].items():
            if card_name.startswith("__") or card_name not in img_dict:
                continue

            card_widget = CardWidget(print_dict, img_dict, card_name)
            self._cards[card_name] = card_widget

            x = i // cols
            y = i % cols
            grid_layout.addWidget(card_widget, x, y)
            i = i + 1

        for j in range(i, cols):
            card_widget = DummyCardWidget(print_dict, img_dict)
            sp_retain = card_widget.sizePolicy()
            sp_retain.setRetainSizeWhenHidden(True)
            card_widget.setSizePolicy(sp_retain)
            card_widget.hide()

            self._cards[card_widget._card_name] = card_widget
            grid_layout.addWidget(card_widget, 0, j)
            i = i + 1

        self._first_item = list(self._cards.values())[0]
        self._cols = cols
        self._rows = math.ceil(i / cols)
        self._nested_resize = False

        self.setMinimumWidth(
            self.totalWidthFromItemWidth(self._first_item.minimumWidth())
        )
        self.setMinimumHeight(
            self._first_item.heightForWidth(self._first_item.minimumWidth())
        )


class CardScrollArea(QScrollArea):
    def __init__(self, print_dict, card_grid):
        super().__init__()

        global_label = QLabel("Global Controls:")
        global_decrement_button = QPushButton("➖")
        global_increment_button = QPushButton("➕")
        global_set_zero_button = QPushButton("Reset All")

        global_decrement_button.setToolTip("Remove one from all")
        global_increment_button.setToolTip("Add one to all")
        global_set_zero_button.setToolTip("Set all to zero")

        global_number_layout = QHBoxLayout()
        global_number_layout.addWidget(global_label)
        global_number_layout.addWidget(global_decrement_button)
        global_number_layout.addWidget(global_increment_button)
        global_number_layout.addWidget(global_set_zero_button)
        global_number_layout.addStretch()
        global_number_layout.setContentsMargins(6, 0, 6, 0)

        global_number_widget = QWidget()
        global_number_widget.setLayout(global_number_layout)

        card_area_layout = QVBoxLayout()
        card_area_layout.addWidget(global_number_widget)
        card_area_layout.addWidget(card_grid)
        card_area_layout.addStretch()
        card_area_layout.setSpacing(0)

        card_area = QWidget()
        card_area.setLayout(card_area_layout)

        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setWidget(card_area)

        self.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOn)

        def dec_number():
            for card in card_grid._cards.values():
                card.dec_number(print_dict)

        def inc_number():
            for card in card_grid._cards.values():
                card.inc_number(print_dict)

        def reset_number():
            for card in card_grid._cards.values():
                card.apply_number(print_dict, 0)

        global_decrement_button.clicked.connect(dec_number)
        global_increment_button.clicked.connect(inc_number)
        global_set_zero_button.clicked.connect(reset_number)

        self._card_grid = card_grid

    def computeMinimumWidth(self):
        margins = self.widget().layout().contentsMargins()
        return (
            self._card_grid.minimumWidth()
            + 2 * self.verticalScrollBar().width()
            + margins.left()
            + margins.right()
        )

    def showEvent(self, event):
        super().showEvent(event)
        self.setMinimumWidth(self.computeMinimumWidth())

    def refresh(self, print_dict, img_dict):
        self._card_grid.refresh(print_dict, img_dict)
        self.setMinimumWidth(self.computeMinimumWidth())
        self._card_grid.adjustSize()  # forces recomputing size


class PageGrid(QWidget):
    def __init__(self, cards, left_to_right, columns, rows, bleed_edge_mm, img_get):
        super().__init__()

        grid = QGridLayout()
        grid.setSpacing(0)
        grid.setContentsMargins(0, 0, 0, 0)

        card_grid = pdf.distribute_cards_to_grid(cards, left_to_right, columns, rows)

        has_missing_preview = False

        for x in range(0, rows):
            for y in range(0, columns):
                if card := card_grid[x][y]:
                    (card_name, is_oversized) = card
                    if card_name is None:
                        continue

                    img_data, img_size = img_get(card_name, bleed_edge_mm)
                    if img_data is None:
                        img_data, img_size = fallback.data, fallback.size
                        has_missing_preview = True

                    img = CardImage(
                        img_data,
                        img_size,
                        round_corners=False,
                        rotate=is_oversized,
                        flipped=False,
                    )

                    if is_oversized:
                        grid.addWidget(img, x, y, 1, 2)
                    else:
                        grid.addWidget(img, x, y)

        # pad with dummy images if we have only one uncompleted row
        for i in range(0, columns):
            x, y = pdf.get_grid_coords(i, columns, left_to_right)
            if grid.itemAtPosition(x, y) is None:
                img_data = fallback.data
                img_size = fallback.size

                img = CardImage(img_data, img_size)
                sp_retain = img.sizePolicy()
                sp_retain.setRetainSizeWhenHidden(True)
                img.setSizePolicy(sp_retain)
                img.hide()

                grid.addWidget(img, x, y)

        for i in range(0, grid.columnCount()):
            grid.setColumnStretch(i, 1)

        self.setLayout(grid)

        self._rows = grid.rowCount()
        self._cols = grid.columnCount()
        self._has_missing_preview = has_missing_preview

    def hasMissingPreviews(self):
        return self._has_missing_preview

    def heightForWidth(self, width):
        return int(width / card_ratio * (self._rows / self._cols))

    def resizeEvent(self, event):
        super().resizeEvent(event)

        width = event.size().width()
        height = self.heightForWidth(width)
        self.setFixedHeight(height)


class PagePreview(QWidget):
    def __init__(
        self, cards, left_to_right, columns, rows, bleed_edge_mm, page_size, img_get
    ):
        super().__init__()

        grid = PageGrid(cards, left_to_right, columns, rows, bleed_edge_mm, img_get)

        layout = QVBoxLayout()
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(grid)
        layout.setAlignment(grid, QtCore.Qt.AlignmentFlag.AlignTop)

        self.setLayout(layout)

        palette = self.palette()
        palette.setColor(self.backgroundRole(), 0xFFFFFF)
        self.setPalette(palette)
        self.setAutoFillBackground(True)

        (page_width, page_height) = page_size
        self._page_ratio = page_width / page_height
        self._page_width = page_width
        self._page_height = page_height

        bleed_edge = mm_to_inch(bleed_edge_mm)
        (card_width, card_height) = (
            v + 2 * bleed_edge for v in card_size_without_bleed_inch
        )
        self._card_width = card_width
        self._card_height = card_height

        self._padding_width = (page_width - columns * card_width) / 2
        self._padding_height = (page_height - rows * card_height) / 2

        self._grid = grid

    def hasMissingPreviews(self):
        return self._grid.hasMissingPreviews()

    def heightForWidth(self, width):
        return int(width / self._page_ratio)

    def resizeEvent(self, event):
        super().resizeEvent(event)

        width = event.size().width()
        height = self.heightForWidth(width)
        self.setFixedHeight(height)

        padding_width_pixels = int(self._padding_width * width / self._page_width)
        padding_height_pixels = int(self._padding_height * height / self._page_height)
        self.setContentsMargins(
            padding_width_pixels,
            padding_height_pixels,
            padding_width_pixels,
            padding_height_pixels,
        )


class PrintPreview(QScrollArea):
    def __init__(self, print_dict, img_dict):
        super().__init__()

        self.refresh(print_dict, img_dict)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)

    def refresh(self, print_dict, img_dict):
        bleed_edge = float(print_dict["bleed_edge"])
        bleed_edge_inch = mm_to_inch(bleed_edge)

        page_size = page_sizes[print_dict["pagesize"]]
        if print_dict["orient"] == "Landscape":
            page_size = tuple(page_size[::-1])
        page_size = tuple(point_to_inch(p) for p in page_size)
        (page_width, page_height) = page_size

        (card_width, card_height) = card_size_without_bleed_inch
        card_width = card_width + 2 * bleed_edge_inch
        card_height = card_height + 2 * bleed_edge_inch

        columns = int(page_width // card_width)
        rows = int(page_height // card_height)

        pages = pdf.distribute_cards_to_pages(print_dict, columns, rows)

        pages = [
            {
                "cards": page,
                "left_to_right": True,
            }
            for page in pages
        ]

        if print_dict["backside_enabled"]:
            back_dict = print_dict["backsides"]

            def backside_of_img(img):
                return (
                    back_dict[img]
                    if img in back_dict
                    else print_dict["backside_default"]
                )

            backside_pages = deepcopy(pages)
            for page in backside_pages:
                page["cards"]["regular"] = [
                    backside_of_img(img) for img in page["cards"]["regular"]
                ]
                page["cards"]["oversized"] = [
                    backside_of_img(img) for img in page["cards"]["oversized"]
                ]
                page["left_to_right"] = False

            pages = [imgs for pair in zip(pages, backside_pages) for imgs in pair]

        @functools.cache
        def img_get(card_name, bleed_edge):
            if card_name in img_dict:
                card_img = img_dict[card_name]
                if bleed_edge > 0 and "uncropped" in card_img:
                    uncropped_data = eval(card_img["uncropped"]["data"])
                    img = image.image_from_bytes(uncropped_data)
                    img_crop = image.crop_image(img, "", bleed_edge, None)
                    img_data, img_size = image.to_bytes(img_crop)
                else:
                    img_data = eval(card_img["data"])
                    img_size = card_img["size"]
                return img_data, img_size
            else:
                return None, None

        img_get.cache_clear()

        pages = [
            PagePreview(
                page["cards"],
                page["left_to_right"],
                columns,
                rows,
                bleed_edge,
                page_size,
                img_get,
            )
            for page in pages
        ]

        has_missing_previews = any([p.hasMissingPreviews() for p in pages])
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.addWidget(
            QLabel("Only a preview; Quality is lower than final render")
        )
        if has_missing_previews:
            bleed_info = QLabel(
                "Bleed edge is incorrect; Run cropper for more accurate preview"
            )
            bleed_info.setStyleSheet("QLabel { color : red; }")
            header_layout.addWidget(bleed_info)
        if CFG.VibranceBump:
            vibrance_info = QLabel("Preview does not respect 'Vibrance Bump' setting")
            vibrance_info.setStyleSheet("QLabel { color : red; }")
            header_layout.addWidget(vibrance_info)

        header = QWidget()
        header.setLayout(header_layout)

        layout = QVBoxLayout()
        layout.addWidget(header)
        for page in pages:
            layout.addWidget(page)
        layout.setSpacing(15)
        layout.setContentsMargins(60, 20, 60, 20)
        pages_widget = QWidget()
        pages_widget.setLayout(layout)

        self.setWidget(pages_widget)


class ActionsWidget(QGroupBox):
    def __init__(
        self,
        application,
        print_dict,
        img_dict,
    ):
        super().__init__()

        self.setTitle("Actions")

        cropper_button = QPushButton("Run Cropper")
        render_button = QPushButton("Render Document")
        save_button = QPushButton("Save Project")
        load_button = QPushButton("Load Project")
        set_images_button = QPushButton("Set Image Folder")
        open_images_button = QPushButton("Open Images")

        buttons = [
            cropper_button,
            render_button,
            save_button,
            load_button,
            set_images_button,
            open_images_button,
        ]
        minimum_width = max(map(lambda x: x.sizeHint().width(), buttons))

        layout = QGridLayout()
        layout.setColumnMinimumWidth(0, minimum_width + 10)
        layout.setColumnMinimumWidth(1, minimum_width + 10)
        layout.addWidget(cropper_button, 0, 0)
        layout.addWidget(render_button, 0, 1)
        layout.addWidget(save_button, 1, 0)
        layout.addWidget(load_button, 1, 1)
        layout.addWidget(set_images_button, 2, 0)
        layout.addWidget(open_images_button, 2, 1)

        self.setLayout(layout)

        def render():
            bleed_edge = float(print_dict["bleed_edge"])
            image_dir = print_dict["image_dir"]
            crop_dir = os.path.join(image_dir, "crop")
            if image.need_run_cropper(
                image_dir, crop_dir, bleed_edge, CFG.VibranceBump
            ):
                QToolTip.showText(
                    QCursor.pos(),
                    "Cropper needs to be run first",
                )
                return

            def render_work():
                rgx = re.compile(r"\W")
                pdf_path = os.path.join(
                    cwd,
                    (
                        f"{re.sub(rgx, '', print_dict['filename'])}.pdf"
                        if len(print_dict["filename"]) > 0
                        else "_printme.pdf"
                    ),
                )
                pages = pdf.generate(
                    print_dict,
                    crop_dir,
                    page_sizes[print_dict["pagesize"]],
                    pdf_path,
                    make_popup_print_fn(render_window),
                )
                make_popup_print_fn(render_window)("Saving PDF...")
                pages.save()
                try:
                    subprocess.Popen([pdf_path], shell=True)
                except Exception as e:
                    print(e)

            self.window().setEnabled(False)
            render_window = popup(self.window(), "Rendering PDF...")
            render_window.show_during_work(render_work)
            del render_window
            self.window().setEnabled(True)

        def run_cropper():
            bleed_edge = float(print_dict["bleed_edge"])
            image_dir = print_dict["image_dir"]
            crop_dir = os.path.join(image_dir, "crop")
            img_cache = print_dict["img_cache"]
            if image.need_run_cropper(
                image_dir, crop_dir, bleed_edge, CFG.VibranceBump
            ):

                self._rebuild_after_cropper = False

                def cropper_work():
                    image.cropper(
                        image_dir,
                        crop_dir,
                        img_cache,
                        img_dict,
                        bleed_edge,
                        CFG.MaxDPI,
                        CFG.VibranceBump,
                        CFG.EnableUncrop,
                        make_popup_print_fn(crop_window),
                    )

                    for img in image.list_image_files(crop_dir):
                        if img not in print_dict["cards"].keys():
                            print_dict["cards"][img] = 1
                            self._rebuild_after_cropper = True

                    deleted_images = []
                    for img in print_dict["cards"].keys():
                        if img not in img_dict.keys():
                            deleted_images.append(img)
                            self._rebuild_after_cropper = True
                    for img in deleted_images:
                        del print_dict["cards"][img]

                self.window().setEnabled(False)
                crop_window = popup(self.window(), "Cropping images...")
                crop_window.show_during_work(cropper_work)
                del crop_window
                if self._rebuild_after_cropper:
                    self.window().refresh(print_dict, img_dict)
                else:
                    self.window().refresh_preview(print_dict, img_dict)
                self.window().setEnabled(True)
            else:
                QToolTip.showText(
                    QCursor.pos(),
                    "All images are already cropped",
                )

        def save_project():
            new_project_json = project_file_dialog(self, FileDialogType.Save)
            if new_project_json is not None:
                application.set_json_path(new_project_json)
                with open(new_project_json, "w") as fp:
                    json.dump(print_dict, fp)

        def load_project():
            new_project_json = project_file_dialog(self, FileDialogType.Open)
            if new_project_json is not None and os.path.exists(new_project_json):
                application.set_json_path(new_project_json)

                def load_project():
                    project.load(
                        print_dict,
                        img_dict,
                        new_project_json,
                        make_popup_print_fn(reload_window),
                    )

                self.window().setEnabled(False)
                reload_window = popup(self.window(), "Reloading project...")
                reload_window.show_during_work(load_project)
                del reload_window
                self.window().refresh_widgets(print_dict)
                self.window().refresh(print_dict, img_dict)
                self.window().setEnabled(True)

        def set_images_folder():
            new_image_dir = folder_dialog(self)
            if new_image_dir is not None:
                print_dict["image_dir"] = new_image_dir
                if new_image_dir == "images":
                    print_dict["img_cache"] = "img.cache"
                else:
                    print_dict["img_cache"] = f"{new_image_dir}.cache"

                project.init_dict(print_dict, img_dict)

                bleed_edge = float(print_dict["bleed_edge"])
                image_dir = new_image_dir
                crop_dir = os.path.join(image_dir, "crop")
                if image.need_run_cropper(
                    image_dir, crop_dir, bleed_edge, CFG.VibranceBump
                ) or image.need_cache_previews(crop_dir, img_dict):

                    def reload_work():
                        project.init_images(
                            print_dict, img_dict, make_popup_print_fn(reload_window)
                        )

                    self.window().setEnabled(False)
                    reload_window = popup(self.window(), "Reloading project...")
                    reload_window.show_during_work(reload_work)
                    del reload_window
                    self.window().refresh(print_dict, img_dict)
                    self.window().setEnabled(True)
                else:
                    self.window().refresh(print_dict, img_dict)

        def open_images_folder():
            open_folder(print_dict["image_dir"])

        render_button.clicked.connect(render)
        cropper_button.clicked.connect(run_cropper)
        save_button.clicked.connect(save_project)
        load_button.clicked.connect(load_project)
        set_images_button.clicked.connect(set_images_folder)
        open_images_button.clicked.connect(open_images_folder)

        self._cropper_button = cropper_button
        self._rebuild_after_cropper = False
        self._img_dict = img_dict


class PrintOptionsWidget(QGroupBox):
    def __init__(self, print_dict, img_dict):
        super().__init__()

        self.setTitle("Print Options")

        print_output = LineEditWithLabel("PDF &Filename", print_dict["filename"])
        paper_size = ComboBoxWithLabel(
            "&Paper Size", list(page_sizes.keys()), print_dict["pagesize"]
        )
        orientation = ComboBoxWithLabel(
            "&Orientation", ["Landscape", "Portrait"], print_dict["orient"]
        )
        guides_checkbox = QCheckBox("Extended Guides")
        guides_checkbox.setChecked(print_dict["extended_guides"])

        layout = QVBoxLayout()
        layout.addWidget(print_output)
        layout.addWidget(paper_size)
        layout.addWidget(orientation)
        layout.addWidget(guides_checkbox)

        self.setLayout(layout)

        def change_output(t):
            print_dict["filename"] = t

        def change_papersize(t):
            print_dict["pagesize"] = t
            self.window().refresh_preview(print_dict, img_dict)

        def change_orientation(t):
            print_dict["orient"] = t
            self.window().refresh_preview(print_dict, img_dict)

        def change_guides(s):
            enabled = s == QtCore.Qt.CheckState.Checked
            print_dict["extended_guides"] = enabled

        print_output._widget.textChanged.connect(change_output)
        paper_size._widget.currentTextChanged.connect(change_papersize)
        orientation._widget.currentTextChanged.connect(change_orientation)
        guides_checkbox.checkStateChanged.connect(change_guides)

        self._print_output = print_output._widget
        self._paper_size = paper_size._widget
        self._orientation = orientation._widget
        self._guides_checkbox = guides_checkbox

    def refresh_widgets(self, print_dict):
        self._print_output.setText(print_dict["filename"])
        self._paper_size.setCurrentText(print_dict["pagesize"])
        self._orientation.setCurrentText(print_dict["orient"])
        self._guides_checkbox.setChecked(print_dict["extended_guides"])


class BacksidePreview(QWidget):
    def __init__(self, backside_name, img_dict):
        super().__init__()

        self.setLayout(QVBoxLayout())
        self.refresh(backside_name, img_dict)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    def refresh(self, backside_name, img_dict):
        backside_default_image = BacksideImage(backside_name, img_dict)

        backside_width = 120
        backside_height = backside_default_image.heightForWidth(backside_width)
        backside_default_image.setFixedWidth(backside_width)
        backside_default_image.setFixedHeight(backside_height)

        backside_default_label = QLabel(backside_name)

        layout = self.layout()
        for i in reversed(range(layout.count())):
            layout.itemAt(i).widget().setParent(None)

        layout.addWidget(backside_default_image)
        layout.addWidget(backside_default_label)
        layout.setAlignment(
            backside_default_image, QtCore.Qt.AlignmentFlag.AlignHCenter
        )
        layout.setAlignment(
            backside_default_label, QtCore.Qt.AlignmentFlag.AlignHCenter
        )
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)

        self.setLayout(layout)


class CardOptionsWidget(QGroupBox):
    def __init__(self, print_dict, img_dict):
        super().__init__()

        self.setTitle("Card Options")

        bleed_edge_spin = QDoubleSpinBox()
        bleed_edge_spin.setDecimals(2)
        bleed_edge_spin.setRange(0, inch_to_mm(0.12))
        bleed_edge_spin.setSingleStep(0.1)
        bleed_edge_spin.setSuffix("mm")
        bleed_edge_spin.setValue(float(print_dict["bleed_edge"]))
        bleed_edge = WidgetWithLabel("&Bleed Edge", bleed_edge_spin)

        bleed_back_divider = QFrame()
        bleed_back_divider.setFrameShape(QFrame.Shape.HLine)
        bleed_back_divider.setFrameShadow(QFrame.Shadow.Sunken)

        backside_enabled = print_dict["backside_enabled"]
        backside_checkbox = QCheckBox("Enable Backside")
        backside_checkbox.setChecked(backside_enabled)

        backside_default_button = QPushButton("Default")
        backside_default_preview = BacksidePreview(
            print_dict["backside_default"], img_dict
        )

        backside_offset_spin = QDoubleSpinBox()
        backside_offset_spin.setDecimals(2)
        backside_offset_spin.setRange(-inch_to_mm(0.3), inch_to_mm(0.3))
        backside_offset_spin.setSingleStep(0.1)
        backside_offset_spin.setSuffix("mm")
        backside_offset_spin.setValue(float(print_dict["backside_offset"]))
        backside_offset = WidgetWithLabel("Off&set", backside_offset_spin)

        backside_default_button.setEnabled(backside_enabled)
        backside_default_preview.setEnabled(backside_enabled)
        backside_offset.setEnabled(backside_enabled)

        back_over_divider = QFrame()
        back_over_divider.setFrameShape(QFrame.Shape.HLine)
        back_over_divider.setFrameShadow(QFrame.Shadow.Sunken)

        oversized_enabled = print_dict["oversized_enabled"]
        oversized_checkbox = QCheckBox("Enable Oversized Option")
        oversized_checkbox.setChecked(oversized_enabled)

        layout = QVBoxLayout()
        layout.addWidget(bleed_edge)
        layout.addWidget(bleed_back_divider)
        layout.addWidget(backside_checkbox)
        layout.addWidget(backside_default_button)
        layout.addWidget(backside_default_preview)
        layout.addWidget(backside_offset)
        layout.addWidget(back_over_divider)
        layout.addWidget(oversized_checkbox)

        layout.setAlignment(
            backside_default_preview, QtCore.Qt.AlignmentFlag.AlignHCenter
        )

        self.setLayout(layout)

        def change_bleed_edge(v):
            print_dict["bleed_edge"] = v
            self.window().refresh_preview(print_dict, img_dict)

        def switch_backside_enabled(s):
            enabled = s == QtCore.Qt.CheckState.Checked
            print_dict["backside_enabled"] = enabled
            backside_default_button.setEnabled(enabled)
            backside_default_preview.setEnabled(enabled)
            self.window().refresh(print_dict, img_dict)

        def pick_backside():
            default_backside_choice = image_file_dialog(self, print_dict["image_dir"])
            if default_backside_choice is not None:
                print_dict["backside_default"] = default_backside_choice
                backside_default_preview.refresh(
                    print_dict["backside_default"], img_dict
                )
                self.window().refresh(print_dict, img_dict)

        def change_backside_offset(v):
            print_dict["backside_offset"] = v
            self.window().refresh_preview(print_dict, img_dict)

        def switch_oversized_enabled(s):
            enabled = s == QtCore.Qt.CheckState.Checked
            print_dict["oversized_enabled"] = enabled
            self.window().refresh(print_dict, img_dict)

        bleed_edge_spin.valueChanged.connect(change_bleed_edge)
        backside_checkbox.checkStateChanged.connect(switch_backside_enabled)
        backside_default_button.clicked.connect(pick_backside)
        backside_offset_spin.valueChanged.connect(change_backside_offset)
        oversized_checkbox.checkStateChanged.connect(switch_oversized_enabled)

        self._bleed_edge_spin = bleed_edge_spin
        self._backside_checkbox = backside_checkbox
        self._backside_offset_spin = backside_offset_spin
        self._backside_default_preview = backside_default_preview
        self._oversized_checkbox = oversized_checkbox

    def refresh_widgets(self, print_dict):
        self._bleed_edge_spin.setValue(float(print_dict["bleed_edge"]))
        self._backside_checkbox.setChecked(print_dict["backside_enabled"])
        self._backside_offset_spin.setValue(float(print_dict["backside_offset"]))
        self._oversized_checkbox.setChecked(print_dict["oversized_enabled"])

    def refresh(self, print_dict, img_dict):
        self._backside_default_preview.refresh(print_dict["backside_default"], img_dict)


class GlobalOptionsWidget(QGroupBox):
    def __init__(self, print_dict, img_dict):
        super().__init__()

        self.setTitle("Global Config")

        display_columns_spin_box = QDoubleSpinBox()
        display_columns_spin_box.setDecimals(0)
        display_columns_spin_box.setRange(2, 10)
        display_columns_spin_box.setSingleStep(1)
        display_columns_spin_box.setValue(CFG.DisplayColumns)
        display_columns = WidgetWithLabel("Display &Columns", display_columns_spin_box)
        display_columns.setToolTip("Number columns in card view")

        precropped_checkbox = QCheckBox("Allow Precropped")
        precropped_checkbox.setChecked(CFG.EnableUncrop)
        precropped_checkbox.setToolTip(
            "Allows putting pre-cropped images into images/crop"
        )

        vibrance_checkbox = QCheckBox("Vibrance Bump")
        vibrance_checkbox.setChecked(CFG.VibranceBump)
        vibrance_checkbox.setToolTip("Requires rerunning cropper")

        max_dpi_spin_box = QDoubleSpinBox()
        max_dpi_spin_box.setDecimals(0)
        max_dpi_spin_box.setRange(300, 1200)
        max_dpi_spin_box.setSingleStep(100)
        max_dpi_spin_box.setValue(CFG.MaxDPI)
        max_dpi = WidgetWithLabel("&Max DPI", max_dpi_spin_box)
        max_dpi.setToolTip("Requires rerunning cropper")

        paper_sizes = ComboBoxWithLabel(
            "Default P&aper Size", list(page_sizes.keys()), CFG.DefaultPageSize
        )

        layout = QVBoxLayout()
        layout.addWidget(display_columns)
        layout.addWidget(precropped_checkbox)
        layout.addWidget(vibrance_checkbox)
        layout.addWidget(max_dpi)
        layout.addWidget(paper_sizes)

        self.setLayout(layout)

        def change_display_columns(v):
            CFG.DisplayColumns = int(v)
            save_config(CFG)
            self.window().refresh(print_dict, img_dict)

        def change_precropped(s):
            enabled = s == QtCore.Qt.CheckState.Checked
            CFG.EnableUncrop = enabled
            save_config(CFG)

        def change_vibrance_bump(s):
            enabled = s == QtCore.Qt.CheckState.Checked
            CFG.VibranceBump = enabled
            save_config(CFG)
            self.window().refresh_preview(print_dict, img_dict)

        def change_max_dpi(v):
            CFG.MaxDPI = int(v)
            save_config(CFG)

        def change_papersize(t):
            CFG.DefaultPageSize = t
            save_config(CFG)
            self.window().refresh_preview(print_dict, img_dict)

        display_columns_spin_box.valueChanged.connect(change_display_columns)
        precropped_checkbox.checkStateChanged.connect(change_precropped)
        vibrance_checkbox.checkStateChanged.connect(change_vibrance_bump)
        max_dpi_spin_box.valueChanged.connect(change_max_dpi)
        paper_sizes._widget.currentTextChanged.connect(change_papersize)


class OptionsWidget(QWidget):
    def __init__(
        self,
        application,
        print_dict,
        img_dict,
    ):
        super().__init__()

        actions_widget = ActionsWidget(
            application,
            print_dict,
            img_dict,
        )
        print_options = PrintOptionsWidget(print_dict, img_dict)
        card_options = CardOptionsWidget(print_dict, img_dict)
        global_options = GlobalOptionsWidget(print_dict, img_dict)

        layout = QVBoxLayout()
        layout.addWidget(actions_widget)
        layout.addWidget(print_options)
        layout.addWidget(card_options)
        layout.addWidget(global_options)
        layout.addStretch()

        self.setLayout(layout)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)

        self._print_options = print_options
        self._card_options = card_options

    def refresh_widgets(self, print_dict):
        self._print_options.refresh_widgets(print_dict)
        self._card_options.refresh_widgets(print_dict)

    def refresh(self, print_dict, img_dict):
        self._card_options.refresh(print_dict, img_dict)


class CardTabs(QTabWidget):
    def __init__(self, print_dict, img_dict, scroll_area, print_preview):
        super().__init__()

        self.addTab(scroll_area, "Cards")
        self.addTab(print_preview, "Preview")

        def current_changed(i):
            if i == 1:
                print_preview.refresh(print_dict, img_dict)

        self.currentChanged.connect(current_changed)


def window_setup(application, print_dict, img_dict):
    card_grid = CardGrid(print_dict, img_dict)
    scroll_area = CardScrollArea(print_dict, card_grid)

    print_preview = PrintPreview(print_dict, img_dict)

    tabs = CardTabs(print_dict, img_dict, scroll_area, print_preview)

    options = OptionsWidget(application, print_dict, img_dict)

    window = MainWindow(tabs, scroll_area, options, print_preview)
    application.set_window(window)

    window.show()
    return window


def event_loop(application):
    application.exec()
