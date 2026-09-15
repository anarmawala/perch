# Bird Watch — Backyard Wildlife Camera & Notifier

A DIY system that watches our balcony feeder and the grass below, detects when
wildlife shows up, identifies what it is, saves the moment, and notifies based
on preferences. A companion app lets us scroll back through everything that
visited and see the captured photos.

Think "self-hosted Bird Buddy" that also handles deer and owls.

## Current status (working prototype)

A working software prototype lives in `prototype/` — running against a live YouTube
feeder cam so it needed **zero hardware** to build. It already does the full loop:

- Live **X-Ray web view**: stream + real-time boxes + species labels (smooth 20 fps)
- **Detection** (YOLOv8s) → **tracking** (ByteTrack) → **species ID** (iNat MobileNet)
  with cross-frame voting and a **geographic prior** (eBird/region) for accuracy
- **Visit logging** to SQLite + a **/timeline** photo gallery + **info cards** (Wikipedia)
- **Push notifications** with a preferences page (species, quiet hours, digest) via ntfy
- **Deploy kit** for the Intel NUC in `prototype/deploy/` (setup script, systemd, OpenVINO)

Swapping the YouTube stream for the real camera is a one-line change (`STREAM_URL`).
Next: deploy to the NUC, then buy the camera. See `prototype/README.md`.

---

## Vision

We have three distinct "stages" wildlife appears on, and they have different needs:

| Stage | Subjects | Distance | Lighting | Key challenge |
|-------|----------|----------|----------|---------------|
| Seed/water bowl | Songbirds | Close | Day | Many species, fast movement |
| Hummingbird feeder | Hummingbirds | Close | Day | Very fast wingbeat, tiny |
| Grass below | Deer, owls | Far | Day **and night** | Night vision for owls, larger frame |

One pipeline, but the hardware/tuning differs per stage. Start with the seed
bowl (easiest, most frequent visitors), then expand outward.

---

## Goals

1. **Detect** wildlife automatically (no watching a live feed).
2. **Identify** it — species for birds, at least category for mammals.
3. **Capture** a good still (and optionally a short clip) with timestamp.
4. **Notify** my wife per her preferences (which species, quiet hours, digest vs. instant).
5. **Browse** history in a simple app: a timeline gallery of visits with photos + labels.

## Non-goals (at least v1)

- 24/7 cloud streaming or "live TV" of the feeder.
- Perfect species accuracy — "House Finch (82%)" is fine; we can correct later.
- Facial-recognition-grade individual animal tracking.
- Public sharing / social features.

---

## Architecture (conceptual)

```
                 ┌─────────────┐
   Camera(s) ───▶│  1. Trigger │  motion / schedule / PIR — avoid running AI 24/7
                 └──────┬──────┘
                        ▼
                 ┌─────────────┐
                 │  2. Capture │  grab still + short clip, buffer frames
                 └──────┬──────┘
                        ▼
                 ┌─────────────┐
                 │  3. Detect  │  MegaDetector: is there an animal? where? crop it
                 └──────┬──────┘
                        ▼
                 ┌─────────────┐
                 │ 4. Classify │  bird species / mammal type  (+ optional BirdNET audio)
                 └──────┬──────┘
                        ▼
                 ┌─────────────┐
                 │  5. Store   │  image + metadata (time, species, confidence) → DB
                 └──────┬──────┘
              ┌─────────┴─────────┐
              ▼                   ▼
      ┌─────────────┐     ┌─────────────┐
      │ 6. Notify   │     │  7. App/UI  │  timeline gallery, filters, corrections
      │ (prefs)     │     │  (PWA)      │
      └─────────────┘     └─────────────┘
```

**Design principle: decouple capture from inference.** The camera/edge device
just captures on motion and drops images in a folder/queue. A separate "brain"
(the Pi itself if light, or a home PC/mini-server) runs detection + classification
on those images — in batch if needed. This keeps the edge cheap and lets us swap
models without touching the camera.

---

## The AI pipeline in detail

Running a big model on every frame is wasteful and hard on cheap hardware. Use a
funnel — cheap filters first, expensive models only on promising frames:

1. **Motion gate** — frame differencing (OpenCV) or a PIR sensor. Kills 95%+ of
   idle frames for near-zero cost.
2. **Detection — MegaDetector** (from the camera-trap world). Answers "is there an
   animal, and where?" Returns boxes for animal/person/vehicle. Crop to the animal.
   Cheap-ish, robust, rejects blowing leaves and shadows.
