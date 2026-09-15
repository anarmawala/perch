#!/usr/bin/env python3
"""
Eval harness — measure species-classifier accuracy on a labeled crop set, so we
can compare models (current iNat vs. BioCLIP, etc.) and settings with numbers
instead of eyeballing.

Build the labeled set from real captures (human-verified):
  1. The running app already saves bird crops to  data/captures/<ts>_<Predicted>_<id>.jpg
  2. Review them and move CORRECT ones into      data/eval/<Species Name>/*.jpg
     (fix any that were mislabeled — that's the whole point of ground truth).
  3. Score:
       docker compose exec api python eval/run.py            # current model + region prior
       docker compose exec api python eval/run.py --no-prior # prior's contribution
       docker compose exec api python eval/run.py --model bioclip   # (once added)

Reports top-1 / top-k accuracy, per-species accuracy, and the most common confusions.
"""
import argparse
import glob
import os
import sys
from collections import Counter, defaultdict

import cv2

# import the classifier(s) from the api service
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from classifier import BirdClassifier  # noqa: E402
from region import load_allowlist  # noqa: E402

DATA_DIR = os.environ.get("DATA_DIR", os.path.join(os.path.dirname(__file__), "..", "data"))


def get_classifier(name: str, use_prior: bool):
    if name == "inat":
        clf = BirdClassifier()
        if use_prior:
            clf.set_allow(load_allowlist())
        return lambda crop, k: [p[0] for p in clf.classify(crop, topk=k)]
    if name == "bioclip":
        from bioclip_classifier import BioCLIPClassifier
        bio = BioCLIPClassifier(sorted(load_allowlist()))
        return lambda crop, k: [p[0] for p in bio.classify(crop, topk=k)]
    raise SystemExit(f"unknown model: {name}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=os.path.join(DATA_DIR, "eval"))
    ap.add_argument("--model", default="inat")
    ap.add_argument("--no-prior", action="store_true")
    ap.add_argument("--topk", type=int, default=3)
    args = ap.parse_args()

    classify = get_classifier(args.model, use_prior=not args.no_prior)

    species_dirs = sorted(d for d in glob.glob(os.path.join(args.data, "*")) if os.path.isdir(d))
    if not species_dirs:
        print(f"No labeled crops found in {args.data}/")
        print("Create data/eval/<Species Name>/*.jpg (verified crops) first — see this file's docstring.")
        return

    total = top1 = topk_hits = 0
    per = defaultdict(lambda: [0, 0])  # species -> [correct, total]
    confusions = Counter()

    for d in species_dirs:
        truth = os.path.basename(d)
        imgs = glob.glob(os.path.join(d, "*.jpg")) + glob.glob(os.path.join(d, "*.png"))
        for img_path in imgs:
            crop = cv2.imread(img_path)
            if crop is None:
                continue
            names = classify(crop, args.topk)
            total += 1
            per[truth][1] += 1
            if names and names[0] == truth:
                top1 += 1
                per[truth][0] += 1
            if truth in names:
                topk_hits += 1
            if names and names[0] != truth:
                confusions[f"{truth}  ->  {names[0]}"] += 1

    if not total:
        print("No images found under the species folders.")
        return

    print(f"\nmodel={args.model}  prior={'off' if args.no_prior else 'on'}  "
          f"({total} crops, {len(species_dirs)} species)")
    print(f"  top-1  accuracy: {top1}/{total} = {100 * top1 / total:.1f}%")
    print(f"  top-{args.topk} accuracy: {topk_hits}/{total} = {100 * topk_hits / total:.1f}%")
    print("\nper species (top-1):")
    for sp in sorted(per):
        c, t = per[sp]
        print(f"  {sp:26s} {c}/{t} = {100 * c / t:.0f}%")
    if confusions:
        print("\ntop confusions (truth -> predicted):")
        for k, n in confusions.most_common(10):
            print(f"  {n:3d}  {k}")


if __name__ == "__main__":
    main()
