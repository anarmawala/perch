#!/usr/bin/env python3
"""
Compare the live iNat classifier vs BioCLIP over the crop set — no ground-truth
labels needed. Reports agreement, the top disagreement patterns, and copies the
contested crops to data/review/ so a human (or Claude) can adjudicate just those.

  docker compose exec api python eval/compare.py --per 20

Then pull data/review/ and eyeball the disagreements:
  rsync -avz <host>:.../perch/data/review/ ./review/
"""
import argparse
import glob
import os
import random
import shutil
import sys
from collections import Counter

import cv2

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from classifier import BirdClassifier  # noqa: E402
from region import load_allowlist  # noqa: E402
from bioclip_classifier import BioCLIPClassifier  # noqa: E402

DATA_DIR = os.environ.get("DATA_DIR", os.path.join(os.path.dirname(__file__), "..", "data"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=os.path.join(DATA_DIR, "eval"))
    ap.add_argument("--per", type=int, default=20, help="sample up to N crops per folder")
    args = ap.parse_args()

    allow = load_allowlist()
    inat = BirdClassifier()
    inat.set_allow(allow)
    print("loading BioCLIP (first run downloads ~400 MB)…", flush=True)
    bio = BioCLIPClassifier(sorted(allow))

    review = os.path.join(DATA_DIR, "review")
    shutil.rmtree(review, ignore_errors=True)
    os.makedirs(review, exist_ok=True)

    crops = []
    for d in sorted(glob.glob(os.path.join(args.data, "*"))):
        if not os.path.isdir(d):
            continue
        imgs = glob.glob(os.path.join(d, "*.jpg"))
        random.shuffle(imgs)
        crops += imgs[: args.per]

    total = agree = 0
    patterns = Counter()
    manifest = []
    for p in crops:
        c = cv2.imread(p)
        if c is None:
            continue
        a = inat.classify(c, 1)
        b = bio.classify(c, 1)
        if not a or not b:
            continue
        (an, _, ac), (bn, _, bc) = a[0], b[0]
        total += 1
        if an == bn:
            agree += 1
        else:
            patterns[f"iNat: {an:22s} | BioCLIP: {bn}"] += 1
            fn = os.path.basename(p)
            shutil.copy(p, os.path.join(review, fn))
            manifest.append({"file": fn, "inat": an, "inat_conf": round(ac, 3),
                             "bioclip": bn, "bioclip_conf": round(bc, 3)})
        if total % 50 == 0:
            print(f"  …{total} crops", flush=True)

    import json
    with open(os.path.join(review, "manifest.json"), "w") as fh:
        json.dump(manifest, fh)

    if not total:
        print("No crops found. Run eval/seed.py first.")
        return
    print(f"\n{total} crops · agreement {agree}/{total} = {100 * agree / total:.1f}%")
    print("\ntop disagreement patterns:")
    for k, n in patterns.most_common(20):
        print(f"  {n:3d}  {k}")
    print(f"\n{total - agree} disagreement crops copied to {review}/ — rsync + review.")


if __name__ == "__main__":
    main()
