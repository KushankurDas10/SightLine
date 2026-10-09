"""GitHub API client for repository inspection and file fetching."""

import base64
import os
import sys
from typing import Any

import httpx

from sightline.config import settings
from sightline.models import RepoSnapshot

# Priority candidate key files to inspect
KEY_FILE_CANDIDATES = [
    "package.json",
    "requirements.txt",
    "pyproject.toml",
    "Makefile",
    "Dockerfile",
    "setup.py",
    "go.mod",
    "Cargo.toml",
    "main.py",
    "app.py",
    "index.js",
]

# Additional entry points to check if room remains under the 6 key files limit
ENTRY_POINT_FALLBACKS = [
    "src/main.py",
    "src/app.py",
    "src/index.js",
]

MAX_KEY_FILES = 6
MAX_FILE_BYTES = 20 * 1024  # 20 KB
DEFAULT_TIMEOUT_SECONDS = 15.0


def parse_repo_url(url: str) -> tuple[str, str]:
    """Parse owner and repository name from GitHub URL or owner/repo string.

    Accepts:
      - https://github.com/owner/repo
      - https://github.com/owner/repo/
      - https://github.com/owner/repo.git
      - https://github.com/owner/repo/tree/branch/...
      - git@github.com:owner/repo.git
      - owner/repo
    """
    clean = url.strip()
    if clean.startswith("git@github.com:"):
        path = clean[len("git@github.com:") :]
    elif "github.com/" in clean:
        path = clean.split("github.com/", 1)[1]
    else:
        path = clean

    # Strip query parameters and fragment identifiers
    path = path.split("?")[0].split("#")[0]
    parts = [p for p in path.strip("/").split("/") if p]

    if len(parts) < 2:
        raise ValueError(f"Invalid GitHub repository URL or specifier: '{url}'")

    owner = parts[0]
    repo = parts[1]
    if repo.endswith(".git"):
        repo = repo[:-4]

    if not owner or not repo:
        raise ValueError(f"Could not extract owner and repository from: '{url}'")

    return owner, repo


def _decode_content(data: Any, raw_text: str = "") -> str:
    """Decode file content from GitHub API response (base64 or plain string)."""
    if isinstance(data, dict) and "content" in data:
        content_field = data.get("content", "")
        encoding = data.get("encoding", "")
        if encoding == "base64" or isinstance(content_field, str):
            try:
                cleaned = content_field.replace("\n", "").replace("\r", "")
                return base64.b64decode(cleaned).decode("utf-8", errors="replace")
            except Exception:
                return content_field
        return str(content_field)
    if isinstance(data, str):
        return data
    return raw_text


def _clean_token(token: str | None) -> str | None:
    """Return token if not empty or placeholder."""
    if not token:
        return None
    val = token.strip()
    if not val or val.startswith("your_") or "personal_access_token" in val.lower():
        return None
    return val


def _check_http_error(resp: httpx.Response, owner: str, repo: str) -> None:
    """Raise clear, actionable errors for known GitHub status codes."""
    if resp.status_code == 401:
        raise RuntimeError(
            "GitHub API authentication failed (401). Check that your GITHUB_TOKEN is valid."
        )
    if resp.status_code == 404:
        raise RuntimeError(
            f"Repository '{owner}/{repo}' not found or is private (404)."
        )
    if resp.status_code == 403:
        raise RuntimeError(
            "GitHub API rate limit exceeded (403). Set GITHUB_TOKEN in your environment "
            "or .env file to increase rate limits."
        )
    resp.raise_for_status()


