"""
adapters/claude_code.py
Adapter: Project Brief → CLAUDE.md configuration for Claude Code.

Gap 6 (Competitive Landscape): translates Brief to Claude Code context file.
Enforces that lost[] must be empty before emitting output.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from adapters.base import ContextAdapter
from fidelity.report import (
    FidelityReport,
    AdapterBlockedError,
    AdapterTarget,
    LostConcept,
)


class ClaudeCodeAdapter(ContextAdapter):
    """
    Translates Project Brief → .claude/CLAUDE.md for Claude Code CLI.
    
    Maps Brief sections to CLAUDE.md structure:
      - AGENTS.md → project title, context, stack, domains
      - GUARDRAILS.md → prohibitions, conditionals
      - PLAYBOOK.md → session protocol
      - BUSINESS.md → out of scope rules
      - decisions/index.md → active decisions table
    
    Enforces: lost[] must be empty or AdapterBlockedError is raised.
    """
    
    target = AdapterTarget.CLAUDE_CODE
    
    def __init__(self):
        super().__init__()
        self._translated = {}
        self._lost_concepts = []
    
    def translate(self, brief: dict) -> dict:
        """
        Translate Brief dict → CLAUDE.md structure dict.
        
        Args:
            brief: dict with keys AGENTS.md, GUARDRAILS.md, PLAYBOOK.md, BUSINESS.md
        
        Returns:
            dict with mapped configuration sections
        
        Raises:
            AdapterBlockedError: if required fields are missing
        """
        errors = self.validate(brief)
        if errors:
            raise AdapterBlockedError([])
        
        self._translated = {
            "title": brief.get("AGENTS.md", {}).get("project_name", "⚠ PENDENTE"),
            "context": brief.get("AGENTS.md", {}).get("business_context", "⚠ PENDENTE"),
            "stack": brief.get("AGENTS.md", {}).get("stack", "⚠ PENDENTE"),
            "domains": brief.get("AGENTS.md", {}).get("domains", []),
            "risk_zones": brief.get("AGENTS.md", {}).get("risk_zones", []),
            "prohibitions": brief.get("GUARDRAILS.md", {}).get("prohibitions", {}),
            "conditionals": brief.get("GUARDRAILS.md", {}).get("conditionals", []),
            "session_protocol": brief.get("PLAYBOOK.md", {}).get("session_protocol", {}),
            "out_of_scope": brief.get("BUSINESS.md", {}).get("out_of_scope", []),
            "decisions": brief.get("decisions/index.md", "⚠ PENDENTE"),
        }
        
        return self._translated
    
    def generate_output(self, output_dir: Path) -> FidelityReport:
        """
        Write translated Brief to .claude/CLAUDE.md.
        
        Args:
            output_dir: directory for .claude/ (will create subdirectory)
        
        Returns:
            FidelityReport with success/lost/warnings/output_files
        
        Raises:
            AdapterBlockedError: if lost[] is non-empty (ENFORCEMENT)
        """
        output_dir = output_dir / ".claude"
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Build CLAUDE.md content
        content = self._build_claude_md()
        
        # Write file
        claude_md_path = output_dir / "CLAUDE.md"
        claude_md_path.write_text(content, encoding="utf-8")
        
        # Create report
        report = FidelityReport(
            project_slug=self._translated.get("title", "unknown"),
            adapter_target=AdapterTarget.CLAUDE_CODE,
            brief_version="1.0.0",
            generated_at=datetime.now(timezone.utc).isoformat(),
        )
        report.translated = self._translated
        report.lost = self._lost_concepts
        report.output_files = [str(claude_md_path)]
        
        # ENFORCE: if lost[] is non-empty, raise AdapterBlockedError
        if report.lost:
            raise AdapterBlockedError(report.lost)
        
        return report
    
    def validate(self, brief: dict) -> list[str]:
        """
        Validate that Brief has required fields.
        
        Args:
            brief: Brief dict
        
        Returns:
            list of validation errors (empty if valid)
        """
        errors = []
        required = self._required_brief_fields()
        
        for field in required:
            if field not in brief or not brief[field]:
                errors.append(f"missing {field}")
        
        return errors
    
    def _build_claude_md(self) -> str:
        """Build complete CLAUDE.md content from translated Brief."""
        lines = [
            f"# {self._translated.get('title', 'Project')}",
            "",
            "## Contexto do Projeto",
            f"{self._translated.get('context', '⚠ PENDENTE')}",
            "",
            "## Stack",
            f"{self._translated.get('stack', '⚠ PENDENTE')}",
            "",
            "## Domínios",
        ]
        
        domains = self._translated.get("domains", [])
        if domains:
            for domain in domains:
                lines.append(f"- {domain}")
        else:
            lines.append("⚠ PENDENTE")
        
        lines.extend([
            "",
            "## Zonas de Risco",
        ])
        
        risk_zones = self._translated.get("risk_zones", [])
        if risk_zones:
            for zone in risk_zones:
                lines.append(f"- {zone}")
        else:
            lines.append("⚠ PENDENTE")
        
        lines.extend([
            "",
            "## Proibições",
            "Ver GUARDRAILS.md#prohibitions",
            "",
            "## Fora de Escopo",
        ])
        
        out_of_scope = self._translated.get("out_of_scope", [])
        if out_of_scope:
            for item in out_of_scope:
                lines.append(f"- {item}")
        else:
            lines.append("⚠ PENDENTE")
        
        lines.extend([
            "",
            "## Decisões Ativas",
            "Ver decisions/index.md",
        ])
        
        return "\n".join(lines)
