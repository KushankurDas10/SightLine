"""Review generation and strict evidence verification using Gemma."""

import copy
import io
import logging
from pathlib import Path
from typing import Any, Union

from PIL import Image

from sightline.config import REPO_ROOT, settings
from sightline.gemma import ask_json
from sightline.merge import merge_findings
from sightline.models import Finding, PageSnapshot, RepoSnapshot
from sightline.site.alternatives import attach_measured_alternatives

logger = logging.getLogger(__name__)


def _validate_ai_alternative(alt: Any) -> dict[str, Any] | None:
    """Validate and sanitize an AI-generated alternative fix.

    Drops the alternative if:
    - Not a dictionary.
    - Missing or non-string label, fix, or tradeoff.
    - Overlong fix_snippet (>600 chars) or label (>60 chars).
    - Contains <script> tags or javascript: URLs.
    """
    if not isinstance(alt, dict):
        return None

    label = alt.get("label")
    fix = alt.get("fix")
    tradeoff = alt.get("tradeoff")
    snippet = alt.get("fix_snippet", "")

    if not isinstance(label, str) or not isinstance(fix, str) or not isinstance(tradeoff, str):
        return None

    label_str = label.strip()
    fix_str = fix.strip()
    tradeoff_str = tradeoff.strip()
    snippet_str = str(snippet).strip() if snippet is not None else ""

    if not label_str or not fix_str:
        return None

    # Length limits
    if len(label_str) > 60:
        return None
    if len(snippet_str) > 600:
        return None

    # Security check: drop if script tags or javascript: URLs present
    combined = f"{label_str} {fix_str} {tradeoff_str} {snippet_str}".lower()
    if "<script" in combined or "javascript:" in combined:
        return None

    return {
        "label": label_str,
        "description": fix_str,
        "fix_snippet": snippet_str,
        "tradeoff": tradeoff_str,
        "source": "ai",
        "check_note": "not browser-verified",
    }


def _load_prompt_template(filename: str) -> str:
    """Load prompt template text from prompts dir, with fallback."""
    candidate_paths = [
        settings.prompts_dir / filename,
        REPO_ROOT / "prompts" / filename,
        Path("sightline/prompts") / filename,
    ]
    for path in candidate_paths:
        if path.exists():
            try:
                return path.read_text(encoding="utf-8")
            except Exception as exc:
                logger.warning("Could not read prompt template %s: %s", path, exc)
    return ""


def normalize_text(text: str | None) -> str:
    """Normalize text by collapsing all whitespace and converting to lowercase."""
    if not text:
        return ""
    return " ".join(text.lower().split())


def _apply_enrichment(
    measured: list[Finding],
    enrich_list: list[dict[str, Any]],
    max_ai_alts: int = 3,
) -> list[Finding]:
    """Enrich measured findings with Gemma rationale and fix recommendations."""
    enriched = [copy.copy(f) for f in measured]
    enrich_by_id = {
        item["id"]: item
        for item in enrich_list
        if isinstance(item, dict) and "id" in item
    }

    ai_alt_count = 0
    for f in enriched:
        f.alternatives = list(f.alternatives)
        if f.id in enrich_by_id:
            enr = enrich_by_id[f.id]
            if enr.get("why_it_matters"):
                f.why_it_matters = str(enr["why_it_matters"])
            if enr.get("fix"):
                f.fix = str(enr["fix"])
            if enr.get("fix_snippet") is not None:
                f.fix_snippet = str(enr["fix_snippet"])
            if enr.get("fix_value") is not None:
                f.fix_value = str(enr["fix_value"])
            if "alternative" in enr and ai_alt_count < max_ai_alts:
                ai_alt = _validate_ai_alternative(enr["alternative"])
                if ai_alt is not None:
                    f.alternatives.append(ai_alt)
                    ai_alt_count += 1
            f.verified = True
            f.verified_note = "Enriched by Gemma"

    return enriched


