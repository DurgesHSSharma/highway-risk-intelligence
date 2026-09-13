import sys
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/app/config.py -> backend/app -> backend -> repo root
REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# Phase 6 reuses the Phase 3 leakage-audited feature definitions
# (scripts.prepare_features) instead of redefining them here. That package
# lives at the repo root, one level above backend/, so it is not importable
# from the backend's own working directory (backend/) without this.
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


class Settings(BaseSettings):
    app_name: str = "Highway Risk Intelligence API"
    app_env: str = "development"
    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]

    # Phase 6: SQLite data layer + ML prediction service.
    # Paths are repo-root-relative by default (configurable via .env) so the
    # same settings work whether the app is launched from backend/ or the
    # repo root.
    database_path: str = "data/database/highway_risk.db"
    dataset_csv_path: str = "data/synthetic/highway_project_snapshots.csv"
    models_dir: str = "models"

    default_page_size: int = 20
    max_page_size: int = 100

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def database_file_path(self) -> Path:
        p = Path(self.database_path)
        return p if p.is_absolute() else REPO_ROOT / p

    @property
    def database_url(self) -> str:
        return f"sqlite:///{self.database_file_path.as_posix()}"

    @property
    def dataset_csv_file_path(self) -> Path:
        p = Path(self.dataset_csv_path)
        return p if p.is_absolute() else REPO_ROOT / p

    @property
    def models_dir_path(self) -> Path:
        p = Path(self.models_dir)
        return p if p.is_absolute() else REPO_ROOT / p


settings = Settings()
