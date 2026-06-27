"""
tests/test_fidelity_report.py

Unit tests for FidelityReport — deterministic, zero LLM dependency.

Coverage:
  - Dataclass construction and derived properties
  - validate() → block rule (lost[] non-empty)
  - validate() → warn rule (degraded[].severity == high)
  - fidelity_score computation
  - to_event_payload() shape and required fields
  - Platform-specific preserved-criteria scenarios (Claude Code, Cursor, Copilot, Ollama)
"""
import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from fidelity.report import (
    AdapterBlockedError,
    AdapterTarget,
    Concept,
    DegradedItem,
    DegradedSeverity,
    FidelityReport,
    LostConcept,
    PlatformFeature,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_report(
    target: AdapterTarget = AdapterTarget.CLAUDE_CODE,
    preserved=None,
    degraded=None,
    lost=None,
    platform_only=None,
    output_files=None,
) -> FidelityReport:
    return FidelityReport(
        project_slug="petshop-whatsapp-bot",
        adapter_target=target,
        brief_version="1.2.0",
        generated_at="2026-06-27T15:00:00Z",
        preserved=preserved or [],
        degraded=degraded or [],
        lost=lost or [],
        platform_only=platform_only or [],
        output_files=output_files or [],
    )


# ---------------------------------------------------------------------------
# Construction and properties
# ---------------------------------------------------------------------------

class TestConstruction:
    def test_defaults_are_empty_lists(self):
        r = _make_report()
        assert r.preserved == []
        assert r.degraded == []
        assert r.lost == []

    def test_is_blocked_false_when_no_lost(self):
        r = _make_report(preserved=[Concept("prohibition-a", "GUARDRAILS.md", ".claude/CLAUDE.md")])
        assert not r.is_blocked

    def test_is_blocked_true_when_lost_non_empty(self):
        r = _make_report(lost=[LostConcept("hook-enforcement", "GUARDRAILS.md", "Cursor has no hooks")])
        assert r.is_blocked

    def test_has_critical_degradation_false_by_default(self):
        r = _make_report(
            degraded=[DegradedItem("risk-zone-a", "AGENTS.md", "no glob support", "added to system prompt", DegradedSeverity.LOW)]
        )
        assert not r.has_critical_degradation

    def test_has_critical_degradation_true_for_high(self):
        r = _make_report(
            degraded=[DegradedItem("absolute-ban", "GUARDRAILS.md", "no hook", "Always rule", DegradedSeverity.HIGH)]
        )
        assert r.has_critical_degradation


# ---------------------------------------------------------------------------
# fidelity_score
# ---------------------------------------------------------------------------

class TestFidelityScore:
    def test_score_is_1_when_no_concepts(self):
        assert _make_report().fidelity_score == 1.0

    def test_score_is_1_when_all_preserved(self):
        r = _make_report(preserved=[
            Concept("a", "GUARDRAILS.md", ".claude/CLAUDE.md"),
            Concept("b", "AGENTS.md", ".claude/CLAUDE.md"),
        ])
        assert r.fidelity_score == 1.0

    def test_score_is_0_when_all_lost(self):
        r = _make_report(lost=[
            LostConcept("a", "GUARDRAILS.md", "no equivalent"),
            LostConcept("b", "AGENTS.md", "no equivalent"),
        ])
        assert r.fidelity_score == 0.0

    def test_score_partial(self):
        r = _make_report(
            preserved=[Concept("a", "GUARDRAILS.md", ".claude/CLAUDE.md")],
            degraded=[DegradedItem("b", "AGENTS.md", "reason", "fallback")],
            lost=[LostConcept("c", "GUARDRAILS.md", "no equivalent")],
        )
        # 1 preserved / 3 total
        assert abs(r.fidelity_score - 1 / 3) < 1e-9


# ---------------------------------------------------------------------------
# validate() — block rule
# ---------------------------------------------------------------------------

class TestValidateBlock:
    def test_raises_when_lost_not_empty(self):
        r = _make_report(lost=[LostConcept("hook", "GUARDRAILS.md", "Cursor has no hooks")])
        with pytest.raises(AdapterBlockedError) as exc_info:
            r.validate()
        assert "hook" in str(exc_info.value)
        assert exc_info.value.lost[0].concept == "hook"

    def test_raises_lists_all_lost_concepts(self):
        r = _make_report(lost=[
            LostConcept("concept-a", "GUARDRAILS.md", "reason-a"),
            LostConcept("concept-b", "AGENTS.md", "reason-b"),
        ])
        with pytest.raises(AdapterBlockedError) as exc_info:
            r.validate()
        assert len(exc_info.value.lost) == 2

    def test_passes_when_lost_empty(self):
        r = _make_report(preserved=[Concept("a", "GUARDRAILS.md", ".claude/CLAUDE.md")])
        warnings = r.validate()
        assert isinstance(warnings, list)

    def test_passes_on_empty_report(self):
        r = _make_report()
        warnings = r.validate()
        assert warnings == []


# ---------------------------------------------------------------------------
# validate() — warn rule
# ---------------------------------------------------------------------------

class TestValidateWarn:
    def test_no_warnings_for_low_severity(self):
        r = _make_report(
            degraded=[DegradedItem("a", "AGENTS.md", "reason", "fallback", DegradedSeverity.LOW)]
        )
        assert r.validate() == []

    def test_no_warnings_for_medium_severity(self):
        r = _make_report(
            degraded=[DegradedItem("a", "AGENTS.md", "reason", "fallback", DegradedSeverity.MEDIUM)]
        )
        assert r.validate() == []

    def test_warning_for_high_severity(self):
        r = _make_report(
            degraded=[DegradedItem("absolute-ban", "GUARDRAILS.md", "no hook", "Always rule", DegradedSeverity.HIGH)]
        )
        warnings = r.validate()
        assert len(warnings) == 1
        assert "[HIGH]" in warnings[0]
        assert "absolute-ban" in warnings[0]

    def test_multiple_high_severity_produces_multiple_warnings(self):
        r = _make_report(
            degraded=[
                DegradedItem("ban-a", "GUARDRAILS.md", "r", "f", DegradedSeverity.HIGH),
                DegradedItem("ban-b", "GUARDRAILS.md", "r", "f", DegradedSeverity.HIGH),
                DegradedItem("risk-c", "AGENTS.md", "r", "f", DegradedSeverity.LOW),
            ]
        )
        warnings = r.validate()
        assert len(warnings) == 2


# ---------------------------------------------------------------------------
# to_event_payload() — schema compliance
# ---------------------------------------------------------------------------

class TestEventPayload:
    def _full_report(self) -> FidelityReport:
        return _make_report(
            preserved=[Concept("ban-payments", "GUARDRAILS.md", ".claude/CLAUDE.md")],
            degraded=[DegradedItem("risk-session", "AGENTS.md", "no glob", "inline rule", DegradedSeverity.MEDIUM)],
            platform_only=[PlatformFeature("auto-context", "Claude Code reads CLAUDE.md automatically")],
            output_files=[".claude/CLAUDE.md"],
        )

    def test_required_fields_present(self):
        payload = self._full_report().to_event_payload()
        required = {"project_slug", "adapter_target", "brief_version", "generated_at",
                    "preserved", "degraded", "lost"}
        assert required.issubset(payload.keys())

    def test_adapter_target_is_string_value(self):
        payload = self._full_report().to_event_payload()
        assert payload["adapter_target"] == "claude-code"

    def test_preserved_shape(self):
        payload = self._full_report().to_event_payload()
        item = payload["preserved"][0]
        assert {"concept", "source_file", "target_file"}.issubset(item.keys())

    def test_degraded_shape(self):
        payload = self._full_report().to_event_payload()
        item = payload["degraded"][0]
        assert {"concept", "source_file", "reason", "fallback", "severity"}.issubset(item.keys())

    def test_lost_is_empty_list_when_none(self):
        payload = self._full_report().to_event_payload()
        assert payload["lost"] == []

    def test_platform_only_included_when_present(self):
        payload = self._full_report().to_event_payload()
        assert "platform_only" in payload
        assert payload["platform_only"][0]["feature"] == "auto-context"

    def test_platform_only_omitted_when_empty(self):
        payload = _make_report().to_event_payload()
        assert "platform_only" not in payload

    def test_output_files_included_when_present(self):
        payload = self._full_report().to_event_payload()
        assert ".claude/CLAUDE.md" in payload["output_files"]

    def test_output_files_omitted_when_empty(self):
        payload = _make_report().to_event_payload()
        assert "output_files" not in payload


# ---------------------------------------------------------------------------
# Platform-specific preserved-criteria scenarios
# ---------------------------------------------------------------------------

class TestClaudeCodeAdapter:
    """
    Claude Code: toda proibição do GUARDRAILS.md → hook pre-tool ou CLAUDE.md rule.
    """
    def test_guardrails_prohibition_preserved_via_hook(self):
        r = _make_report(
            target=AdapterTarget.CLAUDE_CODE,
            preserved=[
                Concept("ban-direct-db-writes", "GUARDRAILS.md", ".claude/hooks/pre-tool-call.sh"),
                Concept("ban-payment-integration", "GUARDRAILS.md", ".claude/CLAUDE.md"),
            ],
        )
        assert not r.is_blocked
        assert r.fidelity_score == 1.0

    def test_missing_hook_equivalent_is_high_severity(self):
        r = _make_report(
            target=AdapterTarget.CLAUDE_CODE,
            degraded=[
                DegradedItem(
                    "ban-schema-migration",
                    "GUARDRAILS.md",
                    "Hook not triggered for Bash tool",
                    "Added as rule in CLAUDE.md",
                    DegradedSeverity.HIGH,
                )
            ],
        )
        warnings = r.validate()
        assert len(warnings) == 1


class TestCursorAdapter:
    """
    Cursor: toda risk_zone → Auto Attached rule com glob correto.
    Cursor não tem hooks — proibições absolutas degradam para Always rule.
    """
    def test_prohibition_degraded_to_always_rule_is_high(self):
        r = _make_report(
            target=AdapterTarget.CURSOR,
            degraded=[
                DegradedItem(
                    "ban-payment-integration",
                    "GUARDRAILS.md",
                    "Cursor has no hook mechanism",
                    "Always rule: never implement payment processing",
                    DegradedSeverity.HIGH,
                )
            ],
        )
        assert r.has_critical_degradation
        assert len(r.validate()) == 1

    def test_risk_zone_preserved_as_auto_attached_rule(self):
        r = _make_report(
            target=AdapterTarget.CURSOR,
            preserved=[
                Concept("risk-session-mgmt", "AGENTS.md", ".cursor/rules/session-risk.mdc"),
            ],
        )
        warnings = r.validate()
        assert warnings == []


class TestCopilotAdapter:
    """
    Copilot: todo GUARDRAILS.md → seção em copilot-instructions.md.
    Copilot tem enforcement mínimo — sem hooks, sem regras por glob.
    """
    def test_all_guardrails_in_copilot_instructions(self):
        r = _make_report(
            target=AdapterTarget.COPILOT,
            preserved=[
                Concept("ban-payment", "GUARDRAILS.md", ".github/copilot-instructions.md"),
                Concept("ban-db-direct", "GUARDRAILS.md", ".github/copilot-instructions.md"),
            ],
        )
        assert r.fidelity_score == 1.0
        assert r.validate() == []

    def test_glob_based_enforcement_lost_on_copilot(self):
        r = _make_report(
            target=AdapterTarget.COPILOT,
            lost=[
                LostConcept(
                    "auto-attach-migration-rules",
                    "AGENTS.md",
                    "Copilot does not support glob-based rule attachment",
                )
            ],
        )
        with pytest.raises(AdapterBlockedError):
            r.validate()


class TestOllamaAdapter:
    """
    Ollama (local): toda proibição → seção no system prompt montado manualmente.
    Não há mecanismo nativo — tudo é instrução no system prompt.
    """
    def test_prohibition_in_system_prompt_is_preserved(self):
        r = _make_report(
            target=AdapterTarget.OLLAMA,
            preserved=[
                Concept("ban-payment-integration", "GUARDRAILS.md", "system-prompt.txt"),
            ],
        )
        assert not r.is_blocked

    def test_hook_capability_lost_on_ollama(self):
        r = _make_report(
            target=AdapterTarget.OLLAMA,
            lost=[
                LostConcept(
                    "pre-tool-hook-enforcement",
                    "GUARDRAILS.md",
                    "Ollama has no hook system — enforcement is instruction-only",
                )
            ],
        )
        with pytest.raises(AdapterBlockedError) as exc_info:
            r.validate()
        assert "pre-tool-hook-enforcement" in str(exc_info.value)