def fetch(
    url: str,
    token: str | None = None,
    client: httpx.Client | None = None,
) -> RepoSnapshot:
    """Fetch GitHub repository metadata, file tree, README, and key files.

    Args:
        url: GitHub repository URL or 'owner/repo' string.
        token: Optional GitHub personal access token (defaults to GITHUB_TOKEN).
        client: Optional httpx.Client instance (useful for MockTransport testing).

    Returns:
        RepoSnapshot data structure with fetched metadata and file contents.
    """
    owner, repo = parse_repo_url(url)
    raw_token = (
        token
        if token is not None
        else (settings.github_token or os.getenv("GITHUB_TOKEN", ""))
    )
    auth_token = _clean_token(raw_token)

    headers: dict[str, str] = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "SightLine-Repo-Analyzer",
    }
    if auth_token:
        headers["Authorization"] = f"Bearer {auth_token}"

    owns_client = False
    if client is None:
        client = httpx.Client(
            headers=headers,
            timeout=DEFAULT_TIMEOUT_SECONDS,
            follow_redirects=True,
        )
        owns_client = True

    try:
        # 1. Fetch repository metadata
        repo_api_url = f"https://api.github.com/repos/{owner}/{repo}"
        try:
            repo_resp = client.get(repo_api_url, headers=headers)
        except httpx.TimeoutException as exc:
            raise TimeoutError(
                f"GitHub API request timed out after {DEFAULT_TIMEOUT_SECONDS}s: {exc}"
            ) from exc

        _check_http_error(repo_resp, owner, repo)
        repo_data = repo_resp.json()

        description = repo_data.get("description")
        homepage = repo_data.get("homepage")
        default_branch = repo_data.get("default_branch") or "main"

        # 2. Fetch recursive git tree
        tree_url = (
            f"https://api.github.com/repos/{owner}/{repo}/git/trees/{default_branch}?recursive=1"
        )
        files: list[str] = []
        truncated = False
        try:
            tree_resp = client.get(tree_url, headers=headers)
            if tree_resp.status_code == 200:
                tree_data = tree_resp.json()
                truncated = bool(tree_data.get("truncated", False))
                for item in tree_data.get("tree", []):
                    if item.get("type", "blob") == "blob":
                        files.append(item.get("path", ""))
            elif tree_resp.status_code in (403, 404):
                _check_http_error(tree_resp, owner, repo)
        except httpx.TimeoutException as exc:
            raise TimeoutError(
                f"GitHub API request timed out after {DEFAULT_TIMEOUT_SECONDS}s: {exc}"
            ) from exc

        # 3. Fetch README
        readme_url = f"https://api.github.com/repos/{owner}/{repo}/readme"
        readme: str | None = None
        try:
            readme_resp = client.get(readme_url, headers=headers)
            if readme_resp.status_code == 200:
                readme_data = readme_resp.json()
                readme = _decode_content(readme_data, readme_resp.text)
            elif readme_resp.status_code == 404:
                readme = None
            elif readme_resp.status_code == 403:
                _check_http_error(readme_resp, owner, repo)
        except httpx.TimeoutException as exc:
            raise TimeoutError(
                f"GitHub API request timed out after {DEFAULT_TIMEOUT_SECONDS}s: {exc}"
            ) from exc

        # 4. Fetch up to 6 key files cut to 20 KB
        file_set = set(files)
        selected_key_files: list[str] = []
        for candidate in KEY_FILE_CANDIDATES:
            if candidate in file_set:
                selected_key_files.append(candidate)
                if len(selected_key_files) == MAX_KEY_FILES:
                    break

        if len(selected_key_files) < MAX_KEY_FILES:
            for fallback in ENTRY_POINT_FALLBACKS:
                if fallback in file_set and fallback not in selected_key_files:
                    selected_key_files.append(fallback)
                    if len(selected_key_files) == MAX_KEY_FILES:
                        break

        key_files: dict[str, str] = {}
        for file_path in selected_key_files:
            file_url = f"https://api.github.com/repos/{owner}/{repo}/contents/{file_path}"
            try:
                file_resp = client.get(file_url, headers=headers)
                if file_resp.status_code == 200:
                    raw_content = _decode_content(file_resp.json(), file_resp.text)
                    key_files[file_path] = raw_content[:MAX_FILE_BYTES]
            except httpx.TimeoutException as exc:
                raise TimeoutError(
                    f"GitHub API request timed out after {DEFAULT_TIMEOUT_SECONDS}s: {exc}"
                ) from exc
            except Exception:
                pass

        return RepoSnapshot(
            url=f"https://github.com/{owner}/{repo}",
            owner=owner,
            name=repo,
            description=description,
            homepage=homepage,
            default_branch=default_branch,
            files=files,
            truncated=truncated,
            readme=readme,
            key_files=key_files,
        )

    finally:
        if owns_client:
            client.close()


def main() -> None:
    """CLI entry point for sightline.repo.github."""
    if len(sys.argv) < 2:
        print("Usage: python -m sightline.repo.github <repo-url>")
        sys.exit(1)

    url = sys.argv[1]
    try:
        snapshot = fetch(url)
        from sightline.repo.checks import run_all

        findings = run_all(snapshot)

        print("=" * 60)
        print(f"SightLine Repository Summary: {snapshot.owner}/{snapshot.name}")
        print("=" * 60)
        print(f"URL:            {snapshot.url}")
        print(f"Default Branch: {snapshot.default_branch}")
        print(f"Description:    {snapshot.description or 'None'}")
        print(f"Files Count:    {len(snapshot.files)} (truncated: {snapshot.truncated})")
        readme_info = (
            f"Present ({len(snapshot.readme)} chars)"
            if snapshot.readme
            else "Missing"
        )
        print(f"README:         {readme_info}")
        print(f"Key Files:      {', '.join(snapshot.key_files.keys()) or 'None'}")
        print(f"Findings:       {len(findings)} measured issues")
        print("-" * 60)
        for f in findings:
            print(f"[{f.severity.upper()}] {f.rule}: {f.problem}")
            if f.evidence:
                print(f"  Evidence: {f.evidence}")
            print(f"  Fix:      {f.fix}")
        print("=" * 60)
    except Exception as exc:
        print(f"Error inspecting repository: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
