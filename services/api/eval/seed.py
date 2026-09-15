#!/usr/bin/env python3
"""
Pre-sort captured crops into data/eval/<Species>/ by their predicted label, as a
STARTING POINT for a labeled eval set. Then you just DELETE the wrong ones (and
move any you can re-identify) — much faster than filing from scratch.

  docker compose exec api python eval/seed.py

Caveat: this seeds using the CURRENT model's guesses, so review carefully — don't
only delete the obvious mistakes, fix the subtle ones too. Otherwise you're
grading the model on its own homework.
"""
import glob
import os
import shutil
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from classifier import BirdClassifier  # noqa: E402

DATA_DIR = os.environ.get("DATA_DIR", os.path.join(os.path.dirname(__file__), "..", "data"))


def main():
    # map "MourningDove" (as stored in filenames) -> "Mourning Dove"
    canon = {c.replace(" ", ""): c for c in BirdClassifier().common}

    caps = glob.glob(os.path.join(DATA_DIR, "captures", "*.jpg"))
    out = os.path.join(DATA_DIR, "eval")
    n = 0
    for p in caps:
        parts = os.path.basename(p).split("_")  # <date>_<time>_<SpeciesNoSpaces>_<id>.jpg
        if len(parts) < 4:
            continue
        species = canon.get(parts[2], parts[2])
        d = os.path.join(out, species)
        os.makedirs(d, exist_ok=True)
        shutil.copy(p, os.path.join(d, os.path.basename(p)))
        n += 1
    print(f"Seeded {n} crops into {out}/ across {len(os.listdir(out)) if os.path.isdir(out) else 0} species.")
    print("Now review each folder and DELETE/FIX the wrong ones — that's your ground truth.")


if __name__ == "__main__":
    main()
