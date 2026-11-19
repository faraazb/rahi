"""Repository locations, resolved once so modules and tests agree.

    <repo>/data/        source data shared by the pipeline and the app
    <repo>/pipeline/    this package
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = REPO_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
BUILD_DIR = REPO_ROOT / "pipeline" / "build"
