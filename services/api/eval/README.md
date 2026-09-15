# Eval harness

Measure species-classifier accuracy on a **labeled** crop set — so model/setting
changes (BioCLIP vs iNat, 1080p vs 4K, prior on/off) are decided with numbers.

Labeled crops live in `data/eval/<Species Name>/*.jpg` (under the persistent data
volume, so they're not in git). The folder name is the ground-truth species and
must match the classifier's common name exactly (e.g. `Mourning Dove`).

## Build a set (a few minutes)

The running app already saves classifier crops to `data/captures/`. So:

```bash
# 1. Pre-sort those crops into data/eval/<Species>/ by predicted label:
docker compose exec api python eval/seed.py

# 2. Review each species folder and DELETE the wrong ones (and fix subtle mistakes).
#    Browse them on the host under ./data/eval/  — this is the human step.
```

Aim for ~20+ crops each across the species you actually see, especially the ones
that get confused.

## Score

```bash
docker compose exec api python eval/run.py               # current model + region prior
docker compose exec api python eval/run.py --no-prior    # how much the prior helps
docker compose exec api python eval/run.py --model bioclip   # (once wired up)
```

Prints top-1 / top-3 accuracy, per-species accuracy, and the most common
confusions (`truth -> predicted`) — which is exactly where to focus next.
