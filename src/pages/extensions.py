"""Seite 'Erweiterungen' (vorerst Platzhalter).

Hier kommt später die Auswahl des GNOME-Shell-Designs hin. Das funktioniert nur
mit der Erweiterung „User Themes“. Schon jetzt zeigen wir an, ob deren Schema
vorhanden ist, der Rest folgt in einem späteren Schritt.
"""

from gi.repository import Adw

from src.core.settings import schema_vorhanden


class ExtensionsPage(Adw.NavigationPage):
    """Platzhalter-Seite mit Status der Erweiterung „User Themes“."""

    def __init__(self, settings):
        super().__init__(title="Erweiterungen")

        if schema_vorhanden("org.gnome.shell.extensions.user-theme"):
            beschreibung = (
                "Die Erweiterung „User Themes“ ist aktiv. Die Auswahl des "
                "Shell-Designs folgt hier in Kürze."
            )
        else:
            beschreibung = (
                "Für Shell-Designs wird die Erweiterung „User Themes“ benötigt. "
                "Sie ist derzeit nicht aktiv."
            )

        status = Adw.StatusPage(
            title="In Arbeit",
            description=beschreibung,
            icon_name="application-x-addon-symbolic",
        )

        toolbar = Adw.ToolbarView()
        toolbar.add_top_bar(Adw.HeaderBar())
        toolbar.set_content(status)
        self.set_child(toolbar)
