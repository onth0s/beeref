# This file is part of BeeRef.
#
# BeeRef is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# BeeRef is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with BeeRef.  If not, see <https://www.gnu.org/licenses/>.

import logging
import os.path

from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtCore import Qt

from beeref.config import BeeSettings
from beeref.main_controls import MainControlsMixin
from beeref.thumbnails import get_thumbnail

logger = logging.getLogger(__name__)

# Recents grid geometry. Single source of truth: the card sizes itself from
# these and the layout derives its spacing from them, so they cannot drift.
CARD_WIDTH = 150
CARD_HEIGHT = 140
THUMB_WIDTH = 138
THUMB_HEIGHT = 95
GRID_SPACING = 10
GRID_MARGIN = 6
CLOSE_BTN_SIZE = 22
# The grid is responsive: it uses as many columns as fit the available
# width, but never fewer than one and never more than this.
MAX_COLUMNS = 5


class RecentFileCard(QtWidgets.QFrame):
    """Widget card displaying thumbnail, file name, and an on-hover 'X' remove button."""

    remove_requested = QtCore.pyqtSignal(str)
    open_requested = QtCore.pyqtSignal(str)

    def __init__(self, filepath, parent=None):
        super().__init__(parent)
        self.filepath = filepath
        self.setMouseTracking(True)
        self.setFixedSize(CARD_WIDTH, CARD_HEIGHT)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self.setStyleSheet("""
            RecentFileCard {
                background-color: rgba(255, 255, 255, 0.05);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 8px;
            }
            RecentFileCard:hover {
                background-color: rgba(255, 255, 255, 0.12);
                border: 1px solid rgba(255, 255, 255, 0.25);
            }
        """)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(GRID_MARGIN, GRID_MARGIN, GRID_MARGIN,
                                  GRID_MARGIN)
        layout.setSpacing(4)

        # Thumbnail Label
        self.thumb_label = QtWidgets.QLabel(self)
        self.thumb_label.setFixedSize(THUMB_WIDTH, THUMB_HEIGHT)
        self.thumb_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.thumb_label.setStyleSheet("border-radius: 4px; background-color: rgba(0, 0, 0, 0.2);")

        pix = get_thumbnail(self.filepath,
                            QtCore.QSize(THUMB_WIDTH, THUMB_HEIGHT))
        if pix and not pix.isNull():
            self.thumb_label.setPixmap(pix)
        else:
            self.thumb_label.setText("No Preview")

        layout.addWidget(self.thumb_label)

        # Filename Label
        filename = os.path.basename(self.filepath)
        self.name_label = QtWidgets.QLabel(filename, self)
        self.name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.name_label.setToolTip(self.filepath)
        font = self.name_label.font()
        font.setPointSize(9)
        self.name_label.setFont(font)

        metrics = QtGui.QFontMetrics(font)
        elided = metrics.elidedText(filename, Qt.TextElideMode.ElideMiddle,
                                    CARD_WIDTH - 2 * GRID_MARGIN - 4)
        self.name_label.setText(elided)

        layout.addWidget(self.name_label)

        # On-hover 'X' close button
        self.close_btn = QtWidgets.QPushButton("✕", self)
        self.close_btn.setFixedSize(CLOSE_BTN_SIZE, CLOSE_BTN_SIZE)
        self.close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.close_btn.setToolTip("Remove from recent files")
        self.close_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(0, 0, 0, 0.65);
                color: #ffffff;
                border: none;
                border-radius: 11px;
                font-weight: bold;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #e53935;
                color: #ffffff;
            }
        """)
        self.close_btn.move(CARD_WIDTH - CLOSE_BTN_SIZE - 4, 4)
        self.close_btn.hide()
        self.close_btn.clicked.connect(self.on_close_clicked)

    def enterEvent(self, event):
        self.close_btn.show()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.close_btn.hide()
        super().leaveEvent(event)

    def on_close_clicked(self):
        self.remove_requested.emit(self.filepath)

    def mousePressEvent(self, event):
        if (event.button() == Qt.MouseButton.LeftButton
                and not self.close_btn.geometry().contains(event.position().toPoint())):
            self.open_requested.emit(self.filepath)
        super().mousePressEvent(event)


class RecentFilesView(QtWidgets.QScrollArea):
    """Scrollable, responsive grid of RecentFileCard widgets.

    Cards are a fixed size and are never shrunk. The grid uses as many
    columns as fit the available width (1 when the window is narrow, up to
    MAX_COLUMNS otherwise) and scrolls vertically instead of squeezing the
    cards into an overlapping pile. The block of columns stays horizontally
    centered.
    """

    def __init__(self, parent, view, files=None):
        super().__init__(parent)
        self.view = view
        self.files = files or []

        self.setWidgetResizable(True)
        self.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # The grid never needs to scroll horizontally: its column count is
        # derived from the viewport width, so it always fits.
        self.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        # Enough room for a single card plus its grid padding, so a card is
        # always fully visible even in the smallest allowed window.
        self.setMinimumHeight(CARD_HEIGHT + 2 * GRID_MARGIN)
        # A QScrollArea's own size hint does not account for its widget, so
        # without an explicit minimum the section would be squeezed to the
        # point that the card no longer fits in the viewport.
        self.setMinimumWidth(
            CARD_WIDTH + 2 * GRID_MARGIN
            + self.verticalScrollBar().sizeHint().width())

        self._grid_parent = QtWidgets.QWidget(self)
        self.grid_layout = QtWidgets.QGridLayout(self._grid_parent)
        self.grid_layout.setContentsMargins(GRID_MARGIN, GRID_MARGIN,
                                             GRID_MARGIN, GRID_MARGIN)
        self.grid_layout.setSpacing(GRID_SPACING)
        self.grid_layout.setAlignment(
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        self.setWidget(self._grid_parent)

        self._cards = []
        self._columns = 1
        self.update_files(self.files)

    def update_files(self, files):
        self.files = list(files)
        self.relayout()

    def column_count(self):
        """Number of columns that fit the viewport, clamped to 1..MAX_COLUMNS."""
        available = self.viewport().width() - 2 * GRID_MARGIN
        if available < CARD_WIDTH:
            return 1
        return max(1, min(MAX_COLUMNS,
                          (available + GRID_SPACING)
                          // (CARD_WIDTH + GRID_SPACING)))

    def _place_cards(self):
        """Lay the existing cards out in the current number of columns."""
        # Assign self._columns before touching the layout: re-adding widgets
        # invalidates it and can deliver a nested resize event, which would
        # otherwise recurse because the column count still looked stale.
        self._columns = self.column_count()
        for card in self._cards:
            self.grid_layout.removeWidget(card)
        for i, card in enumerate(self._cards):
            self.grid_layout.addWidget(
                card, i // self._columns, i % self._columns)

    def relayout(self):
        """Rebuild the card widgets and lay them out from scratch.

        Old cards are hidden and unparented explicitly rather than just
        scheduled for deletion, so their removal cannot be delayed by the
        garbage collector holding a reference, and a card can never linger
        as a stale, still-painted child on top of a new one.
        """
        for card in self._cards:
            self.grid_layout.removeWidget(card)
            # Hide before unparenting: setParent(None) would otherwise turn
            # the still-visible card into a top-level window for a moment.
            card.hide()
            card.setParent(None)
            card.deleteLater()
        self._cards = []

        for filepath in self.files:
            card = RecentFileCard(filepath, self._grid_parent)
            card.remove_requested.connect(self.on_remove_file)
            card.open_requested.connect(self.on_open_file)
            self._cards.append(card)

        self._place_cards()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Reflow into more or fewer columns as the window grows and shrinks.
        # Rebuilding the cards is neither necessary nor safe here; only the
        # placement changes.
        if self._cards and self.column_count() != self._columns:
            self._place_cards()

    def on_open_file(self, filepath):
        self.view.open_from_file(filepath)

    def on_remove_file(self, filepath):
        BeeSettings().remove_recent_file(filepath)
        # Notify overlay to refresh
        parent = self.parent()
        while parent:
            if isinstance(parent, WelcomeOverlay):
                parent.refresh_recents()
                break
            parent = parent.parent()


class WelcomeOverlay(MainControlsMixin, QtWidgets.QWidget):
    """Some basic info to be displayed when the scene is empty."""

    txt = """<p>Paste or drop images here.</p>
             <p>Right-click for more options.</p>"""

    def __init__(self, parent):
        super().__init__(parent)
        self.control_target = parent
        self.setAutoFillBackground(True)
        self.init_main_controls(main_window=parent.parent)

        # Recent files section widget
        self.files_widget = QtWidgets.QWidget(self)
        files_vbox = QtWidgets.QVBoxLayout(self.files_widget)
        files_vbox.setContentsMargins(0, 0, 0, 0)
        files_vbox.setSpacing(8)

        header_box = QtWidgets.QHBoxLayout()
        header_title = QtWidgets.QLabel('<h3>Recent Files</h3>', self.files_widget)
        header_box.addWidget(header_title)
        header_box.addStretch()

        self.clear_btn = QtWidgets.QPushButton('Clear', self.files_widget)
        self.clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clear_btn.setToolTip('Clear all recent files history')
        self.clear_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #aaa;
                border: 1px solid #555;
                border-radius: 4px;
                padding: 3px 10px;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 0.1);
                color: #fff;
                border-color: #888;
            }
        """)
        self.clear_btn.clicked.connect(self.on_clear_all_clicked)
        header_box.addWidget(self.clear_btn)

        files_vbox.addLayout(header_box)

        self.files_view = RecentFilesView(self.files_widget, parent)
        files_vbox.addWidget(self.files_view, 1)
        self.files_widget.hide()

        # Help text label
        self.label = QtWidgets.QLabel(self.txt, self)
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Main layout: the recent files section is inserted at index 0 by
        # refresh_recents(). A plain QHBoxLayout with fixed stretches used to
        # starve the section of width, which is what made the cards overlap;
        # it is now centered explicitly on both axes.
        self.layout = QtWidgets.QVBoxLayout(self)
        self.layout.setContentsMargins(40, 20, 40, 20)
        self.layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.layout.addWidget(self.label)


    def refresh_recents(self):
        files = BeeSettings().get_recent_files(existing_only=True)
        self.files_view.update_files(files)
        if hasattr(self.control_target.parent, '_build_recent_files'):
            self.control_target.parent._build_recent_files()

        if files:
            if self.layout.indexOf(self.files_widget) < 0:
                self.layout.insertWidget(0, self.files_widget)
            self.files_widget.show()
        else:
            if self.layout.indexOf(self.files_widget) >= 0:
                self.layout.removeWidget(self.files_widget)
            self.files_widget.hide()



    def show(self):
        self.refresh_recents()
        super().show()


    def on_clear_all_clicked(self):
        confirm = QtWidgets.QMessageBox.question(
            self,
            "Clear Recent Files",
            "Are you sure you want to clear all recent files history?",
            QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
            QtWidgets.QMessageBox.StandardButton.No
        )
        if confirm == QtWidgets.QMessageBox.StandardButton.Yes:
            BeeSettings().clear_recent_files()
            self.refresh_recents()

    def disable_mouse_events(self):
        self.files_view.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.label.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def enable_mouse_events(self):
        self.files_view.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents,
            on=False)
        self.label.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents,
            on=False)


    def mousePressEvent(self, event):
        if self.mousePressEventMainControls(event):
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.mouseMoveEventMainControls(event):
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self.mouseReleaseEventMainControls(event):
            return
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event):
        if self.keyPressEventMainControls(event):
            return
        super().keyPressEvent(event)


