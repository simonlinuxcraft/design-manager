"""Kompatibilitaetsschicht fuer aeltere GTK4/libadwaita-Staende.

Die App nutzt von Haus aus libadwaita-1.4/1.5- und GTK-4.8/4.10/4.12-APIs. Auf
Ubuntu 22.04 (libadwaita 1.1, GTK 4.6) fehlen die, die App wuerde sonst schon
beim Import abstuerzen. Dieses Modul liefert pro Baustein zur Importzeit entweder
die moderne API (wenn vorhanden) oder einen Ersatz, der ausschliesslich auf
GTK-4.0/4.6- und libadwaita-1.0/1.1-APIs beruht.

Zwei Sorten: Drop-in-Klassen (Aufrufstelle nutzt compat.X statt Adw.X) und
Helfer-Funktionen (Aufrufstelle ruft eine Funktion, weil die alten und neuen
APIs zu unterschiedlich sind).

Zum Testen des Fallback-Pfads auf einem neuen System: DM_COMPAT_FALLBACK=1
erzwingt ueberall den alten Zweig.
"""

import os

from gi.repository import Adw, Gio, GLib, GObject, Gtk, Pango

_FORCE = os.environ.get("DM_COMPAT_FALLBACK") == "1"


def _hat(obj, name):
    """True, wenn das Attribut da ist und der Fallback nicht erzwungen wurde."""
    return (not _FORCE) and hasattr(obj, name)


# --- Picture: Cover-Fuellung (Gtk.ContentFit ist 4.8) -----------------------

def set_cover(picture):
    """Bild formatfuellend (Cover) zeigen. Vor 4.8 nur Seitenverhaeltnis halten."""
    if _hat(Gtk, "ContentFit"):
        picture.set_content_fit(Gtk.ContentFit.COVER)
    else:
        picture.set_keep_aspect_ratio(True)


# --- FlowBox leeren (Gtk.FlowBox.remove_all ist 4.12) -----------------------

def flowbox_clear(box):
    """Alle Kinder einer FlowBox entfernen, auch vor GTK 4.12."""
    if _hat(box, "remove_all"):
        box.remove_all()
        return
    kind = box.get_first_child()
    while kind is not None:
        box.remove(kind)
        kind = box.get_first_child()


# --- ToolbarView (Adw.ToolbarView ist 1.4) ----------------------------------

def toolbar_view(top_bars=(), content=None, bottom_bars=()):
    """Kopfleiste(n) oben, Inhalt, optional Leisten unten. Fallback: vert. Box."""
    if _hat(Adw, "ToolbarView"):
        view = Adw.ToolbarView()
        for bar in top_bars:
            view.add_top_bar(bar)
        if content is not None:
            view.set_content(content)
        for bar in bottom_bars:
            view.add_bottom_bar(bar)
        return view

    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    for bar in top_bars:
        box.append(bar)
    if content is not None:
        content.set_vexpand(True)
        box.append(content)
    for bar in bottom_bars:
        box.append(bar)
    return box


# --- Seiten-Basisklasse (Adw.NavigationPage ist 1.4) ------------------------

if _hat(Adw, "NavigationPage"):
    PageBase = Adw.NavigationPage
else:
    class PageBase(Adw.Bin):
        """Ersatz fuer Adw.NavigationPage auf Basis von Adw.Bin (1.0).

        Schluckt das title-Argument (Bin kennt es nicht) und bietet die paar
        NavigationPage-Methoden, die der Rest des Codes erwartet.
        """

        __gtype_name__ = "DMPageBase"

        def __init__(self, title=None, **kwargs):
            super().__init__(**kwargs)
            self._dm_title = title or ""

        def set_title(self, title):
            self._dm_title = title

        def get_title(self):
            return self._dm_title


# --- Split-Layout (Adw.NavigationSplitView ist 1.4) -------------------------

if _hat(Adw, "NavigationSplitView"):
    def make_split():
        return Adw.NavigationSplitView()
