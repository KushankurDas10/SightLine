"""Configuration settings for SightLine."""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# Load environment variables from .env file if present
load_dotenv()

PACKAGE_ROOT = Path(__file__).resolve().parent
REPO_ROOT = PACKAGE_ROOT.parent
PROMPTS_DIR = PACKAGE_ROOT / "prompts"
MOCK_DATA_DIR = PACKAGE_ROOT / "mock_data"


@dataclass(frozen=True)
class Settings:
    """Application settings read from environment variables."""

    gemma_model: str = os.getenv("GEMMA_MODEL", "gemma-4-26b-a4b-it")
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
    github_token: str = os.getenv("GITHUB_TOKEN", "")
    mock: bool = os.getenv("MOCK", "0").strip().lower() in ("1", "true", "yes")
    prompts_dir: Path = PROMPTS_DIR
    mock_data_dir: Path = MOCK_DATA_DIR


settings = Settings()
