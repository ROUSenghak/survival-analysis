"""Download the pinned buyer-SIREN enrichment Parquets from Hugging Face.

Closes the reproducibility gap found in the pre-refactor audit: the ~1.1 GB
enrichment files were gitignored with no retrieval script. Requires
`huggingface_hub` (see requirements.txt). The revision is pinned to the SHA
recorded in config/pipeline.yaml so the download is byte-reproducible.
"""

from __future__ import annotations


def download_enrichment(cfg, force: bool = False) -> list[str]:
    raw_dir = cfg.paths.raw_enrichment_dir
    existing = sorted(
        p for p in raw_dir.rglob(cfg.pipeline.enrichment.file_glob)
        if p.suffix == ".parquet" and p.stat().st_size > 0
    )
    if existing and not force:
        print(f"Enrichment files already present in {raw_dir} ({len(existing)} files); skipping download.")
        return [str(p) for p in existing]

    try:
        from huggingface_hub import snapshot_download
    except ImportError as e:
        raise ImportError(
            "huggingface_hub is required to download the enrichment dataset: "
            "pip install huggingface_hub"
        ) from e

    raw_dir.mkdir(parents=True, exist_ok=True)
    snapshot_download(
        repo_id=cfg.pipeline.enrichment.hf_dataset_id,
        repo_type="dataset",
        revision=cfg.pipeline.enrichment.hf_dataset_sha,
        local_dir=raw_dir,
        allow_patterns=["*.parquet*"],
    )
    files = sorted(
        p for p in raw_dir.rglob(cfg.pipeline.enrichment.file_glob)
        if p.suffix == ".parquet" and p.stat().st_size > 0
    )
    print(f"Downloaded {len(files)} enrichment files to {raw_dir}")
    return [str(p) for p in files]