else:
    class _FallbackSplit(Gtk.Box):
        """Zweispaltiges Layout aus einer waagerechten Box.

        Bildet die paar NavigationSplitView-Methoden nach, die window.py nutzt.
        set_content tauscht das rechte Kind aus und wahrt die Identitaet, damit
        der is-Vergleich in window.py weiter stimmt.
        """

        __gtype_name__ = "DMFallbackSplit"

        def __init__(self):
            super().__init__(orientation=Gtk.Orientation.HORIZONTAL)
            self._sidebar = None
            self._content = None
            self._breite = 270
            self._sep = Gtk.Separator(orientation=Gtk.Orientation.VERTICAL)

        def set_min_sidebar_width(self, breite):
            self._breite = int(breite)
            if self._sidebar is not None:
                self._sidebar.set_size_request(self._breite, -1)

        def set_max_sidebar_width(self, _breite):
            pass

        def set_sidebar(self, widget):
            if self._sidebar is not None:
                self.remove(self._sidebar)
            self._sidebar = widget
            widget.set_size_request(self._breite, -1)
            self.prepend(widget)
            if self._sep.get_parent() is None:
                self.insert_child_after(self._sep, widget)

        def set_content(self, widget):
            if self._content is not None:
                self.remove(self._content)
            self._content = widget
            widget.set_hexpand(True)
            self.append(widget)

        def get_content(self):
            return self._content

    def make_split():
        return _FallbackSplit()


# --- SwitchRow (Adw.SwitchRow ist 1.4) --------------------------------------

if _hat(Adw, "SwitchRow"):
    SwitchRow = Adw.SwitchRow
else:
    class SwitchRow(Adw.ActionRow):
        """Adw.ActionRow mit Gtk.Switch, API-gleich zu Adw.SwitchRow.

        get_active/set_active und das active-Property leiten direkt an den
        Switch weiter (kein Schattenwert). notify::active feuert genau einmal
        pro Aenderung, damit handler_block_by_func sauber greift.
        """

        __gtype_name__ = "DMSwitchRow"

        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self._switch = Gtk.Switch(valign=Gtk.Align.CENTER)
            self.add_suffix(self._switch)
            self.set_activatable_widget(self._switch)
            self._switch.connect(
                "notify::active", lambda *_: self.notify("active"))

        @GObject.Property(type=bool, default=False)
        def active(self):
            return self._switch.get_active()

        @active.setter
        def active(self, wert):
            self._switch.set_active(wert)

        def get_active(self):
            return self._switch.get_active()

        def set_active(self, wert):
            self._switch.set_active(wert)

        def set_sensitive(self, wert):
            Adw.ActionRow.set_sensitive(self, wert)
            self._switch.set_sensitive(wert)


# --- SpinRow (Adw.SpinRow ist 1.4) ------------------------------------------

if _hat(Adw, "SpinRow"):
    SpinRow = Adw.SpinRow
else:
    class SpinRow(Adw.ActionRow):
        """Adw.ActionRow mit Gtk.SpinButton, API-gleich zu Adw.SpinRow."""

        __gtype_name__ = "DMSpinRow"

        def __init__(self, lo=0.0, hi=100.0, step=1.0, **kwargs):
            super().__init__(**kwargs)
            self._spin = Gtk.SpinButton.new_with_range(lo, hi, step)
            self._spin.set_valign(Gtk.Align.CENTER)
            self.add_suffix(self._spin)
            self.set_activatable_widget(self._spin)
            self._spin.connect(
                "value-changed", lambda *_: self.notify("value"))

        @classmethod
        def new_with_range(cls, lo, hi, step):
            return cls(lo, hi, step)

        @GObject.Property(type=float, default=0.0)
        def value(self):
            return self._spin.get_value()

        @value.setter
        def value(self, wert):
            self._spin.set_value(wert)

        def get_value(self):
            return self._spin.get_value()

        def set_value(self, wert):
            self._spin.set_value(wert)

        def set_digits(self, ziffern):
            self._spin.set_digits(ziffern)


# --- EntryRow (Adw.EntryRow ist 1.2) ----------------------------------------

if _hat(Adw, "EntryRow"):
    EntryRow = Adw.EntryRow
else:
    class EntryRow(Adw.ActionRow):
        """Adw.ActionRow mit Gtk.Entry und apply-Signal wie Adw.EntryRow."""

        __gtype_name__ = "DMEntryRow"
        __gsignals__ = {
            "apply": (GObject.SignalFlags.RUN_LAST, None, ()),
        }

        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self._entry = Gtk.Entry(valign=Gtk.Align.CENTER, hexpand=True)
            self.add_suffix(self._entry)
            self.set_activatable_widget(self._entry)

            self._apply = Gtk.Button(
                icon_name="emblem-ok-symbolic", valign=Gtk.Align.CENTER)
            self._apply.add_css_class("flat")
            self._apply.set_visible(False)
            self._apply.connect("clicked", lambda *_: self.emit("apply"))
            self.add_suffix(self._apply)

            self._entry.connect("activate", lambda *_: self.emit("apply"))

        def set_show_apply_button(self, zeigen):
            self._apply.set_visible(bool(zeigen))

        def get_text(self):
            return self._entry.get_text()

        def set_text(self, text):
            self._entry.set_text(text)


