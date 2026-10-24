#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fetch the CC0 / public-domain images and write derivatives plus a manifest.

Every asset here is either CC0 or public domain — no ShareAlike, no
NonCommercial. ShareAlike is excluded on purpose: it is viral in exactly the
direction a design system runs, so anything that becomes a reusable component
has to be unencumbered. Public-domain *object* and public-domain *photograph*
are different things; everything below is a faithful reproduction of a flat
work, where no new copyright arises.

Writes static/img/<slug>.avif and .webp plus static/img/manifest.json, which is
what the credits page should be generated from rather than a hand-kept list.

    python tools/fetch_images.py
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import urllib.parse
from io import BytesIO
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "static" / "img"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")

# Commons serves a scaled derivative from Special:FilePath with ?width=
def commons(filename: str, width: int) -> str:
    return ("https://commons.wikimedia.org/wiki/Special:FilePath/"
            + urllib.parse.quote(filename) + f"?width={width}")


ASSETS = [
    {
        "slug": "bankes-homer",
        "title": "The Bankes Homer (Papyrus 114 = P. Lond. Lit. 28), Iliad XXIV",
        "holding": "British Library",
        "page": "https://commons.wikimedia.org/wiki/File:The_Bankes_Homer_(Papyrus_114_%3D_P._Lond._Lit._28).jpg",
        "src": commons("The Bankes Homer (Papyrus 114 = P. Lond. Lit. 28).jpg", 2400),
        "license": "Public domain",
        "attribution": "The Bankes Homer, P. Lond. Lit. 28. British Library. Public domain.",
        "use": "illustration",
        "where": "Landing page band. A book roll photographed unrolled — already 6:1.",
        "max_width": 2000,
    },
    {
        "slug": "poxy-221",
        "title": "P.Oxy. 221 — ancient commentary (scholia) on Iliad XXI",
        "holding": "Oxyrhynchus Papyri",
        "page": "https://commons.wikimedia.org/wiki/File:P._Oxy._221.jpg",
        "src": commons("P. Oxy. 221.jpg", 1600),
        "license": "Public domain",
        "attribution": "P.Oxy. 221. Public domain.",
        "use": "illustration",
        "where": "How it works. Secondary scholarship keyed by lemma to a primary text.",
        "max_width": 1400,
    },
    {
        "slug": "callimachus-papyrus",
        "title": "Callimachus, Coma Berenices, papyrus",
        "holding": "Wikimedia Commons",
        "page": "https://commons.wikimedia.org/wiki/File:Callimachus,_Coma_Berenices,_papyrus.jpg",
        "src": commons("Callimachus, Coma Berenices, papyrus.jpg", 1600),
        "license": "Public domain",
        "attribution": "Callimachus, Coma Berenices, papyrus. Public domain.",
        "use": "illustration",
        "where": "Eunomia and Pinakes. Callimachus in his own transmission.",
        "max_width": 900,
    },
]


def get(url: str) -> bytes:
    """Fetch via curl rather than urllib.

    Python's SSL verification fails against Wikimedia on this machine — an
    expired root in the bundled certifi store — while curl, which uses the
    system trust store, succeeds. Shelling out is the pragmatic fix and keeps
    the script portable to a machine where urllib would have worked anyway.
    """
    curl = shutil.which("curl")
    if not curl:
        raise RuntimeError("curl is required to fetch these assets")
    result = subprocess.run(
        [curl, "-sSL", "--fail", "--max-time", "180", "-A", UA, url],
        capture_output=True, check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.decode(errors="replace").strip()[:200])
    return result.stdout


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = []
    total = 0

    for asset in ASSETS:
        print(f"\n{asset['title'][:66]}")
        try:
            raw = get(asset["src"])
        except Exception as exc:  # noqa: BLE001
            print(f"  !! fetch failed: {exc}", file=sys.stderr)
            return 1

        image = Image.open(BytesIO(raw))
        if image.mode not in ("RGB", "L"):
            image = image.convert("RGB")
        if image.width > asset["max_width"]:
            height = round(image.height * asset["max_width"] / image.width)
            image = image.resize((asset["max_width"], height), Image.LANCZOS)
        print(f"  source {len(raw)/1024:.0f} KB -> {image.width}x{image.height}")

        written = {}
        for fmt, ext, opts in (
            ("AVIF", "avif", {"quality": 58}),
            ("WEBP", "webp", {"quality": 78, "method": 6}),
        ):
            path = OUT / f"{asset['slug']}.{ext}"
            image.save(path, fmt, **opts)
            size = path.stat().st_size
            total += size
            written[ext] = f"img/{path.name}"
            print(f"  {path.name:<32} {size/1024:6.0f} KB")

        manifest.append({
            "slug": asset["slug"],
            "title": asset["title"],
            "holding": asset["holding"],
            "object_page": asset["page"],
            "license": asset["license"],
            "attribution": asset["attribution"],
            "attribution_required": False,
            "use": asset["use"],
            "where": asset["where"],
            "files": written,
            "width": image.width,
            "height": image.height,
            "checked": "2026-08-31",
        })

    (OUT / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"\n{len(manifest)} assets, {total/1024:.0f} KB total")
    print(f"Wrote {(OUT / 'manifest.json').relative_to(ROOT)}")
    print("\nRe-verify the manifest annually: institutions relicense, and "
          "'I found it on Commons three years ago' is not a defence.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
