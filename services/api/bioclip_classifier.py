"""
BioCLIP zero-shot bird classifier — for the EVAL harness only (it's slower than
the live iNat model, ~100-300 ms/crop on CPU). Restricted to the local species
list, so it's a fine-grained "which of these ~57 birds" decision, which is where
CLIP-style biological models shine.

Weights (~400 MB ViT) download from HuggingFace on first use and cache under
DATA_DIR/hf_cache so they persist across container restarts.
"""
import os

os.environ.setdefault("HF_HOME", os.path.join(os.environ.get("DATA_DIR", "."), "hf_cache"))

import cv2  # noqa: E402
import open_clip  # noqa: E402
import torch  # noqa: E402
from PIL import Image  # noqa: E402

from classifier import _square_pad  # noqa: E402

MODEL = os.environ.get("BIOCLIP_MODEL", "hf-hub:imageomics/bioclip")


class BioCLIPClassifier:
    def __init__(self, species):
        self.species = list(species)
        self.model, _, self.preprocess = open_clip.create_model_and_transforms(MODEL)
        self.tokenizer = open_clip.get_tokenizer(MODEL)
        self.model.eval()
        torch.set_grad_enabled(False)
        # Pre-encode a text embedding per candidate species.
        prompts = [f"a photo of {s}, a bird." for s in self.species]
        tf = self.model.encode_text(self.tokenizer(prompts))
        self.text_features = tf / tf.norm(dim=-1, keepdim=True)

    def classify(self, bgr_crop, topk=3):
        """Return [(common_name, "", score), ...] best-first (same shape as BirdClassifier)."""
        if bgr_crop is None or bgr_crop.size == 0:
            return []
        rgb = cv2.cvtColor(_square_pad(bgr_crop), cv2.COLOR_BGR2RGB)
        x = self.preprocess(Image.fromarray(rgb)).unsqueeze(0)
        feat = self.model.encode_image(x)
        feat = feat / feat.norm(dim=-1, keepdim=True)
        probs = (100.0 * feat @ self.text_features.T).softmax(dim=-1).squeeze(0)
        idx = probs.argsort(descending=True)[:topk].tolist()
        return [(self.species[i], "", float(probs[i])) for i in idx]
