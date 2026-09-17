#!/usr/bin/env python3
"""
Geographic species prior: the list of birds that actually occur where the camera
is. Used to downweight impossible guesses (e.g. a western Lesser Goldfinch when
we're in Pennsylvania), so the classifier lands on the plausible local species.

Source of truth is eBird if you provide a (free) API key:
    export EBIRD_API_KEY=...        # ebird.org/api/keygen
    export EBIRD_REGION=US-WA-033   # King County, WA (Redmond); US-WA for the state
Without a key it falls back to a built-in Puget Sound / King County feeder-yard
list. The resolved list is cached to DATA_DIR/region_species.json.
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
EBIRD_REGION = os.environ.get("EBIRD_REGION", "US-WA-033")  # King County, WA (Redmond)

# Fallback: common Puget Sound / King County WA feeder & yard birds (no eBird key).
FALLBACK = {
    # finches, siskins, sparrows, juncos, towhees
    "American Goldfinch", "Lesser Goldfinch", "House Finch", "Purple Finch", "Pine Siskin",
    "Dark-eyed Junco", "Song Sparrow", "Fox Sparrow", "Golden-crowned Sparrow",
    "White-crowned Sparrow", "White-throated Sparrow", "Spotted Towhee", "House Sparrow",
    # chickadees, nuthatch, wrens, bushtit, creeper
    "Black-capped Chickadee", "Chestnut-backed Chickadee", "Red-breasted Nuthatch",
    "Bushtit", "Bewick's Wren", "Pacific Wren", "Brown Creeper",
    # jays and corvids
    "Steller's Jay", "California Scrub-Jay", "American Crow", "Common Raven",
    # woodpeckers
    "Northern Flicker", "Downy Woodpecker", "Hairy Woodpecker", "Pileated Woodpecker",
    # thrushes, waxwing, starling
    "American Robin", "Varied Thrush", "Cedar Waxwing", "European Starling",
    # hummingbirds
    "Anna's Hummingbird", "Rufous Hummingbird",
    # doves and pigeons
    "Mourning Dove", "Band-tailed Pigeon", "Eurasian Collared-Dove", "Rock Pigeon",
    # blackbirds
    "Red-winged Blackbird", "Brewer's Blackbird", "Brown-headed Cowbird",
    # kinglets and warblers
    "Golden-crowned Kinglet", "Ruby-crowned Kinglet", "Yellow-rumped Warbler",
    "Townsend's Warbler", "Orange-crowned Warbler", "Wilson's Warbler",
    # grosbeak, tanager (summer)
    "Black-headed Grosbeak", "Western Tanager",
    # raptors (feeder predators / overhead)
    "Cooper's Hawk", "Sharp-shinned Hawk", "Red-tailed Hawk", "Bald Eagle",
    # large / passing through
    "Canada Goose", "Mallard", "Great Blue Heron",
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