3. **Classification — split by subject:**
   - **Mammals/owls in the grass → SpeciesNet** (google/cameratrapai). It wraps
     MegaDetector + a ~2000-species classifier; strong on deer and owls.
   - **Feeder birds → species classifier.** Start with SpeciesNet's bird classes
     or an off-the-shelf iNaturalist/EfficientNet bird model. Only fine-tune your
     own (Kaggle dataset + the Thimira project as a template) if accuracy on *our*
     local species is poor.
4. **Optional audio confirmation — BirdNET** on a cheap USB mic near the feeder.
   Acoustic ID is independent of the camera and boosts confidence ("saw a finch-
   shaped bird AND heard a House Finch call" → high confidence). BirdNET-Go runs
   well on a Pi.

> Rule of thumb: **detection tells you *something* is there; classification tells
> you *what*; audio is a tie-breaker.**

---

## Feature list

### Core (MVP)
- [ ] Motion-triggered image capture with timestamp
- [ ] Animal detection (filter out empty/false frames)
- [ ] Store images + metadata in a local database (SQLite)
- [ ] Basic web timeline: scrollable gallery of captures, newest first

### Identification
- [ ] Bird species classification on feeder captures
- [ ] Mammal/large-animal classification for the grass (deer, owl)
- [ ] Confidence scores shown; "unknown" bucket for low confidence
- [ ] Per-visit grouping (collapse a 30-second burst into one "visit")

### Notifications & preferences
- [ ] Push notifications (ntfy / Telegram / Pushover)
- [ ] Preference rules: species allowlist ("only tell me about hummingbirds")
- [ ] Quiet hours / do-not-disturb window
- [ ] "New species" and "rare visitor" alerts vs. common regulars
- [ ] Daily/weekly digest ("12 visits today: 3 species") as an alternative to instant

### App / UX
- [ ] **Live "X-Ray" view (Prime Video–style):** real-time bounding boxes on each
      bird over the live stream + an info panel per species (photo, facts, confidence,
      "seen N× today"). Boxes drawn client-side from streamed detection metadata so
      they're interactive (hover/click a bird). *This is the prototype's centerpiece.*
- [ ] Timeline with filters (species, date, stage/camera)
- [ ] Species profiles ("all House Finch visits", first-seen, frequency)
- [ ] Human correction: relabel a misidentified capture (improves trust + future training data)
- [ ] Favorites / save the best shots
- [ ] Installable as a phone home-screen app (PWA)

### Nice-to-have / later
- [ ] Short video clips, not just stills
- [ ] Night vision (IR) for owls
- [ ] Audio ID via BirdNET (microphone)
- [ ] Hummingbird high-frame-rate mode
- [ ] Weather/time-of-day correlation ("cardinals show up at dawn")
- [ ] Multi-camera support (feeder + yard as separate stages)
- [ ] Auto-generated "postcard" of the day's best visitor (Bird Buddy vibe)
- [ ] Local dashboard on a tablet mounted inside

---

## Hardware — what we have + what to buy (budget ~$200)

**Already on hand (the expensive parts — compute is fully covered):**
- **Intel NUC** → the "brain." Always-on, runs the full pipeline: motion → detect →
  classify (SpeciesNet/MegaDetector in batch on CPU), the database, the web app, and
  notifications. This is why step one costs $0.
- **Raspberry Pi** → spare/edge device. Not needed for the one-camera start (the 4K cam
  streams straight to the NUC). Comes in later for the optional feeder close-up camera
  and/or running BirdNET audio.

### Recommended start: ONE 4K camera (apartment-friendly)

Living in an apartment, a single weatherproof night-vision camera mounted high in a
balcony corner, angled downward, covers **both** the feeder and the grass below. It's
one purchase, one mount, one power run.

```
   ┌──────────────────────┐
   │  4K RTSP night-vision │  high corner, angled down
   │  camera               │  — sees feeder + grass in one frame
   └──────────┬───────────┘
              │  RTSP stream
              ▼
      ┌───────────────┐
      │  Intel NUC    │  brain: crops feeder-zone & ground-zone
      │               │  from one 4K frame → AI, DB, app, notifications
      └───────────────┘
```

**Why 4K matters here:** the software crops the feeder region and the ground region
out of one big frame *as if they were two cameras*. 4K keeps enough detail on small
feeder birds after cropping; 1080p does not. Resolution is what makes one camera viable.

**Trade-off (accepted for MVP):** excellent for deer/owl and for detecting that *a*
bird visited; weaker at naming *small* bird species vs. a dedicated close-up cam. See
upgrade path below.

**Shopping list (~$70–110, well under the $200 budget):**

| Item | Why | Est. |
|------|-----|------|
| **4K RTSP night-vision camera** (Reolink-class) | Covers both zones. Weatherproof + IR → handles owls at night and is its own enclosure. Confirm **RTSP/ONVIF** on the exact model. | $65–95 |
| No-drill mount (clamp / railing / adhesive) | Renter-friendly, no screws into the building. | $10–20 |
| USB microphone (cheap omni) — *optional* | Enables **BirdNET audio ID** later. | $10–20 |

Candidate models (all RTSP/ONVIF): **Reolink RLC-810WA** (4K WiFi — default pick),
**RLC-811A** (4K + 5× optical zoom if the grass is far below), **RLC-810A** (4K PoE if
ethernet is easy).

> ⚠️ Aim it at *your* balcony + the grass directly below. Keep neighbors' windows and
> units out of frame (privacy + etiquette in a multi-unit building).

### Upgrade path (later, if we want crisp feeder-bird shots)

Add a **Pi Camera Module 3** (standard, autofocus, ~$25–35) at the feeder as a dedicated
close-up — plugs into the Pi you already have. The system is designed for multiple
cameras/stages, so it slots in as **Phase 5** without rework.

**Optional later:** a Google Coral USB TPU (~$60) only if batch inference on the NUC
feels too slow. Almost certainly unnecessary for MVP.

**Suggested purchase order:** buy nothing yet → prototype Phase 0 by pointing any camera
you can borrow at the balcony → then buy the **one 4K camera** → add the feeder close-up
cam + mic only if you want them.

---

## Software stack (proposed)

- **Language:** Python (best ecosystem for all these models).
- **CV / capture:** OpenCV, plus RTSP via the camera or `ip-webcam`.
- **Detection:** MegaDetector (PytorchWildlife) .
- **Classification:** SpeciesNet (google/cameratrapai) for mammals; a bird model
  for the feeder.
- **Audio (later):** BirdNET-Analyzer / BirdNET-Go.
- **Storage:** SQLite + images on disk (upgrade to Postgres only if needed).
- **Backend/API:** FastAPI.
- **App:** simple web frontend (plain HTML/HTMX or a light React) as a PWA.
- **Notifications:** ntfy.sh (self-hostable, dead simple) or Telegram bot.
- **Orchestration:** systemd services or Docker Compose on the brain device.

Everything self-hosted on the home network. No cloud required, no subscriptions.

---

## Data model (first pass)

- **Capture:** id, timestamp, camera/stage, image_path, clip_path?, motion_score
- **Detection:** capture_id, bbox, category (animal/person/vehicle), confidence
- **Identification:** capture_id, species/label, confidence, model_version, source (image|audio)
- **Visit:** id, start/end time, stage, best_capture_id, species (grouped burst)
- **Preference rule:** species/category, action (notify|digest|ignore), quiet_hours
- **Correction:** capture_id, corrected_label, user, timestamp (feeds future training)

---

## Phased roadmap

**Phase 0 — Capture (weekend 1).** Point a camera at the seed bowl. Motion-trigger
stills to a folder with timestamps. Confirm we reliably catch visitors. *No AI yet.*

**Phase 1 — Filter.** Add MegaDetector to reject empty frames and crop to the animal.
Store captures + detections in SQLite. Build the barebones timeline gallery.

**Phase 2 — Identify.** Add bird classification (feeder) and SpeciesNet (yard).
Show species + confidence in the timeline. Add the "correct this label" button.

**Phase 3 — Notify.** Wire up push notifications and the preference rules
(allowlist, quiet hours, digest). This is the feature my wife will actually use daily.

**Phase 4 — Polish the app.** Species profiles, filters, favorites, PWA install,
per-visit grouping.

**Phase 5 — Expand.** Night vision for owls, BirdNET audio, video clips,
hummingbird high-FPS mode, second camera, weather correlation.

Ship Phase 0–1 fast for the dopamine, then iterate. Each phase is independently useful.

---

## Open questions / decisions to make

1. ~~**Where does inference run?**~~ **Decided:** capture on the Pi (feeder) + RTSP
   stream (yard); all AI runs on the **NUC** in batch. Compute is already covered.
2. **Which notification channel** does my wife prefer? (Telegram is easiest to start.)
3. **Instant alerts vs. digest** as the default? (Probably digest for common birds,
   instant for rare/hummingbird/owl.)
4. **One camera or per-stage cameras?** Start with one on the feeder; add a yard cam
   in Phase 5.
5. **Retention** — how long do we keep images? (e.g., keep labeled/favorited forever,
   auto-purge unlabeled after 30 days.)

---

## First concrete step

Path A, Phase 0: mount a phone/webcam at the seed bowl and get motion-triggered
stills landing in a folder. Once we trust the capture, everything else is software
we can build incrementally.
