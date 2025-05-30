# Copyright 2024 - 2025, zalesyc and the budgie-media-player-applet contributors
# SPDX-License-Identifier: GPL-3.0-or-later

from EnumsStructs import (
    AlbumCoverType,
    AlbumCoverData,
    PanelLengthMode,
    PanelClickAction,
)
from mprisWrapper import MprisWrapper
from dataclasses import dataclass
from typing import Optional, Callable
from math import ceil, floor
import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gio", "2.0")
gi.require_version("GdkPixbuf", "2.0")
gi.require_version("Pango", "1.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gtk, GdkPixbuf, Gio
from gi.repository.Pango import EllipsizeMode
from gi.repository.Gdk import EventButton


@dataclass
class MarginElement:
    widget: Gtk.Bin
    margin: int


class PanelControlView(Gtk.Box):
    def __init__(
        self,
        dbus_player: MprisWrapper,
        title: str,
        artist: list[str],
        album_cover: Optional[AlbumCoverData],
        playing: bool,
        can_play_or_pause: bool,
        can_go_previous: bool,
        can_go_next: bool,
        open_popover_func: Callable[[], None],
        orientation: Gtk.Orientation,
        panel_size: int,
        settings: Gio.Settings,
    ):
        Gtk.Box.__init__(self, orientation=orientation)
        self.dbus_player: MprisWrapper = dbus_player
        self.album_cover_size: int = panel_size
        self.open_popover_func = open_popover_func
        self.orientation: Gtk.Orientation = orientation
        self.settings: Gio.Settings = settings
        self.separator_text: str = ""
        self.available_elements: dict[str, Gtk.Widget] = {}
        self.element_margins: list[MarginElement] = []
        self.element_order: list[str] = []
        self.click_actions: dict[int, PanelClickAction] = {}

        self.album_cover: Gtk.Image = Gtk.Image.new_from_icon_name(
            "emblem-music-symbolic", Gtk.IconSize.MENU
        )
        self.song_name_label: Gtk.Label = Gtk.Label()
        self.song_author_label: Gtk.Label = Gtk.Label()
        self.song_separator: Gtk.Label = Gtk.Label()
        self.play_pause_button: Gtk.Button = Gtk.Button()
        self.go_previous_button: Gtk.Button = Gtk.Button()
        self.go_next_button: Gtk.Button = Gtk.Button()

        # albumCover
        album_cover_event_box = Gtk.EventBox()
        album_cover_event_box.add(self.album_cover)
        album_cover_event_box.connect("button-press-event", self._song_clicked)
        self.available_elements.update({"album_cover": album_cover_event_box})
        self.element_margins.append(MarginElement(album_cover_event_box, 5))
        if (album_cover is not None) and album_cover.cover_type != AlbumCoverType.Null:
            self.set_album_cover(album_cover)

        label_angle = 0 if self.orientation == Gtk.Orientation.HORIZONTAL else 270

        # song_name
        self.song_name_label.set_angle(label_angle)
        song_name_event_box = Gtk.EventBox()
        song_name_event_box.add(self.song_name_label)
        song_name_event_box.connect("button-press-event", self._song_clicked)
        self.available_elements.update({"song_name": song_name_event_box})
        self.element_margins.append(MarginElement(song_name_event_box, 4))

        # song_author
        self.song_author_label.set_angle(label_angle)
        song_author_event_box = Gtk.EventBox()
        song_author_event_box.add(self.song_author_label)
        song_author_event_box.connect("button-press-event", self._song_clicked)
        self.available_elements.update({"song_author": song_author_event_box})
        self.element_margins.append(MarginElement(song_author_event_box, 4))

        # song_separator
        self.song_name_label.set_angle(label_angle)
        song_separator_event_box = Gtk.EventBox()
        song_separator_event_box.add(self.song_separator)
        song_separator_event_box.connect("button-press-event", self._song_clicked)
        self._set_separator_text(settings.get_string("separator-text"))
        self.available_elements.update({"song_separator": song_separator_event_box})
        self.element_margins.append(MarginElement(song_separator_event_box, 4))

        # play pause button
        self.play_pause_button.set_image(
            Gtk.Image.new_from_icon_name(
                (
                    "media-playback-pause-symbolic"
                    if playing
                    else "media-playback-start-symbolic"
                ),
                Gtk.IconSize.MENU,
            )
        )
        self.play_pause_button.set_relief(Gtk.ReliefStyle.NONE)
        self.play_pause_button.set_sensitive(can_play_or_pause)
        self.play_pause_button.connect("button-press-event", self._play_paused_clicked)
        self.play_pause_button.set_tooltip_text("Play / Pause")
        self.available_elements.update({"play_pause_button": self.play_pause_button})

        # backward_button
        self.go_previous_button.set_image(
            Gtk.Image.new_from_icon_name(
                "media-skip-backward-symbolic", Gtk.IconSize.MENU
            )
        )
        self.go_previous_button.set_relief(Gtk.ReliefStyle.NONE)
        self.go_previous_button.set_sensitive(can_go_previous)
        self.go_previous_button.connect("button-press-event", self._backward_clicked)
        self.go_previous_button.set_tooltip_text("Go to the previous song / media")
        self.available_elements.update({"backward_button": self.go_previous_button})

        # forward_button
        self.go_next_button.set_image(
            Gtk.Image.new_from_icon_name(
                "media-skip-forward-symbolic", Gtk.IconSize.MENU
            )
        )
        self.go_next_button.set_relief(Gtk.ReliefStyle.NONE)
        self.go_next_button.set_sensitive(can_go_next)
        self.go_next_button.connect("button-press-event", self._forward_clicked)
        self.go_next_button.set_tooltip_text("Go to the next song / media")
        self.available_elements.update({"forward_button": self.go_next_button})

        self.settings.connect("changed", self._settings_changed)

        self._set_length()
        self._set_element_order(
            settings.get_strv("element-order"), remove_previous=False
        )
        self._set_element_margins()
        self.click_actions = settings.get_value("panel-click-action").unpack()
        self._set_song_label(name=title, author=artist)
        self.show_all()

    def set_orientation(self, _):
        raise Exception("Use orientation_changed instead")

    def orientation_changed(
        self, new_orientation: Gtk.Orientation, album_cover_data: AlbumCoverData
    ) -> None:
        self.orientation = new_orientation
        angle = 0 if new_orientation == Gtk.Orientation.HORIZONTAL else 270
        self.song_name_label.set_angle(angle)
        self.song_author_label.set_angle(angle)
        self.song_separator.set_angle(angle)
        super().set_orientation(new_orientation)
        self.set_album_cover(album_cover_data)
        self._set_element_margins()

    def panel_size_changed(
        self, new_size: int, album_cover_data: AlbumCoverData
    ) -> None:
        self.album_cover_size = new_size
        self.set_album_cover(album_cover_data)

    def set_playing(self, playing: bool) -> None:
        self.play_pause_button.set_image(
            Gtk.Image.new_from_icon_name(
                (
                    "media-playback-pause-symbolic"
                    if playing
                    else "media-playback-start-symbolic"
                ),
                Gtk.IconSize.MENU,
            )
        )

    def set_metadata(self, artist: list[str], title: str) -> None:
        self._set_song_label(artist, title)

    def set_can_play_or_pause(self, can_play_or_pause: bool) -> None:
        self.play_pause_button.set_sensitive(can_play_or_pause)

    def set_can_go_previous(self, can_go_previous: bool) -> None:
        self.go_previous_button.set_sensitive(can_go_previous)

    def set_can_go_next(self, can_go_next: bool) -> None:
        self.go_next_button.set_sensitive(can_go_next)

    def set_album_cover(self, data: AlbumCoverData) -> None:
        if data.cover_type == AlbumCoverType.Pixbuf:
            if self.orientation == Gtk.Orientation.HORIZONTAL:
                resized_pixbuf = data.song_cover_pixbuf.scale_simple(
                    int(
                        (self.album_cover_size / data.song_cover_pixbuf.get_height())
                        * data.song_cover_pixbuf.get_width()
                    ),
                    self.album_cover_size,
                    GdkPixbuf.InterpType.BILINEAR,
                )
            else:
                resized_pixbuf = data.song_cover_pixbuf.scale_simple(
                    self.album_cover_size,
                    int(
                        (self.album_cover_size / data.song_cover_pixbuf.get_width())
                        * data.song_cover_pixbuf.get_height()
                    ),
                    GdkPixbuf.InterpType.BILINEAR,
                )
            self.album_cover.set_from_pixbuf(resized_pixbuf)

        elif data.cover_type == AlbumCoverType.Gicon:
            icon_info = Gtk.IconTheme.get_default().lookup_by_gicon(
                data.song_cover_other,
                min(Gtk.IconSize.lookup(Gtk.IconSize.DND)[2], self.album_cover_size),
                Gtk.IconLookupFlags(Gtk.IconLookupFlags.FORCE_SIZE),
            )
            if icon_info is not None:
                pixbuf = icon_info.load_icon()
                self.album_cover.set_from_pixbuf(pixbuf)

        elif data.cover_type == AlbumCoverType.IconName:
            pixbuf = Gtk.IconTheme.get_default().load_icon(
                data.song_cover_other,
                min(Gtk.IconSize.lookup(Gtk.IconSize.DND)[2], self.album_cover_size),
                Gtk.IconLookupFlags(Gtk.IconLookupFlags.FORCE_SIZE),
            )
            if pixbuf is not None:
                self.album_cover.set_from_pixbuf(pixbuf)

    def _play_paused_clicked(self, *_) -> None:
        self.dbus_player.call_player_method("PlayPause")

    def _forward_clicked(self, *_) -> None:
        self.dbus_player.call_player_method("Next")

    def _backward_clicked(self, *_) -> None:
        self.dbus_player.call_player_method("Previous")

    def _song_clicked(self, _, event: EventButton) -> None:
        action = self.click_actions.get(event.button, PanelClickAction.open_popover)
        if action == PanelClickAction.next:
            self._forward_clicked()
        elif action == PanelClickAction.previous:
            self._backward_clicked()
        elif action == PanelClickAction.play_pause:
            self._play_paused_clicked()
        else:
            self.open_popover_func()

    def _set_separator_text(
        self, new_text: str, override_set_text: bool = True
    ) -> None:
        if override_set_text:
            self.separator_text = new_text
        self.song_separator.set_label(new_text)

    def _set_element_order(
        self, order: list[str], remove_previous: bool = True
    ) -> None:
        self.element_order = order
        if remove_previous:
            self.foreach(self.remove)

        for element_name in self.element_order:
            widget = self.available_elements.get(element_name)
            if widget is None:
                print(
                    f"budgie-media-player-applet: '{element_name}' "
                    "not in available elements - probably wrong settings -> skipping"
                )
                continue
            self.pack_start(widget, False, False, 0)

        self.show_all()

    def _set_song_label(self, author: Optional[list[str]], name: Optional[str]) -> None:
        s_author = self._get_author(author)
        s_name = self._get_name(name)

        if s_author and s_name:
            self.song_author_label.set_label(s_author)
            self.song_name_label.set_label(s_name)
            self._set_separator_text(self.separator_text)
            return
        if s_author and not s_name:
            self.song_author_label.set_label(s_author)
            self.song_name_label.set_label("Unknown")
            self._set_separator_text(self.separator_text)
            return
        if not s_author and s_name:
            self.song_name_label.set_label(s_name)
            if "song_name" in self.element_order:
                self.song_author_label.set_label("")
                self._set_separator_text("", override_set_text=False)
            else:
                self.song_author_label.set_label("Unknown")
                self._set_separator_text(self.separator_text)
            return

        if "song_name" in self.element_order and "song_author" in self.element_order:
            self.song_author_label.set_label("")
            self.song_name_label.set_label("Unknown")
            self._set_separator_text("", override_set_text=False)
            return

        self.song_author_label.set_label("Unknown")
        self.song_name_label.set_label("Unknown")
        self._set_separator_text("", override_set_text=False)

    @staticmethod
    def _get_name(title: Optional[str]) -> str:
        """This func is only used in _set_song_label"""
        if title is None:
            return ""
        if not title:
            return ""
        if title.isspace():
            return ""
        return title

    @staticmethod
    def _get_author(author: Optional[list[str]]) -> str:
        """This func is only used in _set_song_label"""
        if author is None:
            return ""
        if not author:
            return ""
        j_author = "".join(author)
        if not j_author:
            return ""
        if j_author.isspace():
            return ""
        return ", ".join(author)

    def _settings_changed(self, settings: Gio.Settings, key: str) -> None:
        if key == "separator-text":
            self.song_separator.set_label(settings.get_string(key))
        elif key == "element-order":
            self._set_element_order(settings.get_strv(key))
        elif key in {
            "panel-length-mode",
            "media-title-max-length",
            "author-name-max-length",
        }:
            self._set_length()
        elif key == "panel-click-action":
            self.click_actions = settings.get_value(key).unpack()

    def _set_length(self) -> None:
        panel_len_mode = self.settings.get_uint("panel-length-mode")
        if panel_len_mode in {PanelLengthMode.Variable, PanelLengthMode.Fixed}:
            self.song_name_label.set_ellipsize(EllipsizeMode.END)
            self.song_author_label.set_ellipsize(EllipsizeMode.END)
        else:
            self.song_name_label.set_ellipsize(EllipsizeMode.NONE)
            self.song_author_label.set_ellipsize(EllipsizeMode.NONE)

        if panel_len_mode == PanelLengthMode.Variable:
            self.song_name_label.set_max_width_chars(
                max(-1, self.settings.get_int("media-title-max-length"))
            )
            self.song_author_label.set_max_width_chars(
                max(-1, self.settings.get_int("author-name-max-length"))
            )
        else:
            self.song_name_label.set_max_width_chars(-1)
            self.song_author_label.set_max_width_chars(-1)

    def _set_element_margins(self):
        # floor and ceil is used because margins can only be integers and if the spacing is odd
        # this will distribute it around the element such that one is one px larger than the other
        # Also the margin has to be set on a child because gtk doesnt accept mouse events on margins
        for element in self.element_margins:
            child = element.widget.get_child()
            if child is None:
                continue

            if self.orientation == Gtk.Orientation.HORIZONTAL:
                child.set_margin_start(ceil(element.margin / 2))
                child.set_margin_end(floor(element.margin / 2))
            else:
                child.set_margin_top(ceil(element.margin / 2))
                child.set_margin_bottom(floor(element.margin / 2))
