"""Download the pinned buyer-SIREN enrichment Parquets (Layer 2 input).

Thin CLI wrapper over boamp.data.download_enrichment. The Hugging Face
revision is pinned in config/pipeline.yaml (enrichment.hf_dataset_sha), so the
download is reproducible. ~1.1 GB.
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from boamp.config import load_config  # noqa: E402
from boamp.data.download_enrichment import download_enrichment  # noqa: E402

if __name__ == "__main__":
    cfg = load_config(PROJECT_ROOT)
    download_enrichment(cfg, force="--force" in sys.argv)
