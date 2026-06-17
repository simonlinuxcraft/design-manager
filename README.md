# Design Manager for GNOME - 2026

A GNOME appearance manager built with Python 3, GTK 4 and libadwaita. Change the
GTK and shell theme, icons, cursor, fonts, accent colour, wallpaper and the lock
and login screen from one place, with live previews.

## Features

- Overview that summarizes the current look and jumps to any section
- Looks: curated complete looks and your own saved profiles, applied in one click
- Background: system and own wallpapers with fit mode, plus the lock screen and the GDM login background
- GTK theme and icon theme, with preview cards
- Cursor packs with real pointer previews (parsed from Xcursor files)
- Fonts: interface, document and monospace, with size and rendering options
- Shell theme with panel and accent preview cards
- Dock: Ubuntu Dock / Dash to Dock or Dash to Panel
- Extensions: enable, disable and open their preferences
- System: accent colour, window buttons, top bar and animations
- Backup: automatic restore points, file backup and shareable .dmlook packages

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

    sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-4.0 gir1.2-adw-1 gir1.2-gdkpixbuf-2.0 gir1.2-pango-1.0 gsettings-desktop-schemas
    python3 main.py

To register the app icon and a desktop entry for local testing:

    data/dev-install.sh      # installs into ~/.local/share, reversible
    data/dev-uninstall.sh    # removes them again

## Safety

The app runs as your normal user, and changes are additive and reversible.
Before every theme, cursor or shell change it takes a restore point, and the
main menu has a "Restore safe state" entry that puts the theme, icons, cursor
and shell theme back to known-good defaults (Adwaita).

One thing to be aware of: a broken third-party theme (invalid GTK or shell CSS)
can make your running session look wrong. It does not lock you out of the login
screen. Recover with a restore point, with "Restore safe state", or by logging
out and back in. The only system-wide change is the GDM login background, which
asks for the administrator password and takes effect after a reboot; it never
overwrites the original and restores itself if something goes wrong (see below).

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
