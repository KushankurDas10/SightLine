"""Tests for sightline.config settings."""

import os

from sightline.config import Settings


def test_default_config():
    cfg = Settings()
    assert cfg.gemma_model == "gemma-4-26b-a4b-it"
    assert str(cfg.out_dir) == "out"
    assert cfg.allow_private_urls is False
    assert cfg.prompts_dir.exists()
    assert cfg.mock_data_dir.exists()
    assert (cfg.prompts_dir / "site_review.txt").exists()
    assert (cfg.prompts_dir / "repo_review.txt").exists()
    assert (cfg.mock_data_dir / "site_review.json").exists()
    assert (cfg.mock_data_dir / "repo_review.json").exists()


def test_custom_env_config(monkeypatch):
    monkeypatch.setenv("GEMMA_MODEL", "gemma-4-custom")
    monkeypatch.setenv("MOCK", "1")
    cfg = Settings(gemma_model=os.getenv("GEMMA_MODEL"), mock=os.getenv("MOCK") == "1")
    assert cfg.gemma_model == "gemma-4-custom"
    assert cfg.mock is True
