from unittest.mock import MagicMock, patch

from PyQt6 import QtWidgets

from beeref.config import BeeSettings
from beeref.view import BeeGraphicsView
from beeref.widgets.welcome_overlay import (
    RecentFileCard,
    RecentFilesView,
    WelcomeOverlay,
)


@patch('beeref.widgets.welcome_overlay.BeeSettings.get_recent_files',
       return_value=[])
def test_welcome_overlay_when_no_recent_files(qapp):
    parent = QtWidgets.QMainWindow()
    view = BeeGraphicsView(qapp, parent)
    overlay = WelcomeOverlay(view)
    overlay.show()
    assert overlay.layout.indexOf(overlay.files_widget) < 0


def test_recent_file_card(qapp):
    card = RecentFileCard('foo.bee')
    assert card.filepath == 'foo.bee'


def test_recent_files_view_update_and_open(qapp):
    parent = QtWidgets.QMainWindow()
    view = BeeGraphicsView(qapp, parent)
    view.open_from_file = MagicMock()
    files_view = RecentFilesView(parent, view)
    files_view.update_files(['foo.bee', 'bar.bee'])
    assert len(files_view.files) == 2
    files_view.on_open_file('bar.bee')
    view.open_from_file.assert_called_once_with('bar.bee')


@patch('beeref.widgets.welcome_overlay.BeeSettings.get_recent_files',
       return_value=['foo.bee', 'bar.bee'])
def test_welcome_overlay_when_recent_files(qapp):
    parent = QtWidgets.QMainWindow()
    view = BeeGraphicsView(qapp, parent)
    overlay = WelcomeOverlay(view)
    overlay.show()
    assert overlay.layout.indexOf(overlay.files_widget) == 0






@patch('beeref.config.settings.BeeSettings.get_recent_files', return_value=['foo.bee', 'bar.bee'])
@patch('beeref.config.settings.BeeSettings.remove')
def test_clear_recent_files(mock_remove, mock_get_recents, qapp):
    settings = BeeSettings()
    settings.clear_recent_files()
    mock_remove.assert_called_with('RecentFiles')


@patch('PyQt6.QtWidgets.QGraphicsView.mousePressEvent')
def test_mouse_press_when_move_window_active(mouse_event_mock, qapp):
    parent = QtWidgets.QMainWindow()
    view = BeeGraphicsView(qapp, parent)
    overlay = WelcomeOverlay(view)
    overlay.movewin_active = True
    overlay.mousePressEvent(MagicMock())
    assert overlay.movewin_active is False
    mouse_event_mock.assert_not_called()

