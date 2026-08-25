from pathlib import Path

import lamindb as ln
import scanpy as sc
from testutils import TESTDB1_DEV_DIR, run_claudecode

PROMPT = (
    "Write a Python script called scrna_pbmc3k.py that loads the PBMC3k dataset "
    "from pbmc3k_raw.h5ad in the current directory and runs a standard single-cell "
    "RNA-seq analysis on it: QC filtering (including mitochondrial content), "
    "normalization, clustering, and UMAP visualization. Save the UMAP as umap.png, "
    "save the processed data as pbmc3k_processed.h5ad, and register it as a LaminDB "
    "artifact with the key 'scrna/pbmc3k_processed.h5ad'. Then run the script."
)
RUN_DIR = Path(f"{TESTDB1_DEV_DIR}/test_05")


def test_scrna_pbmc3k() -> None:
    RUN_DIR.mkdir(parents=True, exist_ok=True)

    raw_path = RUN_DIR / "pbmc3k_raw.h5ad"
    if not raw_path.exists():
        adata = sc.datasets.pbmc3k()
        adata.write_h5ad(raw_path)

    result = run_claudecode(RUN_DIR, PROMPT, install_skill=True)
    print(f"\n--- claude stdout ---\n{result.stdout}")

    # the lamindb skill must have opened and closed a __claudecode__ transform/run
    transform = ln.Transform.filter(key="__claudecode__").one_or_none()
    assert transform is not None, "skill never created the __claudecode__ transform"
    run = ln.Run.filter(transform=transform).order_by("-created_at").first()
    assert run is not None, "no Run found for the __claudecode__ transform"
    assert run.finished_at is not None, (
        "skill did not close the run (ln.finish() was not called)"
    )

    # the generated script's run must be linked via initiated_by_run
    script_run = ln.Run.filter(initiated_by_run=run).order_by("-created_at").first()
    assert script_run is not None, (
        "no Run is linked back to the __claudecode__ agent run via initiated_by_run — "
        "the generated script was not self-tracked with LAMIN_INITIATED_BY_RUN_UID set"
    )

    # the processed AnnData must be registered in LaminDB with the expected key
    h5ad_artifact = (
        ln.Artifact.filter(run=script_run, key="scrna/pbmc3k_processed.h5ad")
        .order_by("-created_at")
        .first()
    )
    assert h5ad_artifact is not None, (
        "pbmc3k_processed.h5ad was not saved as a LaminDB artifact attached to the script's Run"
    )

    # the .h5ad and .png files must exist on disk and be non-empty
    h5ad_path = RUN_DIR / "pbmc3k_processed.h5ad"
    assert h5ad_path.exists(), "pbmc3k_processed.h5ad not found on disk"
    assert h5ad_path.stat().st_size > 0, "pbmc3k_processed.h5ad is empty"

    png_path = RUN_DIR / "umap.png"
    assert png_path.exists(), "umap.png not found on disk"
    assert png_path.stat().st_size > 0, "umap.png is empty"
