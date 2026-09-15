#!/usr/bin/env python3
"""
Geographic species prior: the list of birds that actually occur where the camera
is. Used to downweight impossible guesses (e.g. a western Lesser Goldfinch when
we're in Pennsylvania), so the classifier lands on the plausible local species.

Source of truth is eBird if you provide a (free) API key:
    export EBIRD_API_KEY=...        # ebird.org/api/keygen
    export EBIRD_REGION=US-PA       # or US-PA-001 for a county, etc.
Without a key it falls back to a built-in eastern-US feeder/yard list, which is
enough to demonstrate the prior. The resolved list is cached to models/.
"""

import json
import os
import urllib.request
from pathlib import Path

_HERE = Path(__file__).parent
_DATA = Path(os.environ.get("DATA_DIR", _HERE))
_DATA.mkdir(parents=True, exist_ok=True)
CACHE = _DATA / "region_species.json"
EBIRD_KEY = os.environ.get("EBIRD_API_KEY", "")
EBIRD_REGION = os.environ.get("EBIRD_REGION", "US-PA")

# Fallback: common eastern-US feeder & yard birds (used when no eBird key).
FALLBACK = {
    "American Goldfinch", "House Finch", "Purple Finch", "Northern Cardinal",
    "Song Sparrow", "White-throated Sparrow", "White-crowned Sparrow", "Dark-eyed Junco",
    "Blue Jay", "American Crow", "Fish Crow", "Common Raven", "Mourning Dove",
    "Rock Pigeon", "Downy Woodpecker", "Hairy Woodpecker", "Red-bellied Woodpecker",
    "Northern Flicker", "Pileated Woodpecker", "Tufted Titmouse", "Carolina Chickadee",
    "Black-capped Chickadee", "White-breasted Nuthatch", "Red-breasted Nuthatch",
    "Carolina Wren", "House Wren", "House Sparrow", "European Starling", "Common Grackle",
    "Red-winged Blackbird", "Brown-headed Cowbird", "American Robin", "Gray Catbird",
    "Northern Mockingbird", "Brown Thrasher", "Cedar Waxwing", "Ruby-throated Hummingbird",
    "Eastern Bluebird", "Chipping Sparrow", "Field Sparrow", "Eastern Towhee",
    "Indigo Bunting", "Rose-breasted Grosbeak", "Baltimore Oriole", "American Kestrel",
    "Cooper's Hawk", "Sharp-shinned Hawk", "Red-tailed Hawk", "Red-shouldered Hawk",
    "Mallard", "Canada Goose", "Turkey Vulture", "Great Blue Heron", "Eastern Phoebe",
    "American Tree Sparrow", "Yellow-rumped Warbler", "Ruby-crowned Kinglet",
}


def _fetch_ebird():
    hdr = {"X-eBirdApiToken": EBIRD_KEY}
    try:
        req = urllib.request.Request(
            f"https://api.ebird.org/v2/product/spplist/{EBIRD_REGION}", headers=hdr)
        codes = set(json.loads(urllib.request.urlopen(req, timeout=20).read()))
        req2 = urllib.request.Request(
            "https://api.ebird.org/v2/ref/taxonomy/ebird?fmt=json&locale=en", headers=hdr)
        tax = json.loads(urllib.request.urlopen(req2, timeout=60).read())
        code2name = {t["speciesCode"]: t["comName"] for t in tax}
        names = {code2name[c] for c in codes if c in code2name}
        print(f"[region] eBird {EBIRD_REGION}: {len(names)} species")
        return names
    except Exception as e:
        print("[region] eBird fetch failed, using fallback:", e)
        return None


def load_allowlist(refresh=False):
    if CACHE.exists() and not refresh:
        try:
            return set(json.loads(CACHE.read_text()))
        except Exception:
            pass
    names = _fetch_ebird() if EBIRD_KEY else None
    if not names:
        names = set(FALLBACK)
        print(f"[region] using built-in fallback list ({len(names)} species)")
    CACHE.parent.mkdir(exist_ok=True)
    CACHE.write_text(json.dumps(sorted(names)))
    return set(names)


if __name__ == "__main__":
    names = load_allowlist(refresh=True)
    print(f"{len(names)} species in region prior. Sample:")
    for n in sorted(names)[:15]:
        print("  ", n)
