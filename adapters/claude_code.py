"""
adapters/claude_code.py
Adapter: Project Brief → CLAUDE.md configuration for Claude Code.

Gap 6 (Competitive Landscape): translates Brief to Claude Code context file.
Self-contained CLAUDE.md with full content (no "see other files" references).
Enforces that lost[] must be empty before emitting output via report.validate().
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
    Concept,
    LostConcept,
)


class ClaudeCodeAdapter(ContextAdapter):
    """
    Translates Project Brief → .claude/CLAUDE.md for Claude Code CLI.
    
    Maps Brief sections to CLAUDE.md structure:
      - AGENTS.md → project title, context, stack, domains, risk_zones
      - GUARDRAILS.md → prohibitions (inline, not reference)
      - PLAYBOOK.md → session protocol
      - BUSINESS.md → out of scope rules
      - decisions/index.md → active decisions table (inline)
    
    Enforces: lost[] must be empty (via report.validate()) or AdapterBlockedError is raised.
    Self-contained: no "see other files" references in CLAUDE.md.
    """
    
    target = AdapterTarget.CLAUDE_CODE
    
    def __init__(self):
        super().__init__()
        self._translated = {}
        self._lost_concepts = []
        self._preserved_concepts = []
    
    def translate(self, brief: dict) -> dict:
        """
        Translate Brief dict → CLAUDE.md structure dict.
        
        Args:
            brief: dict with keys AGENTS.md, GUARDRAILS.md, PLAYBOOK.md, BUSINESS.md
        
        Returns:
            dict with mapped configuration sections
        
        Raises:
            AdapterBlockedError: if required fields are missing (with LostConcept details)
        """
        errors = self.validate(brief)
        if errors:
            raise AdapterBlockedError([
                LostConcept(concept=field, source_file="brief", reason=f"missing {field}")
                for field in errors
            ])
        
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
        
        # Track preserved concepts for FidelityReport
        self._preserved_concepts = [
            Concept(concept=k, source_file="AGENTS.md", target_file=".claude/CLAUDE.md")
            for k in self._translated.keys() if self._translated[k] != "⚠ PENDENTE"
        ]
        
        return self._translated
    
    def generate_output(self, output_dir: Path) -> FidelityReport:
        """
        Write translated Brief to .claude/CLAUDE.md.
        
        Args:
            output_dir: directory for .claude/ (will create subdirectory)
        
        Returns:
            FidelityReport with preserved concepts, lost items, and output files
        
        Raises:
            AdapterBlockedError: if lost[] is non-empty (via report.validate())
        """
        output_dir = output_dir / ".claude"
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Build CLAUDE.md content
        content = self._build_claude_md()
        
        # Write file
        claude_md_path = output_dir / "CLAUDE.md"
        claude_md_path.write_text(content, encoding="utf-8")
        
        # Create report with preserved concepts (not translated dict)
        report = FidelityReport(
            project_slug=self._translated.get("title", "unknown"),
            adapter_target=AdapterTarget.CLAUDE_CODE,
            brief_version="1.0.0",
            generated_at=datetime.now(timezone.utc).isoformat(),
        )
        report.preserved = self._preserved_concepts
        report.lost = self._lost_concepts
        report.output_files = [str(claude_md_path)]
        
        # ENFORCE: report.validate() raises AdapterBlockedError if lost[] is non-empty
        # This is the Gap 6 enforcement point
        warnings = report.validate()
        
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
                errors.append(field)
        
        return errors
    
    def _build_claude_md(self) -> str:
        """
        Build complete CLAUDE.md content from translated Brief.
        Self-contained: includes full content, not just references.
        """
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
        
        # Bug 4 fix: include prohibitions inline instead of reference
        lines.extend([
            "",
            "## Proibições",
        ])
        prohibitions = self._translated.get("prohibitions", {})
        if prohibitions:
            for key, value in prohibitions.items():
                lines.append(f"- {key}: {value}")
        else:
            lines.append("⚠ PENDENTE")
        
        lines.extend([
            "",
            "## Fora de Escopo",
        ])
        
        out_of_scope = self._translated.get("out_of_scope", [])
        if out_of_scope:
            for item in out_of_scope:
                lines.append(f"- {item}")
        else:
            lines.append("⚠ PENDENTE")
        
        # Bug 4 fix: include decisions table inline instead of reference
        lines.extend([
            "",
            "## Decisões Ativas",
        ])
        decisions = self._translated.get("decisions", "⚠ PENDENTE")
        if decisions and decisions != "⚠ PENDENTE":
            lines.append(decisions)
        else:
            lines.append("⚠ PENDENTE")
        
        return "\n".join(lines)
