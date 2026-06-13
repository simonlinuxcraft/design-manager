# Design Manager

A GNOME appearance manager built with Python 3, GTK 4 and libadwaita. Change the
GTK theme, icon theme, cursor, system font and wallpaper from one place, with
live previews.

## Features

- Background: system wallpaper gallery, own images, fit mode (zoom, scaled, ...)
- Icons and GTK theme, with icon preview cards
- Cursor packs with real pointer previews (parsed from Xcursor files)
- System font picker
- Extensions and Backup are work in progress

Settings are applied live through `Gio.Settings` (dconf), no `gsettings`
subprocess calls.

## Run

Requires GTK 4 and libadwaita with PyGObject:

    sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-4.0 gir1.2-adw-1
    python3 main.py

To register the app icon and a desktop entry for local testing:

    data/dev-install.sh      # installs into ~/.local/share, reversible
    data/dev-uninstall.sh    # removes them again

## License

GPL-3.0-or-later. See [LICENSE](LICENSE).