# --- Banner (Adw.Banner ist 1.3) --------------------------------------------

if _hat(Adw, "Banner"):
    Banner = Adw.Banner
else:
    class Banner(Gtk.Revealer):
        """Einklappbarer Hinweis mit Knopf, API-gleich zu Adw.Banner."""

        __gtype_name__ = "DMBanner"
        __gsignals__ = {
            "button-clicked": (GObject.SignalFlags.RUN_LAST, None, ()),
        }

        def __init__(self):
            super().__init__()
            self.set_reveal_child(False)

            box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
            box.add_css_class("dm-banner")
            box.set_margin_top(8)
            box.set_margin_bottom(8)
            box.set_margin_start(12)
            box.set_margin_end(12)

            self._label = Gtk.Label(xalign=0, hexpand=True, wrap=True)
            self._button = Gtk.Button()
            self._button.set_valign(Gtk.Align.CENTER)
            self._button.set_visible(False)
            self._button.connect(
                "clicked", lambda *_: self.emit("button-clicked"))

            box.append(self._label)
            box.append(self._button)
            self.set_child(box)

        def set_revealed(self, wert):
            self.set_reveal_child(wert)

        def set_title(self, text):
            self._label.set_label(text)

        def set_button_label(self, text):
            self._button.set_label(text or "")
            self._button.set_visible(bool(text))


# --- AlertDialog (Adw.AlertDialog ist 1.5) ----------------------------------

def alert(parent, heading, body, responses, default=None, close=None,
          on_response=None):
    """Bestaetigungsdialog. responses: Liste (id, label, stil).

    stil ist "", "suggested" oder "destructive". on_response bekommt die id der
    gewaehlten Antwort. Fallback nutzt Gtk.MessageDialog (4.0).
    """
    if _hat(Adw, "AlertDialog"):
        dialog = Adw.AlertDialog(heading=heading, body=body)
        for rid, label, stil in responses:
            dialog.add_response(rid, label)
            if stil == "suggested":
                dialog.set_response_appearance(
                    rid, Adw.ResponseAppearance.SUGGESTED)
            elif stil == "destructive":
                dialog.set_response_appearance(
                    rid, Adw.ResponseAppearance.DESTRUCTIVE)
        if default:
            dialog.set_default_response(default)
        if close:
            dialog.set_close_response(close)
        if on_response:
            dialog.connect("response", lambda _d, rid: on_response(rid))
        dialog.present(parent)
        return

    dialog = Gtk.MessageDialog(
        transient_for=parent, modal=True,
        message_type=Gtk.MessageType.QUESTION,
        text=heading, secondary_text=body)
    nach_id = {}
    for i, (rid, label, stil) in enumerate(responses):
        dialog.add_button(label, i)
        nach_id[i] = rid
        knopf = dialog.get_widget_for_response(i)
        if knopf is not None:
            if stil == "suggested":
                knopf.add_css_class("suggested-action")
            elif stil == "destructive":
                knopf.add_css_class("destructive-action")
    if default is not None:
        for i, rid in nach_id.items():
            if rid == default:
                dialog.set_default_response(i)
                break

    def _antwort(dlg, code):
        rid = nach_id.get(code, close)
        dlg.destroy()
        if on_response and rid is not None:
            on_response(rid)

    dialog.connect("response", _antwort)
    dialog.present()


# --- AboutDialog (Adw.AboutDialog ist 1.5) ----------------------------------

def show_about(parent, application_name, application_icon, version,
               developer_name, comments, license_type, copyright):
    """Ueber-Dialog. Fallback nutzt Gtk.AboutDialog (4.0)."""
    if _hat(Adw, "AboutDialog"):
        dialog = Adw.AboutDialog(
            application_name=application_name,
            application_icon=application_icon,
            version=version, developer_name=developer_name,
            comments=comments, license_type=license_type, copyright=copyright)
        dialog.present(parent)
        return

    dialog = Gtk.AboutDialog(
        transient_for=parent, modal=True,
        program_name=application_name, logo_icon_name=application_icon,
        version=version, authors=[developer_name], comments=comments,
        license_type=license_type, copyright=copyright)
    dialog.present()


# --- Datei-Dialoge (Gtk.FileDialog ist 4.10) --------------------------------

