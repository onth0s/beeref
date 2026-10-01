from unittest.mock import MagicMock, patch

import pytest
from PyQt6 import QtCore, QtWidgets

from beeref.config import BeeSettings
from beeref.view import BeeGraphicsView
from beeref.widgets.welcome_overlay import (
    MAX_COLUMNS,
    RecentFileCard,
    RecentFilesView,
    WelcomeOverlay,
)


def min_window_size():
    """Read MIN_WINDOW_SIZE lazily to avoid a circular import at module load."""
    from beeref.main_controls import MainControlsMixin
    return MainControlsMixin.MIN_WINDOW_SIZE


def visible_cards(root):
    """Return visible RecentFileCard widgets found under root."""
    return [c for c in root.findChildren(RecentFileCard) if not c.isHidden()]


def card_rects(root):
    """Map visible cards' geometry into root's coordinate space.

    Returns a list of (filepath, QRect).
    """
    rects = []
    for card in visible_cards(root):
        top_left = card.mapTo(root, QtCore.QPoint(0, 0))
        rects.append((card.filepath, QtCore.QRect(top_left, card.size())))
    return rects


def overlapping_pairs(rects):
    """Return (a, b, rect_a, rect_b) for every intersecting pair.

    'a'/'b' are filepaths; rect_a/rect_b are the offending QRects.
    """
    overlaps = []
    for i in range(len(rects)):
        for j in range(i + 1, len(rects)):
            if rects[i][1].intersects(rects[j][1]):
                overlaps.append((rects[i][0], rects[j][0],
                                 rects[i][1], rects[j][1]))
    return overlaps


def activate_layouts(qapp, overlay):
    """Force layout resolution and event delivery for an overlay.

    Note: WelcomeOverlay.layout shadows the QWidget.layout() method with a
    layout attribute, so it is used directly rather than called.
    """
    overlay.layout.activate()
    overlay.files_widget.layout().activate()
    overlay.files_view.grid_layout.activate()
    qapp.processEvents()


def _clear_recent_files_actions():
    """Drop the 'recent_files_*' entries a view adds to the global registry.

    Constructing a BeeGraphicsView registers one callback-less action per
    recent-file slot (beeref.actions.mixin._build_recent_files). A second
    view built in the same process then trips over those (getattr with a
    None callback). tests/conftest.py clears them between tests; a test that
    builds several overlays has to do the same between builds.
    """
    from beeref.actions.actions import actions
    for key in [k for k in actions if k.startswith('recent_files_')]:
        actions.pop(key)


def build_overlay(qtbot, qapp, files, width, height):
    """Construct a shown overlay resized to width x height.

    The overlay is resized and the recents are refreshed again afterwards,
    mirroring the real sequence (window resize -> overlay resized ->
    recents rebuilt) so any width-dependent layout logic runs against a
    settled viewport instead of a not-yet-laid-out one.

    The parent window is registered with qtbot so it is torn down after the
    test; leaking top-level windows makes the whole session unstable.
    """
    _clear_recent_files_actions()
    parent = QtWidgets.QMainWindow()
    qtbot.addWidget(parent)
    view = BeeGraphicsView(qapp, parent)
    overlay = WelcomeOverlay(view)
    overlay.resize(width, height)
    with patch('beeref.widgets.welcome_overlay.BeeSettings.get_recent_files',
               return_value=files):
        overlay.show()
        activate_layouts(qapp, overlay)
        overlay.resize(width, height)
        overlay.refresh_recents()
        activate_layouts(qapp, overlay)
    return overlay


@patch('beeref.widgets.welcome_overlay.BeeSettings.get_recent_files',
       return_value=[])
def test_welcome_overlay_when_no_recent_files(qtbot, qapp):
    parent = QtWidgets.QMainWindow()
    qtbot.addWidget(parent)
    view = BeeGraphicsView(qapp, parent)
    overlay = WelcomeOverlay(view)
    qtbot.addWidget(overlay)
    overlay.show()
    assert overlay.layout.indexOf(overlay.files_widget) < 0


def test_recent_file_card(qapp):
    card = RecentFileCard('foo.bee')
    assert card.filepath == 'foo.bee'


def test_recent_files_view_update_and_open(qtbot, qapp):
    parent = QtWidgets.QMainWindow()
    qtbot.addWidget(parent)
    view = BeeGraphicsView(qapp, parent)
    view.open_from_file = MagicMock()
    files_view = RecentFilesView(parent, view)
    qtbot.addWidget(files_view)
    files_view.update_files(['foo.bee', 'bar.bee'])
    assert len(files_view.files) == 2
    files_view.on_open_file('bar.bee')
    view.open_from_file.assert_called_once_with('bar.bee')


@patch('beeref.widgets.welcome_overlay.BeeSettings.get_recent_files',
       return_value=['foo.bee', 'bar.bee'])
def test_welcome_overlay_when_recent_files(qtbot, qapp):
    parent = QtWidgets.QMainWindow()
    qtbot.addWidget(parent)
    view = BeeGraphicsView(qapp, parent)
    overlay = WelcomeOverlay(view)
    qtbot.addWidget(overlay)
    overlay.show()
    assert overlay.layout.indexOf(overlay.files_widget) == 0


