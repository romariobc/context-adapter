"""
tests/test_round_trip.py

Round-trip harness tests — verifica FidelityReport para diferentes plataformas
e cenários de tradução.

Casos de teste:
  - Tradução perfeita (tudo preserved, nada degraded/lost)
  - Degradação controlada (severity=high em proibição degradada)
  - Bloqueio (lost[] não vazio — adapter deveria ter recusado)
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from harness.round_trip import (
    fixture_claude_code_simple,
    fixture_cursor_with_risk,
    execute_round_trip,
    validate_fidelity_report,
)
from fidelity.report import AdapterTarget, DegradedSeverity


# ---------------------------------------------------------------------------
# Perfect translation
# ---------------------------------------------------------------------------

class TestPerfectTranslation:
    """Claude Code traduz tudo sem perda — plataforma suporta 100% do Brief."""

    def test_claude_code_perfect_translation(self):
        fixture = fixture_claude_code_simple()
        report = execute_round_trip(fixture)

        # Validações
        is_valid, errors = validate_fidelity_report(report)
        assert is_valid, f"Report validation failed: {errors}"

        # Verificações específicas
        assert len(report.preserved) > 0
        assert len(report.degraded) == 0
        assert len(report.lost) == 0
        assert report.fidelity_score == 1.0

    def test_report_payload_valid(self):
        fixture = fixture_claude_code_simple()
        report = execute_round_trip(fixture)

        payload = report.to_event_payload()
        assert "preserved" in payload
        assert payload["preserved"]
        assert payload["degraded"] == []
        assert payload["lost"] == []


# ---------------------------------------------------------------------------
# Controlled degradation
# ---------------------------------------------------------------------------

class TestControlledDegradation:
    """Cursor degrada algumas proibições (sem hooks) — ainda aceitável."""

    def test_cursor_with_degraded_prohibition(self):
        fixture = fixture_cursor_with_risk()
        report = execute_round_trip(fixture)

        # Validações básicas
        is_valid, errors = validate_fidelity_report(report)
        assert is_valid, f"Report validation failed: {errors}"

        # Deve ter degradação
        assert len(report.degraded) > 0
        degraded_concepts = {d.concept for d in report.degraded}
        assert "ban-direct-db-write" in degraded_concepts

    def test_degraded_has_severity(self):
        fixture = fixture_cursor_with_risk()
        report = execute_round_trip(fixture)

        for degraded in report.degraded:
            assert degraded.severity in [DegradedSeverity.LOW, DegradedSeverity.MEDIUM, DegradedSeverity.HIGH]
            if "prohibition" in degraded.concept.lower() or "ban" in degraded.concept.lower():
                assert degraded.severity == DegradedSeverity.HIGH

    def test_degraded_warning_on_validate(self):
        fixture = fixture_cursor_with_risk()
        report = execute_round_trip(fixture)

        warnings = report.validate()
        # Deve haver warning pois tem degradation high
        if any(d.severity == DegradedSeverity.HIGH for d in report.degraded):
            assert len(warnings) > 0


# ---------------------------------------------------------------------------
# Blocking scenarios
# ---------------------------------------------------------------------------

class TestBlockingScenarios:
    """Adapter bloqueia se lost[] não está vazio — verificar AdapterBlockedError."""

    def test_lost_concepts_block_adapter(self):
        fixture = fixture_claude_code_simple()
        fixture.expected_lost_concepts = ["hook-enforcement"]  # Simular algo que nenhuma plataforma suporta

        report = execute_round_trip(fixture)

        # Report deve ter lost[] preenchido
        assert len(report.lost) > 0

        # Validação deve rejeitar (não é válido ter lost concepts)
        is_valid, errors = validate_fidelity_report(report)
        assert not is_valid
        assert any("not empty" in error for error in errors)

    def test_adapter_error_on_lost_concepts(self):
        fixture = fixture_claude_code_simple()
        fixture.expected_lost_concepts = ["unsupported-concept"]

        report = execute_round_trip(fixture)

        # validate() deve lançar AdapterBlockedError
        from fidelity.report import AdapterBlockedError
        with pytest.raises(AdapterBlockedError):
            report.validate()


# ---------------------------------------------------------------------------
# Fidelity score
# ---------------------------------------------------------------------------

class TestFidelityScore:
    """Score reflete o quanto do Brief foi preservado."""

    def test_perfect_score_when_all_preserved(self):
        fixture = fixture_claude_code_simple()
        report = execute_round_trip(fixture)

        assert report.fidelity_score == 1.0

    def test_degraded_score_with_partial_loss(self):
        fixture = fixture_cursor_with_risk()
        report = execute_round_trip(fixture)

        # Cursor degrada algumas proibições
        # score = preserved / (preserved + degraded + lost)
        total = len(report.preserved) + len(report.degraded) + len(report.lost)
        expected_score = len(report.preserved) / total
        assert report.fidelity_score == expected_score

    def test_zero_score_when_everything_lost(self):
        fixture = fixture_claude_code_simple()
        fixture.expected_preserved_concepts = []
        fixture.expected_lost_concepts = ["everything"]

        report = execute_round_trip(fixture)

        # Todos perdidos = score 0
        assert report.fidelity_score == 0.0


# ---------------------------------------------------------------------------
# Platform-specific behavior
# ---------------------------------------------------------------------------

class TestPlatformSpecific:
    """Cada plataforma tem capacidades diferentes."""

    def test_claude_code_target_file(self):
        fixture = fixture_claude_code_simple()
        report = execute_round_trip(fixture)

        for concept in report.preserved:
            assert ".claude" in concept.target_file

    def test_cursor_target_file(self):
        fixture = fixture_cursor_with_risk()
        report = execute_round_trip(fixture)

        for concept in report.preserved:
            assert ".cursor" in concept.target_file or "always" in concept.fallback.lower()

    def test_adapter_target_in_payload(self):
        fixture = fixture_claude_code_simple()
        report = execute_round_trip(fixture)

        payload = report.to_event_payload()
        assert payload["adapter_target"] == AdapterTarget.CLAUDE_CODE.value
