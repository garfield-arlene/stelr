#!/usr/bin/env python3
"""Build store-ready zips for each browser target.

Chrome, Edge, and Firefox each validate manifest.json differently for MV3
background scripts: Chrome silently ignores an extra "background.scripts"
key, Edge's packaging validator rejects it outright ("cannot be used with
manifest version 3"), and Firefox needs "scripts" since it doesn't support
"service_worker". No single manifest.json satisfies all three store
validators, so this produces one transformed manifest per target and zips
each into dist/.

Usage: python3 package.py
"""
import copy
import json
import pathlib
import zipfile

HERE = pathlib.Path(__file__).parent
DIST = HERE / "dist"

# Runtime files shipped in every package; README.md and this script are dev-only.
FILES = [
    "background.js", "popup.html", "popup.js", "options.html", "options.js",
    "lib/browser-polyfill.js", "lib/stelr-api.js", "lib/sync-engine.js",
    "icons/icon16.png", "icons/icon48.png", "icons/icon128.png",
]


def build_manifest(base, target):
    m = copy.deepcopy(base)
    if target in ("chrome", "edge"):
        m["background"] = {"service_worker": "background.js", "type": "module"}
        m.pop("browser_specific_settings", None)
    elif target == "firefox":
        m["background"] = {"scripts": ["background.js"], "type": "module"}
        m.pop("minimum_chrome_version", None)
    else:
        raise ValueError(f"unknown target: {target}")
    return m


def main():
    base = json.loads((HERE / "manifest.json").read_text())
    version = base["version"]
    DIST.mkdir(exist_ok=True)

    for target in ("chrome", "edge", "firefox"):
        manifest = build_manifest(base, target)
        zip_path = DIST / f"stelr-bookmark-sync-{target}-v{version}.zip"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("manifest.json", json.dumps(manifest, indent=2) + "\n")
            for rel in FILES:
                z.write(HERE / rel, rel)
        print(f"wrote {zip_path.relative_to(HERE.parent)}")


if __name__ == "__main__":
    main()
