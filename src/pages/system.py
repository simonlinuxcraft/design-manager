"""Seite 'System'.

Sammelt kleinere Anpassungen, die sich nicht um Designs drehen, aber das
Erscheinungsbild prägen: die Akzentfarbe, die Knöpfe der Titelleiste, ein paar
Schalter für die obere Leiste (Uhr, Akku) und die Fenster-Animationen.

Alle Werte sind dconf-Schlüssel, jede Auswahl wirkt sofort.
"""

from gi.repository import Adw, Gtk


# Die Akzentfarben von GNOME (ab Version 47). Pro Eintrag: der interne Name, wie
# ihn dconf speichert, und ein deutsches Label für den Tooltip.
AKZENTE = [
    ("blue", "Blau"),
    ("teal", "Türkis"),
    ("green", "Grün"),
    ("yellow", "Gelb"),
    ("orange", "Orange"),
    ("red", "Rot"),
    ("pink", "Rosa"),
    ("purple", "Violett"),
    ("slate", "Schiefer"),
]

# Die drei Fensterknöpfe (minimize/maximize/close), nach denen button-layout
# durchsucht wird. "close" lassen wir immer stehen, sonst hätte ein Fenster
# keinen Schließen-Knopf mehr.
FENSTER_KNOEPFE = {"minimize", "maximize", "close"}


