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

import hashlib
import logging
import os
import sqlite3

from PyQt6 import QtCore, QtGui, QtWidgets

logger = logging.getLogger(__name__)


def get_cache_dir():
    cache_base = QtCore.QStandardPaths.writableLocation(
        QtCore.QStandardPaths.StandardLocation.CacheLocation)
    cache_dir = os.path.join(cache_base, 'thumbnails')
    os.makedirs(cache_dir, exist_ok=True)
    return cache_dir


def get_thumbnail(filepath, size=QtCore.QSize(180, 140)):
    """Returns a QPixmap thumbnail for a given file (either .bee or image).
    Cached on disk using file modification time.
    """
    if not os.path.exists(filepath):
        return None

    try:
        mtime = str(os.path.getmtime(filepath))
        key = hashlib.md5(f'{filepath}_{mtime}'.encode('utf-8')).hexdigest()
        cache_path = os.path.join(get_cache_dir(), f'{key}.png')

        if os.path.exists(cache_path):
            pix = QtGui.QPixmap(cache_path)
            if not pix.isNull():
                return pix

        pix = render_thumbnail(filepath, size)
        if pix and not pix.isNull():
            pix.save(cache_path, 'PNG')
            return pix
    except Exception:
        logger.exception(f'Failed to generate thumbnail for {filepath}')

    return None


def render_thumbnail(filepath, size):
    ext = os.path.splitext(filepath)[1].lower()
    if ext == '.bee':
        return render_bee_thumbnail(filepath, size)
    else:
        return render_image_thumbnail(filepath, size)


def render_image_thumbnail(filepath, size):
    reader = QtGui.QImageReader(filepath)
    reader.setAutoTransform(True)
    orig_size = reader.size()
    if orig_size.isValid():
        scaled_size = orig_size.scaled(size, QtCore.Qt.AspectRatioMode.KeepAspectRatio)
        reader.setScaledSize(scaled_size)
    img = reader.read()
    if img.isNull():
        return None
    return QtGui.QPixmap.fromImage(img)


def render_bee_thumbnail(filepath, size):
    """Renders the scene items in a .bee file into a thumbnail pixmap."""
    scene = QtWidgets.QGraphicsScene()
    try:
        conn = sqlite3.connect(filepath)
        cursor = conn.cursor()

        # Fetch pixmaps from DB
        rows = cursor.execute(
            'SELECT items.id, type, x, y, z, scale, rotation, flip, '
            'items.data, sqlar.data '
            'FROM sqlar JOIN items on sqlar.item_id = items.id'
        ).fetchall()
        conn.close()

        if not rows:
            return None

        bounds = QtCore.QRectF()
        for row in rows:
            item_type = row[1]
            x, y, z = row[2], row[3], row[4]
            scale, rotation, flip = row[5], row[6], row[7]
            img_bytes = row[9]

            if item_type == 'pixmap' and img_bytes:
                img = QtGui.QImage()
                img.loadFromData(img_bytes)
                if not img.isNull():
                    pix_item = QtWidgets.QGraphicsPixmapItem(QtGui.QPixmap.fromImage(img))
                    pix_item.setPos(x, y)
                    pix_item.setZValue(z)

                    transform = QtGui.QTransform()
                    transform.scale(scale * flip, scale)
                    transform.rotate(rotation)
                    pix_item.setTransform(transform)

                    scene.addItem(pix_item)
                    bounds = bounds.united(pix_item.sceneBoundingRect())

        if not scene.items() or bounds.isEmpty():
            return None

        # Render scene bounds into a thumbnail QPixmap
        target_rect = bounds
        aspect_ratio = target_rect.width() / target_rect.height() if target_rect.height() > 0 else 1.0

        w, h = size.width(), size.height()
        if w / h > aspect_ratio:
            render_w = int(h * aspect_ratio)
            render_h = h
        else:
            render_w = w
            render_h = int(w / aspect_ratio)

        result = QtGui.QPixmap(size)
        result.fill(QtCore.Qt.GlobalColor.transparent)

        painter = QtGui.QPainter(result)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QtGui.QPainter.RenderHint.SmoothPixmapTransform)

        target_canvas = QtCore.QRectF(
            (w - render_w) / 2, (h - render_h) / 2, render_w, render_h
        )
        scene.render(painter, target_canvas, target_rect)
        painter.end()

        scene.clear()
        return result
    except Exception:
        logger.exception(f'Failed to render .bee scene thumbnail for {filepath}')
        scene.clear()
        return None

