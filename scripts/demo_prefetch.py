"""Prefetch demo script to warm up local caches and prepare demo assets."""

import json
import os
from pathlib import Path

from sightline.config import settings
from sightline.pipeline import run

ROOT_DIR = Path(__file__).resolve().parent.parent


def prefetch() -> None:
    """Warm up demo assets and generate a sample offline run."""
    print("=== SightLine Demo & Cache Prefetch ===")

    out_demo = settings.out_dir / "demo"
    out_demo.mkdir(parents=True, exist_ok=True)
    print(f"[*] Target demo output directory: {out_demo}")

    # 1. Validate bundled static demo files
    static_demo_dir = ROOT_DIR / "web" / "static" / "demo"
    expected_images = [
        "example_annotated.png",
        "compare_site-001.png",
        "compare_site-002.png",
        "compare_site-003.png",
    ]

    missing_images = [img for img in expected_images if not (static_demo_dir / img).exists()]
    if missing_images:
        print(f"[!] Warning: Missing bundled demo images: {missing_images}")
    else:
        print(f"[+] Bundled demo comparison images verified ({len(expected_images)} files).")

    # 2. Validate sample results
    sample_site = ROOT_DIR / "web" / "static" / "sample_result_site.json"
    sample_repo = ROOT_DIR / "web" / "static" / "sample_result_repo.json"

    if sample_site.exists() and sample_repo.exists():
        print("[+] Bundled site and repo demo result JSONs verified.")
        # Copy to out/demo for immediate offline review
        (out_demo / "sample_result_site.json").write_text(
            sample_site.read_text(encoding="utf-8"), encoding="utf-8"
        )
        (out_demo / "sample_result_repo.json").write_text(
            sample_repo.read_text(encoding="utf-8"), encoding="utf-8"
        )
    else:
        print("[!] Warning: Missing bundled sample result JSONs.")

    # 3. Generate offline local test fixture inspection (MOCK=1)
    os.environ["MOCK"] = "1"
    sample_repo_fixture = ROOT_DIR / "tests" / "fixtures" / "sample_repo.json"

    if sample_repo_fixture.exists():
        print("[*] Generating offline repository inspection sample...")
        repo_data = json.loads(sample_repo_fixture.read_text(encoding="utf-8"))
        repo_url = repo_data.get("url", "https://github.com/octocat/Hello-World")
        try:
            result = run(
                mode="repo",
                url=repo_url,
                out_dir=out_demo,
            )
            print(f"[+] Offline sample repo analysis generated: {len(result.findings)} findings.")
            print(f"[+] Output saved to {out_demo / 'result.json'}")
        except Exception as exc:
            print(f"[!] Notice: Offline pipeline run encountered: {exc}")

    print("\n[+] Demo warmup complete! You can view the demo UI at:")
    print("    http://localhost:8000?demo=site")
    print("    http://localhost:8000?demo=repo")


if __name__ == "__main__":
    prefetch()
