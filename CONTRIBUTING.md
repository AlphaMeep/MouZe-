# Contributing to MouZe

Thanks for helping! Bug reports, skins, translations and code are all welcome.

## Setup

```bash
git clone https://github.com/AlphaMeep/MouZe-.git
cd MouZe-
pip install -e ".[dev]"
pytest
ruff check mouze tests scripts
```

The tests run Qt offscreen, so no display is needed. On a headless Linux machine you may need to install `libegl1 libxkbcommon0 libfontconfig1`.

## Contributing built-in skins

There are two ways to add a skin to the built-in library:

- **As a procedural design (preferred).** Add an entry to `mouze/builtin/catalog.py`. If you need a new shape, add it to `geometry.py`. If you need a new look, add a painter to `procedural.py`. Then run `python scripts/make_assets.py` to refresh the README gallery.
- **As image files.** Only submit art you made yourself, and you must agree to release it under the MIT license.

Please **do not** submit skins that were copied from other apps, websites or Workshop pages, or skins that use characters and logos you don't own.

## Translations

UI strings are written in English and wrapped in `tr()`. Each language is a JSON file in `mouze/i18n/` that maps the English text to the translation.

- To check every language is complete and its `{placeholders}` match, run `python scripts/i18n_strings.py`. A test enforces the same thing.
- To add a language, copy `zh_CN.json`, translate the values and add the language code to `LANGUAGES` in `mouze/i18n/__init__.py`.

## Code layout

| Path | What |
|---|---|
| `mouze/roles.py` | The 17 cursor roles and how they map onto Windows and X11 |
| `mouze/skin.py` | The skin model, `skin.json` loading/saving and image decoding |
| `mouze/builtin/` | Procedural skins: vector geometry, styles and the catalog |
| `mouze/formats/` | `.cur`/`.ani`/Xcursor codecs, pack import/export, other platforms (`platforms.py`), Mouse X / Steam Workshop import (`mousex.py`) |
| `mouze/community.py` | Community catalogs: fetch, subscribe, auto-update |
| `mouze/i18n/` | Translations |
| `mouze/backends/` | Integration with the OS cursor (Windows registry + `SPI_SETCURSORS`, Linux Xcursor themes) |
| `mouze/overlay/` | The click-through effects overlay |
| `mouze/system/` | Hotkeys, pointer polling, foreground-app detection and autostart |
| `mouze/controller.py` | App state: applying skins, profiles, shuffle, hotkey actions |
| `mouze/gui/` | Qt widgets and pages |

## Ground rules

- No input hooks and no DLL injection. MouZe has to stay safe to use alongside anti-cheat software.
- Always leave the user a way back to their original cursors.
- Keep the core (`skin.py`, `formats/`) free of OS-specific code.
