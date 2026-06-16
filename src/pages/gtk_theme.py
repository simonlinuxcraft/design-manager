"""Seite 'GTK-Design'.

Das GTK-Design bestimmt das Aussehen der Programmfenster. Oben die Auswahl als
Dropdown mit einem 'Standard'-Knopf als Notausstieg, darunter eine Ablage zum
Installieren neuer GTK-Designs.

Wichtig: moderne GNOME-Apps (Nautilus, Einstellungen, Texteditor) sind
libadwaita-Apps und ignorieren benannte GTK-Designs. Die App spiegelt das
gewählte Design darum zusätzlich nach ~/.config/gtk-4.0, damit es auch dort
wirkt (siehe core/settings.py). Der 'Standard'-Knopf räumt diesen Spiegel
wieder weg.
"""

from gi.repository import Adw, Gtk

from src import compat
from src.core import restorepoint, theme_check, themes
from src.i18n import _
from src.widgets.dropzone import InstallDropzone


class GtkThemePage(compat.PageBase):
    """Navigationsseite für die Auswahl des GTK-Designs."""

    def __init__(self, settings):
        super().__init__(title=_("GTK Theme"))
        self._settings = settings

        toolbar = compat.toolbar_view(
            top_bars=[Adw.HeaderBar()], content=self._inhalt())
        self.set_child(toolbar)

    def _inhalt(self):
        """Scrollbarer Inhalt mit Auswahl und Installations-Ablage."""
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_margin_top(16)
        box.set_margin_bottom(16)
        box.set_margin_start(18)
        box.set_margin_end(18)

        untertitel = Gtk.Label(
            label=_("Determines how application windows look. Applied "
                    "immediately, also to modern apps like Files."),
            xalign=0, wrap=True)
        untertitel.add_css_class("dim-label")
        box.append(untertitel)

        box.append(self._feld_titel(_("GTK theme (windows & apps)")))
        box.append(self._gtk_design_zeile())

        box.append(self._feld_titel(_("Install a new GTK theme")))
        box.append(InstallDropzone(
            _("Drag a GTK theme (.tar.gz/.zip) here"), erwartet={"gtk"}))

        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        scroll.set_child(box)
        return scroll

    # --- kleine Bausteine ---

    def _feld_titel(self, text):
        label = Gtk.Label(label=text, xalign=0)
        label.add_css_class("feld-titel")
        return label

    def _gtk_design_zeile(self):
        """GTK-Design-Dropdown plus ein 'Standard'-Knopf als Notausstieg.

        Der Knopf setzt das GTK-Design auf Adwaita zurück und entfernt den
        libadwaita-Spiegel. Adwaita ist in GTK eingebaut und immer gültig, also
        der schnelle Weg zurück, falls ein gewähltes Design (z.B. mit ungültigem
        CSS) die Oberfläche unbrauchbar macht.
        """
        self._gtk_namen = themes.list_gtk_themes()
        if self._settings.SAFE_GTK_THEME not in self._gtk_namen:
            self._gtk_namen.insert(0, self._settings.SAFE_GTK_THEME)

        self._gtk_dropdown = Gtk.DropDown.new_from_strings(self._gtk_namen)
        self._gtk_dropdown.set_hexpand(True)
        aktuell = self._settings.gtk_theme()
        if aktuell in self._gtk_namen:
            self._gtk_dropdown.set_selected(self._gtk_namen.index(aktuell))
        # Erst nach dem Vorauswählen verbinden, sonst zählt die Vorauswahl schon
        # als Änderung. Handler-ID merken, damit das Nachziehen beim Reset nicht
        # erneut als Nutzerauswahl zählt.
        self._gtk_handler_id = self._gtk_dropdown.connect(
            "notify::selected", self._on_dropdown_changed,
            self._settings.set_gtk_theme)

        standard = Gtk.Button(label=_("Default"))
        standard.set_valign(Gtk.Align.CENTER)
        standard.set_tooltip_text(
            _("Reset the GTK theme to the safe default theme (Adwaita)"))
        standard.connect("clicked", self._on_gtk_reset)

        zeile = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        zeile.append(self._gtk_dropdown)
        zeile.append(standard)
        return zeile

    def _on_dropdown_changed(self, dropdown, _param, setter):
        eintrag = dropdown.get_selected_item()
        if eintrag is None:
            return
        name = eintrag.get_string()
        # Vor dem Aktivieren prüfen, ob die gtk.css wirklich da ist. Fehlt sie,
        # würde GNOME still auf Adwaita zurückfallen; lieber vorher fragen.
        ok, grund = theme_check.pruefe_gtk(name)
        if not ok:
            self._gtk_trotzdem_fragen(name, grund)
            return
        restorepoint.erstelle(
            self._settings, _("before GTK theme {name}").format(name=name))
        setter(name)

    def _gtk_trotzdem_fragen(self, name, grund):
        compat.alert(
            self,
            _("Activate theme anyway?"),
            '"{name}": {reason}'.format(name=name, reason=grund),
            [("abbrechen", _("Cancel"), ""),
             ("trotzdem", _("Activate anyway"), "destructive")],
            default="abbrechen", close="abbrechen",
            on_response=lambda antwort: self._on_gtk_trotzdem(antwort, name))

    def _on_gtk_trotzdem(self, antwort, name):
        if antwort == "trotzdem":
            restorepoint.erstelle(
                self._settings,
                _("before GTK theme {name}").format(name=name))
            self._settings.set_gtk_theme(name)
            return
        # Abbrechen: das Dropdown hat die Auswahl schon geändert, also auf das
        # tatsächlich aktive Design zurückziehen (ohne den Handler erneut
        # auszulösen).
        aktuell = self._settings.gtk_theme()
        if aktuell in self._gtk_namen:
            self._gtk_dropdown.handler_block(self._gtk_handler_id)
            self._gtk_dropdown.set_selected(self._gtk_namen.index(aktuell))
            self._gtk_dropdown.handler_unblock(self._gtk_handler_id)

    def _on_gtk_reset(self, _knopf):
        """Notausstieg: GTK-Design auf Adwaita zurück und Dropdown nachziehen."""
        self._settings.reset_gtk_theme()
        name = self._settings.SAFE_GTK_THEME
        if name in self._gtk_namen:
            # Handler blockieren: das Nachziehen ist Folge des Resets, keine
            # neue Nutzerauswahl, sonst würde set_gtk_theme doppelt feuern.
            self._gtk_dropdown.handler_block(self._gtk_handler_id)
            self._gtk_dropdown.set_selected(self._gtk_namen.index(name))
            self._gtk_dropdown.handler_unblock(self._gtk_handler_id)
