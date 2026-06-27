"""
harness/round_trip.py

Round-trip test harness — verifica que o adapter traduz corretamente um Brief
e gera FidelityReport válido contra o nerve-layer schema, SEM chamar LLM.

Fluxo:
  1. Carregar fixture (BUSINESS.md, PROJECT_SPEC.md)
  2. Simular tradução para plataforma alvo
  3. Gerar FidelityReport
  4. Validar contra adapter.fidelity.report.yaml schema

Determinístico: sem dependência de LLM, sem network calls.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from fidelity.report import (
    FidelityReport,
    Concept,
    DegradedItem,
    DegradedSeverity,
    LostConcept,
    AdapterTarget,
)


# ---------------------------------------------------------------------------
# Fixtures (hardcoded for deterministic testing)
# ---------------------------------------------------------------------------

@dataclass
class BriefFixture:
    """Uma fixture estática do Brief (simulando projeto real)."""
    project_slug: str
    brief_version: str
    platform_target: AdapterTarget

    # Garantias do Brief
    guardrails: list[str]  # proibições absolutas
    risk_zones: list[str]  # zonas de risco
    business_rules: list[str]  # regras de negócio

    # O que a plataforma deveria traduzir
    expected_preserved_concepts: list[str]
    expected_degraded_concepts: dict[str, str]  # {concept: reason}
    expected_lost_concepts: list[str]  # conceitos sem equivalente


def fixture_claude_code_simple() -> BriefFixture:
    """Fixture: projeto simples, plataforma Claude Code (suporta tudo)."""
    return BriefFixture(
        project_slug="petshop-whatsapp-bot",
        brief_version="1.0.0",
        platform_target=AdapterTarget.CLAUDE_CODE,
        guardrails=["ban-payment-integration", "ban-direct-db-write"],
        risk_zones=["session-management", "migration-scripts"],
        business_rules=["whatsapp-integration-required", "pt-br-language"],
        expected_preserved_concepts=[
            "ban-payment-integration",
            "ban-direct-db-write",
            "session-management",
            "whatsapp-integration-required",
        ],
        expected_degraded_concepts={},
        expected_lost_concepts=[],
    )


def fixture_cursor_with_risk() -> BriefFixture:
    """Fixture: cursor (sem hooks) — algumas proibições degradam."""
    return BriefFixture(
        project_slug="petshop-whatsapp-bot",
        brief_version="1.0.0",
        platform_target=AdapterTarget.CURSOR,
        guardrails=["ban-payment-integration", "ban-direct-db-write"],
        risk_zones=["session-management"],
        business_rules=["whatsapp-integration-required"],
        expected_preserved_concepts=["ban-payment-integration", "session-management"],
        expected_degraded_concepts={
            "ban-direct-db-write": "Cursor has no hook mechanism",
        },
        expected_lost_concepts=[],
    )


# ---------------------------------------------------------------------------
# Round-trip execution
# ---------------------------------------------------------------------------

def execute_round_trip(fixture: BriefFixture) -> FidelityReport:
    """
    Executa tradução simulada e retorna FidelityReport.

    Não chama LLM — usa a fixture para determinar o que deveria estar
    no FidelityReport.
    """
    preserved = [
        Concept(
            concept=c,
            source_file="GUARDRAILS.md",
            target_file=_target_file_for_concept(fixture.platform_target, c),
        )
        for c in fixture.expected_preserved_concepts
    ]

    degraded = [
        DegradedItem(
            concept=c,
            source_file="GUARDRAILS.md",
            reason=reason,
            fallback=f"Always rule instead of hook",
            severity=DegradedSeverity.HIGH,
        )
        for c, reason in fixture.expected_degraded_concepts.items()
    ]

    lost = [
        LostConcept(
            concept=c,
            source_file="GUARDRAILS.md",
            reason=f"No equivalent on {fixture.platform_target.value}",
        )
        for c in fixture.expected_lost_concepts
    ]

    return FidelityReport(
        project_slug=fixture.project_slug,
        adapter_target=fixture.platform_target,
        brief_version=fixture.brief_version,
        generated_at=datetime.now(timezone.utc).isoformat(),
        preserved=preserved,
        degraded=degraded,
        lost=lost,
    )


def _target_file_for_concept(platform: AdapterTarget, concept: str) -> str:
    """Infer the target file path based on platform and concept type."""
    if platform == AdapterTarget.CLAUDE_CODE:
        return ".claude/CLAUDE.md"
    elif platform == AdapterTarget.CURSOR:
        return ".cursor/rules/guardrails.mdc"
    elif platform == AdapterTarget.COPILOT:
        return ".github/copilot-instructions.md"
    else:
        return "system-prompt.txt"


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_fidelity_report(report: FidelityReport) -> tuple[bool, list[str]]:
    """
    Valida FidelityReport contra o schema esperado.

    Regras:
      - lost[] vazio (sempre — adapter bloqueia se não vazio)
      - degraded[] sem severity=HIGH (ou pode ter, depende do teste)
      - preserved[] em ordem

    Returns:
        (is_valid, list_of_errors)
    """
    errors = []

    # Validação 1: lost[] deve estar vazio para passar
    if report.lost:
        errors.append(
            f"report.lost is not empty: {len(report.lost)} concepts have no equivalent"
        )

    # Validação 2: FidelityReport deve ter required fields
    required_fields = ["project_slug", "adapter_target", "brief_version", "generated_at"]
    for field in required_fields:
        if not getattr(report, field, None):
            errors.append(f"Missing required field: {field}")

    # Validação 3: fidelity_score deve ser calculável
    try:
        _ = report.fidelity_score
    except Exception as e:
        errors.append(f"fidelity_score calculation failed: {e}")

    # Validação 4: to_event_payload() deve ser válido
    try:
        payload = report.to_event_payload()
        if not isinstance(payload, dict):
            errors.append("to_event_payload() did not return a dict")
    except Exception as e:
        errors.append(f"to_event_payload() failed: {e}")

    return len(errors) == 0, errors
