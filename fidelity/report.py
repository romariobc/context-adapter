"""
fidelity/report.py

Dataclasses for the FidelityReport — the formal record of how faithfully
a context-adapter translated the Project Brief to a target platform.

Schema mirrors adapter.fidelity.report.yaml from the nerve-layer.

Rules enforced here (not in the adapter itself):
  - lost[] non-empty  → AdapterBlockedError (adapter must NOT emit config files)
  - degraded[] with severity="high" → emits a warning (caller decides)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# ---------------------------------------------------------------------------
# Supported adapter targets (mirrors schema enum)
# ---------------------------------------------------------------------------

class AdapterTarget(str, Enum):
    CLAUDE_CODE = "claude-code"
    CURSOR      = "cursor"
    COPILOT     = "copilot"
    OLLAMA      = "ollama"
    WINDSURF    = "windsurf"
    CONTINUE    = "continue"


class DegradedSeverity(str, Enum):
    LOW    = "low"
    MEDIUM = "medium"
    HIGH   = "high"   # prohibition degraded — requires Tech Lead review


# ---------------------------------------------------------------------------
# Building blocks
# ---------------------------------------------------------------------------

@dataclass
class Concept:
    """A Brief concept translated with full fidelity."""
    concept:     str  # human-readable name of the concept
    source_file: str  # e.g. "GUARDRAILS.md"
    target_file: str  # e.g. ".claude/CLAUDE.md"


@dataclass
class DegradedItem:
    """A Brief concept translated with partial loss."""
    concept:     str
    source_file: str
    reason:      str              # why the loss happened
    fallback:    str              # what was generated instead
    severity:    DegradedSeverity = DegradedSeverity.MEDIUM


@dataclass
class LostConcept:
    """A Brief concept with no equivalent on the target platform."""
    concept:     str
    source_file: str
    reason:      str


@dataclass
class PlatformFeature:
    """Platform-native feature not originating from the Brief (informational)."""
    feature:     str
    description: str


# ---------------------------------------------------------------------------
# Error
# ---------------------------------------------------------------------------

class AdapterBlockedError(Exception):
    """
    Raised when lost[] is non-empty.
    The adapter MUST NOT emit config files in this state.
    """
    def __init__(self, lost: list[LostConcept]) -> None:
        self.lost = lost
        concepts = ", ".join(f'"{c.concept}"' for c in lost)
        super().__init__(
            f"Adapter blocked — {len(lost)} concept(s) have no platform equivalent: {concepts}"
        )


# ---------------------------------------------------------------------------
# FidelityReport
# ---------------------------------------------------------------------------

@dataclass
class FidelityReport:
    """
    Formal record produced by every adapter after translating the Project Brief.

    Call `.validate()` before emitting config files — raises AdapterBlockedError
    if any concepts were lost, and returns a list of high-severity warnings if
    any prohibitions were degraded.
    """
    project_slug:   str
    adapter_target: AdapterTarget
    brief_version:  str          # semver e.g. "1.2.0"
    generated_at:   str          # ISO-8601 datetime string

    preserved:      list[Concept]        = field(default_factory=list)
    degraded:       list[DegradedItem]   = field(default_factory=list)
    lost:           list[LostConcept]    = field(default_factory=list)
    platform_only:  list[PlatformFeature] = field(default_factory=list)
    output_files:   list[str]            = field(default_factory=list)

    # ------------------------------------------------------------------
    # Derived properties
    # ------------------------------------------------------------------

    @property
    def is_blocked(self) -> bool:
        """True when the adapter must not emit config files."""
        return len(self.lost) > 0

    @property
    def has_critical_degradation(self) -> bool:
        """True when at least one prohibition was degraded (severity=high)."""
        return any(d.severity == DegradedSeverity.HIGH for d in self.degraded)

    @property
    def fidelity_score(self) -> float:
        """
        Simple ratio: preserved / total_concepts.
        Returns 1.0 if no concepts were processed (nothing to lose).
        """
        total = len(self.preserved) + len(self.degraded) + len(self.lost)
        if total == 0:
            return 1.0
        return len(self.preserved) / total

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate(self) -> list[str]:
        """
        Enforce the two rules from the issue spec:

        1. BLOCK  — raises AdapterBlockedError if lost[] is non-empty.
        2. WARN   — returns list of warning strings for high-severity degraded items.

        Callers should call this before writing any config file to disk.
        """
        if self.is_blocked:
            raise AdapterBlockedError(self.lost)

        warnings: list[str] = []
        for item in self.degraded:
            if item.severity == DegradedSeverity.HIGH:
                warnings.append(
                    f'[HIGH] Prohibition degraded: "{item.concept}" '
                    f'({item.source_file}) → {item.fallback}. '
                    f'Reason: {item.reason}'
                )
        return warnings

    # ------------------------------------------------------------------
    # Serialisation (matches nerve-layer event schema)
    # ------------------------------------------------------------------

    def to_event_payload(self) -> dict:
        """Return a dict ready to be emitted as adapter.fidelity.report event."""
        payload: dict = {
            "project_slug":   self.project_slug,
            "adapter_target": self.adapter_target.value,
            "brief_version":  self.brief_version,
            "generated_at":   self.generated_at,
            "preserved": [
                {
                    "concept":     c.concept,
                    "source_file": c.source_file,
                    "target_file": c.target_file,
                }
                for c in self.preserved
            ],
            "degraded": [
                {
                    "concept":     d.concept,
                    "source_file": d.source_file,
                    "reason":      d.reason,
                    "fallback":    d.fallback,
                    "severity":    d.severity.value,
                }
                for d in self.degraded
            ],
            "lost": [
                {
                    "concept":     l.concept,
                    "source_file": l.source_file,
                    "reason":      l.reason,
                }
                for l in self.lost
            ],
        }
        if self.platform_only:
            payload["platform_only"] = [
                {"feature": f.feature, "description": f.description}
                for f in self.platform_only
            ]
        if self.output_files:
            payload["output_files"] = self.output_files
        return payload