def test_overlap_detector_flags_known_overlap():
    rects = [('a.png', QtCore.QRect(0, 0, 150, 140)),
             ('b.png', QtCore.QRect(60, 60, 150, 140))]
    overlaps = overlapping_pairs(rects)
    assert len(overlaps) == 1
    assert overlaps[0][0] == 'a.png'
    assert overlaps[0][1] == 'b.png'


def test_overlap_detector_ignores_adjacent_rects():
    rects = [('a.png', QtCore.QRect(0, 0, 150, 140)),
             ('b.png', QtCore.QRect(0, 150, 150, 140)),
             ('c.png', QtCore.QRect(160, 0, 150, 140))]
    assert overlapping_pairs(rects) == []


def test_overlap_detector_catches_full_overlap():
    rects = [('a.png', QtCore.QRect(0, 0, 150, 140)),
             ('b.png', QtCore.QRect(0, 0, 150, 140))]
    assert len(overlapping_pairs(rects)) == 1


RESPONSIVE_SIZES = [(w, h)
                    for w in [220, 320, 641, 1280, 1920, 3840]
                    for h in [290, 400, 1080]]


def column_count_of(root):
    """Number of distinct column x-positions among the visible cards."""
    return len({r.x() for _, r in card_rects(root)})


@pytest.mark.parametrize('size', RESPONSIVE_SIZES,
                         ids=[f'{w}x{h}' for w, h in RESPONSIVE_SIZES])
@pytest.mark.parametrize('count', [1, 12])
def test_recents_never_overlap(qtbot, qapp, size, count):
    width, height = size
    files = [f'/tmp/img{i}.png' for i in range(count)]
    overlay = build_overlay(qtbot, qapp, files, width, height)
    rects = card_rects(overlay)
    assert len(rects) == count
    overlaps = overlapping_pairs(rects)
    assert overlaps == [], (
        f'{len(overlaps)} overlapping card pair(s) at {width}x{height}, '
        f'first: {overlaps[0][0]} {overlaps[0][2].getRect()} vs '
        f'{overlaps[0][1]} {overlaps[0][3].getRect()}' if overlaps else '')


def test_recents_many_files_never_overlap(qtbot, qapp):
    files = [f'/tmp/img{i}.png' for i in range(30)]
    overlay = build_overlay(qtbot, qapp, files, 1280, 1080)
    rects = card_rects(overlay)
    assert len(rects) == 30
    assert overlapping_pairs(rects) == []


@pytest.mark.parametrize('size', [(270, 290), (320, 340), (400, 400)],
                         ids=['270x290', '320x340', '400x400'])
def test_recents_single_column_when_narrow(qtbot, qapp, size):
    width, height = size
    files = [f'/tmp/img{i}.png' for i in range(9)]
    overlay = build_overlay(qtbot, qapp, files, width, height)
    columns = column_count_of(overlay)
    assert columns == 1, (
        f'expected a single column at constrained size {width}x{height}, '
        f'got {columns}')


@pytest.mark.parametrize('width', [1280, 1920, 3840])
def test_recents_multi_column_when_wide(qtbot, qapp, width):
    files = [f'/tmp/img{i}.png' for i in range(12)]
    overlay = build_overlay(qtbot, qapp, files, width, 1080)
    columns = column_count_of(overlay)
    assert columns > 1, f'expected multiple columns at width {width}'
    assert columns <= MAX_COLUMNS


def test_recents_never_exceeds_max_columns(qtbot, qapp):
    files = [f'/tmp/img{i}.png' for i in range(30)]
    overlay = build_overlay(qtbot, qapp, files, 3840, 2160)
    assert column_count_of(overlay) == MAX_COLUMNS
    assert overlapping_pairs(card_rects(overlay)) == []


def test_recents_columns_monotonic_with_width(qtbot, qapp):
    files = [f'/tmp/img{i}.png' for i in range(12)]
    counts = [
        column_count_of(build_overlay(qtbot, qapp, files, width, 1080))
        for width in [270, 320, 400, 500, 641, 800, 1000, 1280, 1920]
    ]
    assert counts == sorted(counts), f'columns are not monotonic: {counts}'
    assert counts[0] == 1, f'expected 1 column when narrow, got {counts[0]}'
    assert counts[-1] == MAX_COLUMNS, (
        f'expected {MAX_COLUMNS} columns when wide, got {counts[-1]}')


def test_recents_reflow_on_resize(qtbot, qapp):
    files = [f'/tmp/img{i}.png' for i in range(12)]
    overlay = build_overlay(qtbot, qapp, files, 1600, 900)
    wide = column_count_of(overlay)
    assert wide == MAX_COLUMNS

    overlay.resize(300, 290)
    activate_layouts(qapp, overlay)
    assert column_count_of(overlay) == 1, 'did not collapse to one column'
    assert overlapping_pairs(card_rects(overlay)) == []

    overlay.resize(1600, 900)
    activate_layouts(qapp, overlay)
    assert column_count_of(overlay) == wide, 'did not reflow back to wide'
    assert overlapping_pairs(card_rects(overlay)) == []


