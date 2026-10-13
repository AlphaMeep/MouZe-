# MouZe skin format

A skin is either a **folder** or a **`.mouzeskin` file**. A `.mouzeskin` file is just a zip of that folder. Either way it contains a `skin.json` manifest and the files that manifest refers to.

```
my-skin/
├── skin.json
├── arrow.png
├── link.svg
├── busy.gif
└── text.cur
```

## `skin.json`

```json
{
  "format": 1,
  "name": "My Skin",
  "author": "you",
  "category": "Custom",
  "tags": ["neon", "animated"],
  "description": "Optional text shown in the library",
  "license": "CC-BY-4.0",
  "version": "1.0",
  "cursors": {
    "arrow":   {"file": "arrow.png", "hotspot": [0, 0]},
    "link":    {"file": "link.svg",  "hotspot": [11, 1], "size": 32},
    "busy":    {"file": "busy.gif",  "hotspot": [16, 16]},
    "working": {"file": "working.png", "frames": 12, "delay": 60, "hotspot": [0, 0]},
    "text":    {"file": "text.cur"},
    "help":    {"files": ["help1.png", "help2.png"], "delay": 120, "hotspot": [0, 0]},
    "precision": {"file": "cross.png", "hotspot": [7, 7], "pixel_art": true}
  }
}
```

### Roles

`arrow`, `help`, `working`, `busy`, `precision`, `text`, `handwriting`, `unavailable`, `size_ns`, `size_ew`, `size_nwse`, `size_nesw`, `move`, `alternate`, `link`, `pin`, `person`.

Only `arrow` is required. If a role is missing, MouZe uses a sensible fallback instead. For example, `working` falls back to `busy`, the resize roles fall back to `move`, and everything else ends up at `arrow`.

### Per-cursor fields

| Field | Meaning |
|---|---|
| `file` | Image or cursor file: PNG, GIF, APNG, WebP, AVIF, BMP, SVG, CUR, ICO, ANI or Xcursor |
| `files` | A list of images to use as animation frames (instead of `file`) |
| `hotspot` | `[x, y]` of the click point, in the source image's pixels (SVG: viewBox units). For `.cur`/`.ani` files it is read from the file if you leave it out |
| `frames` | Number of frames in a sprite strip (horizontal or vertical) |
| `delay` | Milliseconds per frame. This overrides the delays in a GIF or ANI |
| `size` | The size the art was designed for. Defaults to the image's largest side. Used for SVG and for scaling |
| `pixel_art` | `true` scales by whole multiples with no smoothing |

Art is scaled to whatever cursor size the user picks. The cursor size is the `size` value, which is normally the image width. For crisp results, draw at 64 px or larger, or use SVG.

### Procedural skins

Instead of `cursors`, a skin can contain a `generator` recipe. This is what the Designer saves:

```json
{
  "name": "Night Drive",
  "generator": {
    "pointer": "modern",
    "style": "neon",
    "glow": "#ff2bd6",
    "accent": "#ffffff",
    "rainbow": false
  }
}
```

The available values are:

- **`pointer`**: `classic`, `modern`, `sharp`, `dart`, `dot`, or `reticle:<design>`. The reticle designs are `cross`, `gap`, `dot`, `circle`, `t`, `chevron`, `scope`, `brackets`, `diamond`, `triad`, `x`, `hex`, `ticks` and `bold`.
- **`style`**: `solid`, `gradient`, `neon`, `glass`, `outline`, `pixel`, `rgb`, `flow` or `pulse`.
- **Other keys**: `fill`, `outline`, `accent`, `glow`, `gradient` (a list of 2 or 3 colours), `outline_width`, `shadow`, `rainbow`, `frames` and `frame_delay`.

When MouZe exports a procedural skin, it also writes rendered PNG strips into `cursors`. That way the skin still works in other tools and older versions.
