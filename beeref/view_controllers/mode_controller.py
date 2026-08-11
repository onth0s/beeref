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

logger = logging.getLogger(__name__)


class ModeMixin:
    """Mixin for BeeGraphicsView handling mode management (sample color, opacity, pan/zoom modes)."""

    def cancel_active_modes(self):
        self.scene.cancel_active_modes()
        self.cancel_sample_color_mode()
        self.cancel_opacity_mode()
        self.active_mode = None

    def cancel_sample_color_mode(self):
        logger.debug('Cancel sample color mode')
        self.active_mode = None
        self.viewport().unsetCursor()
        if hasattr(self, 'sample_color_widget'):
            self.sample_color_widget.hide()
            del self.sample_color_widget
        if self.scene.has_multi_selection():
            self.scene.multi_select_item.bring_to_front()

    def cancel_opacity_mode(self):
        if self.active_mode == self.OPACITY_MODE:
            logger.debug('Cancel opacity mode')
            self.active_mode = None
            self.viewport().unsetCursor()
            if hasattr(self, 'opacity_images') and self.opacity_images:
                for img, start_opacity in zip(self.opacity_images, self.opacity_start_values):
                    img.setOpacity(start_opacity)
                self.opacity_images = None
                self.opacity_start_values = None