class SystemPage(Adw.NavigationPage):
    """Navigationsseite mit Akzentfarbe, Fensterknöpfen und Leisten-Schaltern."""

    def __init__(self, settings):
        super().__init__(title="System")
        self._settings = settings

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        box.set_margin_top(16)
        box.set_margin_bottom(16)
        box.set_margin_start(18)
        box.set_margin_end(18)

        box.append(self._feld_titel("Akzentfarbe"))
        box.append(self._akzent_bereich())
        box.append(self._fensterknoepfe_gruppe())
        box.append(self._leisten_gruppe())
        box.append(self._bewegung_gruppe())

        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        scroll.set_child(box)

        toolbar = Adw.ToolbarView()
        toolbar.add_top_bar(Adw.HeaderBar())
        toolbar.set_content(scroll)
        self.set_child(toolbar)

    # --- kleine Bausteine ---

    def _feld_titel(self, text):
        label = Gtk.Label(label=text, xalign=0)
        label.add_css_class("feld-titel")
        return label

    def _schalter(self, titel, untertitel, get_wert, set_wert):
        """Eine Adw.SwitchRow, die einen Boolean-Schlüssel spiegelt.

        set_active steht bewusst vor connect, sonst würde schon das Vorbelegen
        als Änderung zählen und den Schlüssel überschreiben.
        """
        zeile = Adw.SwitchRow(title=titel)
        if untertitel:
            zeile.set_subtitle(untertitel)
        zeile.set_active(get_wert())
        zeile.connect("notify::active",
                      lambda row, _p: set_wert(row.get_active()))
        return zeile

    # --- Akzentfarbe (Punkt: nur ab GNOME 47) ---

    def _akzent_bereich(self):
        """Farbreihe, oder ein Hinweis, falls die GNOME-Version zu alt ist."""
        if not self._settings.accent_verfuegbar():
            hinweis = Gtk.Label(
                label="Die Akzentfarbe lässt sich erst ab GNOME 47 einstellen.",
                xalign=0, wrap=True)
            hinweis.add_css_class("dim-label")
            return hinweis

        reihe = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        aktuell = self._settings.accent_color()

        erster = None
        for name, anzeige in AKZENTE:
            knopf = Gtk.ToggleButton()
            knopf.add_css_class("akzent-swatch")
            knopf.add_css_class("akzent-" + name)
            knopf.set_tooltip_text(anzeige)
            # Alle Knöpfe zu einer Gruppe -> es ist immer genau einer aktiv.
            if erster is None:
                erster = knopf
            else:
                knopf.set_group(erster)
            knopf.set_active(name == aktuell)
            knopf.connect("toggled", self._on_akzent, name)
            reihe.append(knopf)

        return reihe

    def _on_akzent(self, knopf, name):
        # Nur auf das Einschalten reagieren (das Ausschalten des vorherigen
        # Knopfes feuert ebenfalls, soll aber nichts setzen).
        if knopf.get_active():
            self._settings.set_accent_color(name)

    # --- Fensterknöpfe (Titelleiste) ---

    def _fensterknoepfe_gruppe(self):
        aktive, rechts = self._parse_layout(self._settings.button_layout())

        gruppe = Adw.PreferencesGroup(
            title="Fensterknöpfe",
            description="Welche Knöpfe die Titelleiste zeigt und auf welcher "
                        "Seite. Schließen bleibt immer sichtbar.")

        self._sw_minimieren = Adw.SwitchRow(title="Minimieren")
        self._sw_minimieren.set_active("minimize" in aktive)
        self._sw_minimieren.connect("notify::active", self._on_knoepfe)
        gruppe.add(self._sw_minimieren)

        self._sw_maximieren = Adw.SwitchRow(title="Maximieren")
        self._sw_maximieren.set_active("maximize" in aktive)
        self._sw_maximieren.connect("notify::active", self._on_knoepfe)
        gruppe.add(self._sw_maximieren)

        self._cr_seite = Adw.ComboRow(title="Anordnung")
        self._cr_seite.set_model(Gtk.StringList.new(["Rechts", "Links"]))
        self._cr_seite.set_selected(0 if rechts else 1)
        self._cr_seite.connect("notify::selected", self._on_knoepfe)
        gruppe.add(self._cr_seite)

        return gruppe

    def _parse_layout(self, layout):
        """Liest button-layout aus: welche Fensterknöpfe sind da, welche Seite.

        Format ist "links:rechts", z.B. "appmenu:minimize,maximize,close".
        Rückgabe: (Menge der aktiven Knöpfe, True wenn rechts).
        """
        links, _, rechts = layout.partition(":")
        links_knoepfe = [k for k in links.split(",") if k]
        rechts_knoepfe = [k for k in rechts.split(",") if k]

        if any(k in FENSTER_KNOEPFE for k in links_knoepfe):
            return set(links_knoepfe) & FENSTER_KNOEPFE, False
        return set(rechts_knoepfe) & FENSTER_KNOEPFE, True

    def _on_knoepfe(self, *_args):
        """Baut button-layout aus den drei Bedienelementen neu zusammen."""
        knoepfe = []
        if self._sw_minimieren.get_active():
            knoepfe.append("minimize")
        if self._sw_maximieren.get_active():
            knoepfe.append("maximize")
        knoepfe.append("close")
        gruppe = ",".join(knoepfe)

        rechts = self._cr_seite.get_selected() == 0
        layout = ":" + gruppe if rechts else gruppe + ":"
        self._settings.set_button_layout(layout)

    # --- Obere Leiste ---

    def _leisten_gruppe(self):
        gruppe = Adw.PreferencesGroup(
            title="Obere Leiste",
            description="Was die Uhr und der Systembereich anzeigen.")
        gruppe.add(self._schalter(
            "Sekunden in der Uhr", None,
            self._settings.clock_show_seconds,
            self._settings.set_clock_show_seconds))
        gruppe.add(self._schalter(
            "Wochentag anzeigen", None,
            self._settings.clock_show_weekday,
            self._settings.set_clock_show_weekday))
        gruppe.add(self._schalter(
            "Datum anzeigen", None,
            self._settings.clock_show_date,
            self._settings.set_clock_show_date))
        gruppe.add(self._schalter(
            "Akkustand in Prozent", None,
            self._settings.show_battery_percentage,
            self._settings.set_show_battery_percentage))
        return gruppe

    # --- Animationen ---

    def _bewegung_gruppe(self):
        gruppe = Adw.PreferencesGroup(title="Bewegung")
        gruppe.add(self._schalter(
            "Animationen", "Ein- und Ausblendeffekte der Oberfläche.",
            self._settings.enable_animations,
            self._settings.set_enable_animations))
        return gruppe
