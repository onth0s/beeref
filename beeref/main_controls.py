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
import os

from PyQt6 import QtCore, QtGui
from PyQt6.QtCore import Qt

from beeref import commands, constants, fileio, widgets
from beeref.items import BeePixmapItem

logger = logging.getLogger(__name__)


class MainControlsMixin:
    """Basic controls shared by the main view and the welcome overlay:

    * Right-click menu
    * Dropping files
    * Moving and resizing the window without title bar
    """

    # Thickness of the window's resize area when the title bar is
    # hidden. Matches the native Windows frame so the edge is about as
    # easy to grab as it would be with a title bar.
    RESIZE_MARGIN = 8
    # Large enough that a full-size recent files card plus its header, help
    # text and padding always fit, so cards are never cut off or squeezed.
    MIN_WINDOW_SIZE = QtCore.QSize(*constants.MIN_WINDOW_SIZE)

    # Window manipulation state. Declared here so the mixin is usable
    # before (or without) init_main_controls, e.g. for the cursor
    # guard, which can be queried as soon as signals are connected.
    movewin_active = False
    resizewin_active = False
    resizewin_edges = frozenset()
    last_resizewin_cursor = None

    def init_main_controls(self, main_window):
        self.main_window = main_window
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(
            self.control_target.on_context_menu)
        self.setAcceptDrops(True)
        self.movewin_active = False
        self.resizewin_active = False
        self.resizewin_edges = set()
        self.last_resizewin_cursor = None
        # Needed for hover feedback on the resize edges
        self.setMouseTracking(True)
        self.viewport_or_self.setMouseTracking(True)

    def on_action_movewin_mode(self):
        if self.movewin_active:
            # Pressing the same shortcut again should end the action
            self.exit_movewin_mode()
        else:
            self.enter_movewin_mode()

    @property
    def viewport_or_self(self):
        if hasattr(self, 'viewport'):
            return self.viewport()
        return self

    def enter_movewin_mode(self):
        logger.debug('Entering movewin mode')
        self.movewin_active = True
        self.last_resizewin_cursor = None
        self.viewport_or_self.setCursor(Qt.CursorShape.SizeAllCursor)
        self.event_start = QtCore.QPointF(self.cursor().pos())
        if hasattr(self, 'disable_mouse_events'):
            self.disable_mouse_events()

    def exit_movewin_mode(self):
        logger.debug('Exiting movewin mode')
        self.movewin_active = False
        self.last_resizewin_cursor = None
        self.viewport_or_self.unsetCursor()
        if hasattr(self, 'enable_mouse_events'):
            self.enable_mouse_events()

    @property
    def resizewin_possible(self):
        """Resizing is only possible on frameless, non-fullscreen
        windows."""
        win = self.main_window
        return bool(
            win.windowFlags() & Qt.WindowType.FramelessWindowHint
            and not win.isFullScreen())

    @property
    def cursor_owned_by_resize(self):
        """Whether the window's resize area currently owns the cursor.

        Item hover events are delivered *after* the mouse move event,
        so without this guard an image's own cursor (e.g. the scale
        cursor of a selected item whose border touches the window
        border) would overwrite the resize cursor right at the window
        edge, making the window look unresizable.
        """
        return self.resizewin_active or bool(self.resize_edges_at_cursor())

    def resize_edges_at_cursor(self):
        """The edges of the resize area the mouse cursor is currently
        over.

        This asks for the real cursor position instead of reusing the
        position of the last mouse move event, because item hover and
        mouse move events do not necessarily arrive in the same order,
        so a cached position may be one event behind and let an item
        grab the cursor at the very window edge.
        """
        if not self.resizewin_possible:
            return set()
        local_pos = self.viewport_or_self.mapFromGlobal(QtGui.QCursor.pos())
        return self.edges_within_margin(self.viewport_or_self.rect(), local_pos)

    def edges_within_margin(self, rect, pos):
        """Return the edges ('left', 'right', 'top', 'bottom') of the
        given rect that the given position within it is less than
        RESIZE_MARGIN pixels away from."""
        x, y = pos.x(), pos.y()
        edges = set()
        if x < rect.left() + self.RESIZE_MARGIN:
            edges.add('left')
        elif x > rect.right() - self.RESIZE_MARGIN:
            edges.add('right')
        if y < rect.top() + self.RESIZE_MARGIN:
            edges.add('top')
        elif y > rect.bottom() - self.RESIZE_MARGIN:
            edges.add('bottom')
        return edges

    def resize_edges_for_local_pos(self, pos):
        """Return the edges ('left', 'right', 'top', 'bottom') of the
        window the given position is within RESIZE_MARGIN pixels of.

        The position is given in the control target's own coordinate
        system (i.e. the viewport for the view, the widget itself for
        the welcome overlay). Both of them fill the entire window, so
        this stays correct regardless of menu bars, scroll bars or
        frames -- unlike measuring against the window's global frame
        geometry, which is off by however much the client area is
        inset.
        """
        if not self.resizewin_possible:
            return set()
        return self.edges_within_margin(self.viewport_or_self.rect(), pos)

    def resize_cursor_for_edges(self, edges):
        if 'left' in edges or 'right' in edges:
            if 'top' in edges or 'bottom' in edges:
                if ('left' in edges) == ('top' in edges):
                    return Qt.CursorShape.SizeFDiagCursor
                return Qt.CursorShape.SizeBDiagCursor
            return Qt.CursorShape.SizeHorCursor
        if 'top' in edges or 'bottom' in edges:
            return Qt.CursorShape.SizeVerCursor
        return None

    def apply_resize_cursor(self, cursor):
        """Set the cursor of the control target to the resize cursor for
        the given edges, or remove the override for ``None``."""
        if cursor is None:
            self.viewport_or_self.unsetCursor()
        else:
            self.viewport_or_self.setCursor(cursor)
        self.last_resizewin_cursor = cursor

    def enter_resizewin_mode(self, edges, event):
        logger.debug(f'Entering resizewin mode: {sorted(edges)}')
        self.resizewin_active = True
        self.resizewin_edges = edges
        self.event_start = QtCore.QPointF(self.mapToGlobal(event.position()))
        self.event_start_geometry = QtCore.QRect(
            self.main_window.frameGeometry())
        self.apply_resize_cursor(self.resize_cursor_for_edges(edges))

    def exit_resizewin_mode(self):
        logger.debug('Exiting resizewin mode')
        self.resizewin_active = False
        self.resizewin_edges = set()
        self.apply_resize_cursor(None)

    def apply_resizewin_delta(self, pos):
        win = self.main_window
        geo = QtCore.QRect(self.event_start_geometry)
        min_w = max(win.minimumWidth(), self.MIN_WINDOW_SIZE.width())
        min_h = max(win.minimumHeight(), self.MIN_WINDOW_SIZE.height())
        delta = pos - self.event_start
        edges = self.resizewin_edges
        if 'left' in edges:
            geo.setLeft(min(round(geo.left() + delta.x()),
                            geo.right() - min_w + 1))
        if 'right' in edges:
            geo.setRight(max(round(geo.right() + delta.x()),
                             geo.left() + min_w - 1))
        if 'top' in edges:
            geo.setTop(min(round(geo.top() + delta.y()),
                           geo.bottom() - min_h + 1))
        if 'bottom' in edges:
            geo.setBottom(max(round(geo.bottom() + delta.y()),
                              geo.top() + min_h - 1))
        win.setGeometry(geo)

    def update_resizewin_cursor(self, event):
        edges = self.resize_edges_for_local_pos(event.position())
        cursor = self.resize_cursor_for_edges(edges)
        if not edges and cursor == self.last_resizewin_cursor:
            # Nothing to restore outside of the resize area. Don't
            # unset the cursor there, or we would fight with the items'
            # own hover cursors.
            return
        # Inside the resize area the cursor is re-applied on every move
        # instead of relying on the cached one, so it is restored even
        # if something reset it in between (e.g. a widget hover event
        # or leaving and re-entering the window).
        self.apply_resize_cursor(cursor)

    def dragEnterEvent(self, event):
        mimedata = event.mimeData()
        logger.debug(f'Drag enter event: {mimedata.formats()}')
        if mimedata.hasUrls() or mimedata.hasImage():
            event.acceptProposedAction()
        else:
            msg = 'Attempted drop not an image or image too big'
            logger.info(msg)
            widgets.BeeNotification(self.control_target, msg)

    def dragMoveEvent(self, event):
        event.acceptProposedAction()

    def dropEvent(self, event):
        mimedata = event.mimeData()
        logger.debug(f'Handling file drop: {mimedata.formats()}')
        pos = QtCore.QPoint(round(event.position().x()),
                            round(event.position().y()))
        if mimedata.hasUrls():
            logger.debug(f'Found dropped urls: {mimedata.urls()}')
            if not self.control_target.scene.items():
                # Check if we have a bee file we can open directly
                path = mimedata.urls()[0]
                if (path.isLocalFile()
                        and fileio.is_bee_file(path.toLocalFile())):
                    self.control_target.open_from_file(
                        os.path.normpath(path.toLocalFile()))
                    return
            self.control_target.do_insert_images(mimedata.urls(), pos)
        elif mimedata.hasImage():
            img = QtGui.QImage(mimedata.imageData())
            item = BeePixmapItem(img)
            pos = self.control_target.mapToScene(pos)
            self.control_target.undo_stack.push(
                commands.InsertItems(self.control_target.scene, [item], pos))
        else:
            logger.info('Drop not an image')

    def mousePressEventMainControls(self, event):
        if self.movewin_active:
            self.exit_movewin_mode()
            event.accept()
            return True

        action, _inverted =\
            self.control_target.keyboard_settings.mouse_action_for_event(event)
        if action == 'movewindow':
            self.enter_movewin_mode()
            event.accept()
            return True

        if self.resizewin_possible:
            edges = self.resize_edges_for_local_pos(event.position())
            if edges:
                self.enter_resizewin_mode(edges, event)
                event.accept()
                return True

    def mouseMoveEventMainControls(self, event):
        if self.movewin_active:
            pos = self.mapToGlobal(event.position())
            delta = pos - self.event_start
            self.event_start = pos
            self.main_window.move(self.main_window.x() + int(delta.x()),
                                  self.main_window.y() + int(delta.y()))
            event.accept()
            return True

        if self.resizewin_active:
            self.apply_resizewin_delta(
                QtCore.QPointF(self.mapToGlobal(event.position())))
            event.accept()
            return True

        self.update_resizewin_cursor(event)

    def mouseReleaseEventMainControls(self, event):
        if self.movewin_active:
            self.exit_movewin_mode()
            event.accept()
            return True
        if self.resizewin_active:
            self.exit_resizewin_mode()
            event.accept()
            return True

    def keyPressEventMainControls(self, event):
        if self.movewin_active:
            self.exit_movewin_mode()
            event.accept()
            return True
        if self.resizewin_active:
            self.exit_resizewin_mode()
            event.accept()
            return True
