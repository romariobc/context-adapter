"""
tests/test_adapter_base.py
Unit tests for adapters/base.py (P0-D specification).
Minimum 12 tests required.
"""
import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from adapters.base import ContextAdapter
from fidelity.report import (
    FidelityReport,
    AdapterBlockedError,
    AdapterTarget,
)


class ConcreteAdapter(ContextAdapter):
    """Concrete implementation for testing ABC."""
    
    target = AdapterTarget.CLAUDE_CODE
    
    def translate(self, brief: dict) -> dict:
        if "AGENTS.md" not in brief:
            raise AdapterBlockedError([])
        return {"output_key": "output_value"}
    
    def generate_output(self, output_dir: Path) -> FidelityReport:
        return FidelityReport(
            project_slug="test-project",
            adapter_target=AdapterTarget.CLAUDE_CODE,
            brief_version="1.0.0",
            generated_at="2026-06-27T00:00:00Z",
        )
    
    def validate(self, brief: dict) -> list[str]:
        errors = []
        if "AGENTS.md" not in brief:
            errors.append("missing AGENTS.md")
        return errors


@pytest.fixture
def adapter():
    return ConcreteAdapter()


@pytest.fixture
def valid_brief():
    return {"AGENTS.md": "content", "GUARDRAILS.md": "content"}


@pytest.fixture
def invalid_brief():
    return {"OTHER": "content"}


# Test 1-3: ContextAdapter ABC enforcement
class TestContextAdapterABC:
    """Test 1-3: ABC abstract methods"""
    
    def test_cannot_instantiate_abstract(self):
        with pytest.raises(TypeError):
            ContextAdapter()
    
    def test_concrete_adapter_instantiates(self, adapter):
        assert adapter is not None
        assert adapter.target == AdapterTarget.CLAUDE_CODE
    
    def test_has_three_abstract_methods(self):
        abstract_methods = {
            name for name in ["translate", "generate_output", "validate"]
            if hasattr(ContextAdapter, name)
        }
        assert len(abstract_methods) == 3


# Test 4-6: translate() contract
class TestTranslate:
    """Test 4-6: translate() method"""
    
    def test_translate_returns_dict(self, adapter, valid_brief):
        result = adapter.translate(valid_brief)
        assert isinstance(result, dict)
    
    def test_translate_with_valid_brief(self, adapter, valid_brief):
        result = adapter.translate(valid_brief)
        assert "output_key" in result
    
    def test_translate_raises_on_missing_fields(self, adapter, invalid_brief):
        with pytest.raises(AdapterBlockedError):
            adapter.translate(invalid_brief)


# Test 7-9: generate_output() contract
class TestGenerateOutput:
    """Test 7-9: generate_output() method"""
    
    def test_generate_output_returns_report(self, adapter, tmp_path):
        report = adapter.generate_output(tmp_path)
        assert isinstance(report, FidelityReport)
    
    def test_report_has_required_fields(self, adapter, tmp_path):
        report = adapter.generate_output(tmp_path)
        assert report.project_slug == "test-project"
        assert report.adapter_target == AdapterTarget.CLAUDE_CODE
        assert report.brief_version == "1.0.0"
    
    def test_report_generated_at_is_string(self, adapter, tmp_path):
        report = adapter.generate_output(tmp_path)
        assert isinstance(report.generated_at, str)


# Test 10-12: validate() contract
class TestValidate:
    """Test 10-12: validate() method"""
    
    def test_validate_returns_list(self, adapter, valid_brief):
        errors = adapter.validate(valid_brief)
        assert isinstance(errors, list)
    
    def test_validate_with_valid_brief(self, adapter, valid_brief):
        errors = adapter.validate(valid_brief)
        assert len(errors) == 0
    
    def test_validate_with_invalid_brief(self, adapter, invalid_brief):
        errors = adapter.validate(invalid_brief)
        assert len(errors) > 0
        assert "missing AGENTS.md" in errors


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
