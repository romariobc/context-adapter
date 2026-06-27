"""
adapters/base.py
Abstract base class for Project Brief → platform config translation.
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from fidelity.report import (
    FidelityReport,
    AdapterBlockedError,
    AdapterTarget,
)


class ContextAdapter(ABC):
    """
    Abstract adapter for translating Project Brief → platform-specific config.
    
    Each subclass:
      1. Declares its target: AdapterTarget.CLAUDE_CODE, etc
      2. Implements translate() to parse Brief and produce output dict
      3. Implements generate_output() to write files and return FidelityReport
      4. Implements validate() to check Brief for required fields
    
    Subclasses MUST NOT redefine FidelityReport or AdapterBlockedError —
    these are imported from fidelity.report and shared across all adapters.
    """
    
    # Subclass must override
    target: AdapterTarget = None
    
    @abstractmethod
    def translate(self, brief: dict) -> dict:
        """
        Translate Project Brief dict → platform-specific config dict.
        
        Args:
            brief: parsed Brief (union of AGENTS.md, GUARDRAILS.md, PLAYBOOK.md, BUSINESS.md)
        
        Returns:
            dict of translated configuration (structure depends on adapter)
        
        Raises:
            AdapterBlockedError: if required Brief fields are missing
        """
        pass

    @abstractmethod
    def generate_output(self, output_dir: Path) -> FidelityReport:
        """
        Write translated config to files in output_dir.
        
        Args:
            output_dir: directory to write files (e.g., .claude/, .cursor/)
        
        Returns:
            FidelityReport with success/lost/warnings/output_files
        
        Note:
            Caller must check report.validate() before using output.
            If report.lost[] is non-empty, AdapterBlockedError is raised.
        """
        pass

    @abstractmethod
    def validate(self, brief: dict) -> list[str]:
        """
        Validate that Brief has required fields for this adapter.
        
        Args:
            brief: parsed Brief dict
        
        Returns:
            list of error messages (empty if valid, non-empty if invalid)
        
        Note:
            Does NOT raise — returns errors for caller to decide action.
        """
        pass

    def _required_brief_fields(self) -> list[str]:
        """
        Default list of required Brief fields.
        Override in subclass if adapter needs different fields.
        
        Returns:
            list of required field names (e.g., ["AGENTS.md", "GUARDRAILS.md"])
        """
        return ["AGENTS.md", "GUARDRAILS.md", "BUSINESS.md"]