# Gtk.FileChooserNative ist kein Widget und wird ohne harte Referenz sofort
# eingesammelt. Bis das response-Signal kommt, hier festhalten.
_offene_dialoge = set()


def _native_dialog(parent, title, aktion, initial_name, filters, on_path):
    native = Gtk.FileChooserNative.new(title, parent, aktion, None, None)
    native.set_modal(True)
    if initial_name:
        native.set_current_name(initial_name)
    for f in filters or ():
        native.add_filter(f)
    _offene_dialoge.add(native)

    def _antwort(dlg, code):
        _offene_dialoge.discard(dlg)
        pfad = None
        if code == Gtk.ResponseType.ACCEPT:
            datei = dlg.get_file()
            pfad = datei.get_path() if datei is not None else None
        dlg.destroy()
        on_path(pfad)

    native.connect("response", _antwort)
    native.show()


def open_file(parent, title, filters, on_path):
    """Datei oeffnen. on_path bekommt den Pfad oder None (Abbruch)."""
    if _hat(Gtk, "FileDialog"):
        dialog = Gtk.FileDialog()
        dialog.set_title(title)
        if filters:
            store = Gio.ListStore.new(Gtk.FileFilter)
            for f in filters:
                store.append(f)
            dialog.set_filters(store)

        def _fertig(dlg, ergebnis):
            try:
                datei = dlg.open_finish(ergebnis)
            except GLib.Error:
                return
            on_path(datei.get_path() if datei is not None else None)

        dialog.open(parent, None, _fertig)
        return

    _native_dialog(parent, title, Gtk.FileChooserAction.OPEN, None,
                   filters, on_path)


def save_file(parent, title, initial_name, filters, on_path):
    """Datei speichern. on_path bekommt den Pfad oder None (Abbruch)."""
    if _hat(Gtk, "FileDialog"):
        dialog = Gtk.FileDialog()
        dialog.set_title(title)
        if initial_name:
            dialog.set_initial_name(initial_name)
        if filters:
            store = Gio.ListStore.new(Gtk.FileFilter)
            for f in filters:
                store.append(f)
            dialog.set_filters(store)

        def _fertig(dlg, ergebnis):
            try:
                datei = dlg.save_finish(ergebnis)
            except GLib.Error:
                return
            on_path(datei.get_path() if datei is not None else None)

        dialog.save(parent, None, _fertig)
        return

    _native_dialog(parent, title, Gtk.FileChooserAction.SAVE, initial_name,
                   filters, on_path)


# --- Schrift-Knopf (Gtk.FontDialogButton ist 4.10) --------------------------

def font_button(initial_desc, on_changed):
    """Schrift-Auswahlknopf. initial_desc als String, on_changed(string)."""
    def _melde(knopf):
        desc = knopf.get_font_desc()
        if desc is not None:
            on_changed(desc.to_string())

    if _hat(Gtk, "FontDialogButton"):
        knopf = Gtk.FontDialogButton.new(Gtk.FontDialog())
        if initial_desc:
            knopf.set_font_desc(Pango.FontDescription.from_string(initial_desc))
        knopf.connect("notify::font-desc", lambda b, _p: _melde(b))
        return knopf

    knopf = Gtk.FontButton()
    if initial_desc:
        knopf.set_font_desc(Pango.FontDescription.from_string(initial_desc))
    knopf.connect("font-set", _melde)
    return knopf


# --- Dialog-Fenster (Adw.Dialog ist 1.5) ------------------------------------

_DIALOG_MODERN = _hat(Adw, "Dialog")
DialogBase = Adw.Dialog if _DIALOG_MODERN else Adw.Window


def dialog_setup(dialog, title, width, height):
    """Titel und Groesse setzen, je nach Basisklasse."""
    dialog.set_title(title)
    if _DIALOG_MODERN:
        dialog.set_content_width(width)
        dialog.set_content_height(height)
    else:
        dialog.set_default_size(width, height)


def dialog_set_content(dialog, child):
    """Inhalt setzen (Adw.Dialog: set_child, Adw.Window: set_content)."""
    if _DIALOG_MODERN:
        dialog.set_child(child)
    else:
        dialog.set_content(child)


def dialog_present(dialog, parent):
    """Dialog modal zum Elternfenster zeigen."""
    if _DIALOG_MODERN:
        dialog.present(parent)
    else:
        dialog.set_transient_for(parent)
        dialog.set_modal(True)
        dialog.present()
