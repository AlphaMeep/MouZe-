import importlib.util
import json
import re
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_builder():
    spec = importlib.util.spec_from_file_location("build_site", ROOT / "scripts" / "build_site.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_site_build(tmp_path, qapp):
    site = _load_builder()
    out = tmp_path / "site"
    stats = site.build(out, limit=1)
    page = (out / "index.html").read_text("utf-8")
    assert "{{" not in page, "unfilled template placeholder"
    data = json.loads(re.search(r'<script id="site-data" type="application/json">(.*?)</script>', page, re.S)[1])
    assert stats["skins"] == len(data["skins"]) == len(data["categories"])  # one per category
    assert {s["category"] for s in data["skins"]} == set(data["categories"])
    for s in data["skins"]:
        assert (out / s["thumb"]).is_file()
        css = (out / s["css"]).read_text("utf-8")
        # every cursor image the stylesheet points at exists next to it
        for name in re.findall(r'url\("([^"]+)"\)', css):
            assert (out / s["css"]).parent.joinpath(name).is_file()
        with zipfile.ZipFile(out / s["zip"]) as z:
            assert f"{s['slug']}/mouze-cursors.css" in z.namelist()
    # the community catalog is mirrored and its links resolve
    assert data["community"]["skins"]
    for e in data["community"]["skins"]:
        assert (out / e["url"]).is_file() and (out / e["preview"]).is_file()
    assert (out / "community" / "index.json").is_file()
    for asset in ("style.css", "app.js", "icon.png", ".nojekyll"):
        assert (out / asset).exists()


def test_site_page_uses_test_zone_classes():
    """The page's test zones must use the selectors that the CSS exporter writes."""
    from mouze.formats.platforms import ROLE_CSS
    page = (ROOT / "site" / "index.html").read_text("utf-8")
    exported = {c for sel, _ in ROLE_CSS.values() for c in re.findall(r"\.(mz-[\w-]+)", sel)}
    used = set(re.findall(r'class="zone (mz-[\w-]+)"', page))
    assert used and used <= exported
