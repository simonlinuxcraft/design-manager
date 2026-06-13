"""Seite 'Sicherung' (vorerst Platzhalter).

Hier kommt später das Sichern und Wiederherstellen der Einstellungen hin
(Export/Import). Vorerst nur ein Hinweis.
"""

from gi.repository import Adw


class BackupPage(Adw.NavigationPage):
    """Platzhalter-Seite für Sicherung und Wiederherstellung."""

    def __init__(self, settings):
        super().__init__(title="Sicherung")

        status = Adw.StatusPage(
            title="In Arbeit",
            description="Hier kannst du bald deine Einstellungen sichern und "
                        "wiederherstellen.",
            icon_name="document-save-symbolic",
        )

        toolbar = Adw.ToolbarView()
        toolbar.add_top_bar(Adw.HeaderBar())
        toolbar.set_content(status)
        self.set_child(toolbar)
