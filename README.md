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

## Where to get themes, icons and cursors

Design Manager switches between what is already installed; it does not download
themes itself. The main source for GNOME GTK themes, shell themes, icon packs,
cursors and wallpapers is [gnome-look.org](https://www.gnome-look.org/).

Install a downloaded set into one of these and it shows up in the app:

- GTK and shell themes: `~/.themes/` or `~/.local/share/themes/`
- Icons and cursors: `~/.icons/` or `~/.local/share/icons/`

Shell themes also need the User Themes extension enabled.

## Run

Requires GTK 4 and libadwaita with PyGObject:

    sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-4.0 gir1.2-adw-1
    python3 main.py

To register the app icon and a desktop entry for local testing:

    data/dev-install.sh      # installs into ~/.local/share, reversible
    data/dev-uninstall.sh    # removes them again

## Login screen recovery

The GDM login background never overwrites the system theme; it hooks in via
`update-alternatives` and a boot guard restores the stock greeter automatically
if a freshly set theme is not confirmed. If you ever need to force the stock
login screen back from a terminal (for example the app itself will not start),
run:

    sudo /usr/local/lib/design-manager/gdm-helper.sh reset

This removes the override and falls back to the original greeter. A system
upgrade of gnome-shell or the Yaru theme may also reset a confirmed login
background to stock on the next boot; just set it again.

## License

GPL-3.0-or-later. See [LICENSE](LICENSE).
