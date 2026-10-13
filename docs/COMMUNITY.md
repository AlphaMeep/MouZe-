# Community catalogs

A community catalog is MouZe's open answer to the Steam Workshop. It is a plain JSON file plus the skin files, and you can host it anywhere: a GitHub repository, GitHub Pages, any web server or a shared folder. People add the catalog in **Discover → Add catalog…** and can then subscribe to its skins. Subscribed skins appear in their library and update automatically whenever you bump a skin's `version`.

MouZe ships with the starter catalog in this repository ([`community/index.json`](../community/index.json)).

## Format

```json
{
  "name": "My Cursor Catalog",
  "description": "Optional",
  "skins": [
    {
      "id": "sakura-glass",
      "name": "Sakura Glass",
      "author": "you",
      "description": "Cherry-blossom pink glass.",
      "category": "Glass",
      "tags": ["pink", "glass"],
      "version": "1.0",
      "updated": "2026-10-13",
      "animated": false,
      "license": "CC-BY-4.0",
      "url": "skins/sakura-glass.mouzeskin",
      "preview": "previews/sakura-glass.png"
    }
  ]
}
```

- `id` must be unique within the catalog and should never change. Subscriptions are keyed by catalog URL + id.
- `url` and `preview` can be absolute, or relative to the `index.json`. The download can be a `.mouzeskin`, or anything else MouZe imports, such as a `.zip` Windows pack, a `.cape` file or a `.tar.gz` Xcursor theme.
- Bump `version` whenever you change the skin. Subscribers get the update the next time MouZe starts, if *Keep subscribed community skins up to date* is on.
- Downloads are limited to 50 MB. Previews should be small PNGs; `mouze export <skin> -f preview -o preview.png` makes one.

## Contributing to the MouZe catalog

1. Make your skin in MouZe, then use Library → Export → MouZe skin (.mouzeskin) and Export → Preview image.
2. Put the files in `community/skins/` and `community/previews/`.
3. Add an entry to `EXTERNAL` in [`scripts/build_community.py`](../scripts/build_community.py), run it, and open a pull request.

Only submit work you made yourself. Please say which license it is under; MIT or a Creative Commons license is ideal. Skins copied from other apps, sites or Workshop pages, and skins that use characters or logos you don't own, will not be accepted.