def review_site(
    snapshot: PageSnapshot,
    marked_image_path: Union[str, Path],
    measured: list[Finding],
    timeout_seconds: float = 45.0,
) -> list[Finding]:
    """Generate visual design review using Gemma on annotated snapshot image and DOM.

    Enriches measured findings and validates new findings against real element numbers.
    """
    template = _load_prompt_template("site_review.txt")

    # Build prompt with page context, element list, and measured findings
    lines = [template, "\n--- PAGE CONTEXT ---"]
    lines.append(f"URL: {snapshot.url}")
    lines.append(f"Dimensions: {snapshot.page_width}x{snapshot.page_height}")
    if snapshot.title:
        lines.append(f"Title: {snapshot.title}")
    if snapshot.lang:
        lines.append(f"Language: {snapshot.lang}")

    measured_el_numbers = {f.element_number for f in measured if f.element_number is not None}
    lines.append("\nCaptured Elements:")
    for el in snapshot.elements:
        if el.meta.get("kind") == "interactive" or el.number in measured_el_numbers:
            bx, by, bw, bh = el.box.x, el.box.y, el.box.w, el.box.h
            lines.append(
                f"- Element #{el.number}: <{el.tag}> box=({bx},{by},{bw},{bh}) "
                f"name={el.name!r} text={el.text[:60]!r} meta={el.meta}"
            )

    lines.append("\nMeasured Findings to Enrich:")
    for f in measured:
        lines.append(
            f"- Finding id={f.id!r} rule={f.rule!r} severity={f.severity!r} "
            f"problem={f.problem!r} element_number={f.element_number}"
        )

    user_prompt = "\n".join(lines)

    # Read and downscale marked screenshot image bytes (max 1280px wide)
    image_bytes = None
    image_mime = "image/png"
    marked_path = Path(marked_image_path)
    if marked_path.exists():
        try:
            with Image.open(marked_path) as im:
                if im.width > 1280:
                    new_width = 1280
                    new_height = int(im.height * (1280 / im.width))
                    im = im.resize((new_width, new_height), Image.Resampling.LANCZOS)
                buf = io.BytesIO()
                if im.mode in ("RGBA", "P"):
                    im = im.convert("RGB")
                im.save(buf, format="JPEG", quality=85)
                image_bytes = buf.getvalue()
                image_mime = "image/jpeg"
        except Exception as exc:
            logger.error("Failed to process marked image %s: %s", marked_path, exc)
            try:
                image_bytes = marked_path.read_bytes()
                image_mime = "image/png"
            except Exception:
                pass

    data = ask_json(
        "site_review",
        user_prompt,
        image_bytes=image_bytes,
        image_mime=image_mime,
        timeout_seconds=timeout_seconds,
    )
    if not isinstance(data, dict):
        logger.warning("Gemma site review returned no valid JSON; returning measured findings.")
        return attach_measured_alternatives(snapshot, list(measured))

    # 1. Apply enrichment to measured findings
    enrich_list = data.get("enrich", [])
    if not isinstance(enrich_list, list):
        enrich_list = []
    enriched_measured = _apply_enrichment(measured, enrich_list)

    # 2. Validate and build new findings
    new_findings_raw = data.get("new_findings") or data.get("findings") or []
    if not isinstance(new_findings_raw, list):
        new_findings_raw = []

    elements_by_number = {el.number: el for el in snapshot.elements}
    validated_ai: list[Finding] = []

    for raw in new_findings_raw:
        if not isinstance(raw, dict):
            continue

        el_num = raw.get("element_number")
        if el_num is None:
            continue
        try:
            el_num = int(el_num)
        except (ValueError, TypeError):
            continue

        # Strict validation: element_number must exist in snapshot
        if el_num not in elements_by_number:
            continue

        el = elements_by_number[el_num]
        sev = str(raw.get("severity", "medium")).lower()
        if sev not in ("low", "medium", "high"):
            sev = "medium"

        try:
            conf = float(raw.get("confidence", 0.9))
        except (ValueError, TypeError):
            conf = 0.9
        conf = max(0.0, min(1.0, conf))

        ai_id = f"ai-{len(validated_ai) + 1:03d}"
        finding = Finding(
            id=ai_id,
            source="ai",
            target="site",
            rule=str(raw.get("rule", "visual-hierarchy")),
            severity=sev,  # type: ignore
            problem=str(raw.get("problem", "Visual design issue identified by Gemma.")),
            why_it_matters=str(raw.get("why_it_matters", "")),
            fix=str(raw.get("fix", "")),
            fix_snippet=raw.get("fix_snippet"),
            fix_value=raw.get("fix_value"),
            evidence=str(raw.get("evidence", f"Observed on element #{el_num}")),
            confidence=conf,
            element_number=el_num,
            box=el.box,
            verified=True,
            verified_note=f"Verified element #{el_num}",
        )
        if "alternative" in raw and isinstance(raw["alternative"], dict):
            ai_alt = _validate_ai_alternative(raw["alternative"])
            if ai_alt is not None:
                finding.alternatives.append(ai_alt)

        validated_ai.append(finding)
        if len(validated_ai) >= 8:
            break

    merged = merge_findings(enriched_measured, validated_ai)
    return attach_measured_alternatives(snapshot, merged)


