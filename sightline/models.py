"""Data models for SightLine analysis."""

from dataclasses import asdict, dataclass, field
from typing import Any, Literal


@dataclass
class Box:
    """Bounding box in CSS pixels."""

    x: float
    y: float
    w: float
    h: float


@dataclass
class Element:
    """Captured interactive, image, or text DOM element."""

    number: int
    selector: str
    tag: str
    text: str
    box: Box
    name: str
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class PageSnapshot:
    """Snapshot of a captured web page."""

    url: str
    screenshot_path: str
    page_width: int
    page_height: int
    elements: list[Element]
    lang: str | None = None
    title: str | None = None


@dataclass
class RepoSnapshot:
    """Snapshot of a fetched GitHub repository."""

    url: str
    owner: str
    name: str
    description: str | None
    homepage: str | None
    default_branch: str
    files: list[str]
    truncated: bool
    readme: str | None
    key_files: dict[str, str] = field(default_factory=dict)
    stars: int = 0
    forks: int = 0
    language: str | None = None
    license_name: str | None = None
    open_issues: int = 0
    pushed_at: str | None = None
    html_url: str = ""


@dataclass
class Finding:
    """A single measured or AI-identified problem."""

    id: str
    source: Literal["measured", "ai"]
    target: Literal["site", "repo"]
    rule: str
    severity: Literal["low", "medium", "high"]
    problem: str
    why_it_matters: str
    fix: str
    fix_snippet: str | None = None
    fix_value: str | None = None
    evidence: str = ""
    confidence: float = 1.0
    element_number: int | None = None
    box: Box | None = None
    file_path: str | None = None
    verified: bool = False
    verified_note: str | None = None
    compare_image: str | None = None
    compare_note: str | None = None


@dataclass
class AnalysisResult:
    """Aggregated result of site or repository analysis."""

    mode: Literal["site", "repo"]
    url: str
    title: str
    findings: list[Finding]
    annotated_image: str | None = None
    issues: dict[str, str] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    stats: dict[str, Any] = field(default_factory=dict)
    repo_info: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert result to a plain JSON-serializable dictionary."""
        return asdict(self)