@pytest.mark.parametrize('width', [400, 641, 800, 1280])
def test_recents_grid_horizontally_centered(qtbot, qapp, width):
    files = [f'/tmp/img{i}.png' for i in range(3)]
    overlay = build_overlay(qtbot, qapp, files, width, 800)
    files_view = overlay.files_view
    viewport = files_view.viewport()
    vp_rect = QtCore.QRect(
        viewport.mapTo(overlay, QtCore.QPoint(0, 0)), viewport.size())

    rects = [r for _, r in card_rects(overlay)]
    left_gap = min(r.left() for r in rects) - vp_rect.left()
    right_gap = vp_rect.right() - max(r.right() for r in rects)
    assert abs(left_gap - right_gap) <= 1, (
        f'grid not centered in viewport at width {width}: '
        f'left gap {left_gap}, right gap {right_gap}')


def test_recents_scrolls_instead_of_overflowing(qtbot, qapp):
    files = [f'/tmp/img{i}.png' for i in range(12)]
    overlay = build_overlay(qtbot, qapp, files, 320, 290)
    bar = overlay.files_view.verticalScrollBar()
    assert bar.maximum() > 0, 'expected a scrollable range at 320x290'


def test_recents_scroll_reveals_last_card(qtbot, qapp):
    files = [f'/tmp/img{i}.png' for i in range(12)]
    overlay = build_overlay(qtbot, qapp, files, 320, 290)
    files_view = overlay.files_view
    bar = files_view.verticalScrollBar()
    bar.setValue(bar.maximum())
    qapp.processEvents()
    files_view.grid_layout.activate()
    qapp.processEvents()

    last_card = visible_cards(files_view)[-1]
    tl = last_card.mapTo(files_view.viewport(), QtCore.QPoint(0, 0))
    last_rect = QtCore.QRect(tl, last_card.size())
    assert files_view.viewport().rect().contains(last_rect), (
        f'last card {last_rect.getRect()} not fully visible in viewport '
        f'{files_view.viewport().rect().getRect()}')


def test_min_window_size_shows_a_full_card(qtbot, qapp):
    files = [f'/tmp/img{i}.png' for i in range(12)]
    size = min_window_size()
    overlay = build_overlay(qtbot, qapp, files, size.width(), size.height())
    files_view = overlay.files_view
    rects = card_rects(overlay)
    assert overlapping_pairs(rects) == []

    first = visible_cards(files_view)[0]
    tl = first.mapTo(files_view.viewport(), QtCore.QPoint(0, 0))
    first_rect = QtCore.QRect(tl, first.size())
    assert files_view.viewport().rect().contains(first_rect), (
        f'first card not fully visible at minimum window size {size.width()}'
        f'x{size.height()}: {first_rect.getRect()} vs '
        f'{files_view.viewport().rect().getRect()}')


def test_main_window_minimum_size_matches(main_window):
    expected = min_window_size()
    assert main_window.minimumWidth() == expected.width()
    assert main_window.minimumHeight() == expected.height()


def test_no_stale_cards_after_update_files(qtbot, qapp):
    parent = QtWidgets.QMainWindow()
    qtbot.addWidget(parent)
    view = BeeGraphicsView(qapp, parent)
    files_view = RecentFilesView(parent, view)
    files_view.resize(400, 800)
    files_view.show()
    files_view.update_files([f'/tmp/img{i}.png' for i in range(6)])
    qapp.processEvents()
    assert len(visible_cards(files_view)) == 6

    # Checked synchronously, before the event loop runs: if anything holds a
    # reference to the old cards, removing them from the layout alone is not
    # enough -- they stay parented and stay painted, piling up on top of the
    # new cards. Counting child widgets catches exactly that.
    files_view.update_files(['/tmp/img0.png', '/tmp/img1.png'])
    children = files_view.findChildren(RecentFileCard)
    assert len(children) == 2, (
        f'expected 2 card widgets after update, found {len(children)}: '
        f'{[c.filepath for c in children]}')

    qapp.processEvents()
    assert len(visible_cards(files_view)) == 2, (
        f'expected 2 visible cards after update, found '
        f'{[c.filepath for c in visible_cards(files_view)]}')


def test_relayout_is_idempotent(qtbot, qapp):
    parent = QtWidgets.QMainWindow()
    qtbot.addWidget(parent)
    view = BeeGraphicsView(qapp, parent)
    files = [f'/tmp/img{i}.png' for i in range(5)]
    files_view = RecentFilesView(parent, view, files)
    files_view.resize(1200, 800)
    files_view.show()
    qapp.processEvents()
    files_view.grid_layout.activate()
    qapp.processEvents()

    before = card_rects(files_view)
    files_view.relayout()
    qapp.processEvents()
    files_view.grid_layout.activate()
    qapp.processEvents()
    after = card_rects(files_view)

    assert before == after, 'relayout() changed card geometry'
    assert overlapping_pairs(after) == []


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