def review_repo(
    repo_snapshot: RepoSnapshot,
    measured: list[Finding],
    timeout_seconds: float = 45.0,
) -> list[Finding]:
    """Generate repository review using Gemma on file tree, README, and key files.

    Enriches measured findings and validates new findings against exact verbatim text quotes.
    """
    template = _load_prompt_template("repo_review.txt")

    lines = [template, "\n--- REPOSITORY CONTEXT ---"]
    lines.append(f"URL: {repo_snapshot.url}")
    lines.append(f"Owner/Name: {repo_snapshot.owner}/{repo_snapshot.name}")
    if repo_snapshot.description:
        lines.append(f"Description: {repo_snapshot.description}")
    file_list = "\n".join(f"- {f}" for f in repo_snapshot.files[:150])
    lines.append(f"Files ({len(repo_snapshot.files)} total):\n{file_list}")

    if repo_snapshot.readme:
        lines.append(f"\n--- README.md ---\n{repo_snapshot.readme[:8000]}")

    for path, content in repo_snapshot.key_files.items():
        if path != "README.md":
            lines.append(f"\n--- {path} ---\n{content[:4000]}")

    lines.append("\nMeasured Findings to Enrich:")
    for f in measured:
        lines.append(
            f"- Finding id={f.id!r} rule={f.rule!r} severity={f.severity!r} "
            f"problem={f.problem!r} file_path={f.file_path}"
        )

    user_prompt = "\n".join(lines)

    data = ask_json("repo_review", user_prompt, image_bytes=None, timeout_seconds=timeout_seconds)
    if not isinstance(data, dict):
        logger.warning("Gemma repo review returned no valid JSON; returning measured findings.")
        return list(measured)

    # 1. Apply enrichment to measured findings
    enrich_list = data.get("enrich", [])
    if not isinstance(enrich_list, list):
        enrich_list = []
    enriched_measured = _apply_enrichment(measured, enrich_list)

    # 2. Build normalized corpus for exact verbatim quote verification
    corpus_chunks: list[str] = []
    if repo_snapshot.readme:
        corpus_chunks.append(repo_snapshot.readme)
    for path, content in repo_snapshot.key_files.items():
        corpus_chunks.append(path)
        corpus_chunks.append(content)
    for f in repo_snapshot.files:
        corpus_chunks.append(f)

    normalized_corpus = " ".join(normalize_text(chunk) for chunk in corpus_chunks)

    # 3. Validate new findings against evidence quotes
    new_findings_raw = data.get("new_findings") or data.get("findings") or []
    if not isinstance(new_findings_raw, list):
        new_findings_raw = []

    validated_ai: list[Finding] = []

    for raw in new_findings_raw:
        if not isinstance(raw, dict):
            continue

        evidence = str(raw.get("evidence", "")).strip()
        if not evidence:
            continue  # Hard rule: drop AI finding without evidence

        norm_evidence = normalize_text(evidence)
        if not norm_evidence or norm_evidence not in normalized_corpus:
            logger.info("Dropping AI finding: evidence quote %r not found in repo text.", evidence)
            continue  # Hard rule: evidence quote must be found in repo text

        sev = str(raw.get("severity", "medium")).lower()
        if sev not in ("low", "medium", "high"):
            sev = "medium"

        try:
            conf = float(raw.get("confidence", 0.9))
        except (ValueError, TypeError):
            conf = 0.9
        conf = max(0.0, min(1.0, conf))

        ai_id = f"ai-{len(validated_ai) + 1:03d}"
        finding = Finding(
            id=ai_id,
            source="ai",
            target="repo",
            rule=str(raw.get("rule", "readme-clarity")),
            severity=sev,  # type: ignore
            problem=str(raw.get("problem", "Repository quality issue identified by Gemma.")),
            why_it_matters=str(raw.get("why_it_matters", "")),
            fix=str(raw.get("fix", "")),
            fix_snippet=raw.get("fix_snippet"),
            fix_value=raw.get("fix_value"),
            evidence=evidence,
            confidence=conf,
            file_path=raw.get("file_path"),
            verified=True,
            verified_note="Verbatim quote verified in repo text",
        )
        validated_ai.append(finding)
        if len(validated_ai) >= 8:
            break

    return merge_findings(enriched_measured, validated_ai)
