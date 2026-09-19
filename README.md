# Design Manager for GNOME - 2026

A GNOME appearance manager built with Python 3, GTK 4 and libadwaita. Change the
GTK and shell theme, icons, cursor, fonts, accent colour, wallpaper and the lock
and login screen from one place, with live previews.

## Features

- Overview that summarizes the current look and jumps to any section
- Looks: curated complete looks and your own saved profiles, applied in one click
- Background: own and system wallpapers in tabs, per-monitor images, fit mode, plus the lock screen and the GDM login background
- Drag and drop anywhere into the window to install themes, icons, cursors, fonts, wallpapers or a .dmlook
- Install straight from a gnome-look.org link (button "From gnome-look.org…" or drag the link) and get update checks for it
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

The main source for GNOME GTK themes, shell themes, icon packs, cursors and
wallpapers is [gnome-look.org](https://www.gnome-look.org/).

Drop the downloaded file into the app window. Or skip the download: copy the
address of the gnome-look page (e.g. `https://www.gnome-look.org/p/1013030`),
click "From gnome-look.org…" next to "Choose file…" and paste it. A link copied
right before is filled in already. Dragging the link into the window works too. It takes .zip and .tar archives
(gz, xz, bz2, and zst on Python 3.14+), extracted folders, archives that only
contain more archives, font files and images, and sorts everything into the
right folder:

| gnome-look category | Goes to |
| --- | --- |
| GTK3/4 Themes, Gnome Shell Themes | `~/.local/share/themes/` |
| Full Icon Themes | `~/.local/share/icons/` |
| Cursors | `~/.icons/` |
| Gnome Extensions (zip from extensions.gnome.org) | `~/.local/share/gnome-shell/extensions/<uuid>/` |
| Wallpapers (single images or packs, 1280x720 and up) | `~/.local/share/backgrounds/` |
| Fonts | `~/.local/share/fonts/` |

Installing never activates anything; pick the new theme on its page afterwards.
Extensions show up after the next login and stay off until you enable them.

Rejected on purpose, with an explanation: GDM login themes, GRUB boot menu
themes and Plymouth boot splashes. They replace system files as root and a
mistake there can block the login or the boot. For a custom login background
use Background > Login screen instead. Also rejected: Plank/Latte dock themes,
theme source code that still needs building, and anything named like a
built-in fallback theme (Adwaita, Yaru, hicolor), which would otherwise shadow it.

Archives are unpacked under `~/.cache/design-manager` with size limits, path and
symlink checks, and each folder is swapped in only once it is complete. 7z and
rar are not supported, extract those first and drop the folder. Themes copied
into `~/.themes/` or `~/.icons/` by hand show up as well.

Shell themes also need the User Themes extension enabled.

### Updates from gnome-look.org

A link is resolved through the gnome-look OCS API. The app lists the
files of the entry, downloads the chosen one over HTTPS, checks its md5 and runs
it through the same installer. It remembers where each theme folder came from in
`~/.config/design-manager/sources.json`.

On start (only if such a file exists) and via the menu entry "Check theme
updates", the app asks the API again. A changed md5 or a newer file with the same
name apart from date or version counts as an update. The Overview lists every
linked entry, and theme cards show a small mark: up to date, update available,
updating, or a problem with the reason in the tooltip. Updates are installed only
on request and keep the variants that were installed before. A new version of
the active GTK theme with CSS that GTK cannot parse is not installed. Offline
starts change nothing.

Themes installed from a local file have no link; install them once more from
their gnome-look link to connect them.

Self-tests (run in a throwaway home, no network):

    LANGUAGE=en python3 tests/test_installer.py
    LANGUAGE=en python3 tests/test_gnomelook.py

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
