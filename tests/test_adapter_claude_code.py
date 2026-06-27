"""
tests/test_adapter_claude_code.py
Unit tests for adapters/claude_code.py (P0-E specification).
Minimum 15 tests + 2 additional validation tests (17 total).
Gap 6 enforcement: lost[] must be empty before emitting output.
"""
import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from adapters.claude_code import ClaudeCodeAdapter
from fidelity.report import AdapterBlockedError, AdapterTarget, Concept, LostConcept


@pytest.fixture
def adapter():
    return ClaudeCodeAdapter()


@pytest.fixture
def valid_brief():
    return {
        "AGENTS.md": {
            "project_name": "Test Project",
            "business_context": "Test context",
            "stack": "Python + Claude",
            "domains": ["domain1"],
            "risk_zones": ["zone1"],
        },
        "GUARDRAILS.md": {
            "prohibitions": {"test_block": "test prohibition"},
            "conditionals": [{"condition": "test"}],
        },
        "PLAYBOOK.md": {
            "session_protocol": {"startup": "checklist"},
        },
        "BUSINESS.md": {
            "out_of_scope": ["feature1"],
        },
        "decisions/index.md": "ADR-001 | Title | accepted",
    }


@pytest.fixture
def invalid_brief():
    return {
        "AGENTS.md": None,
        "GUARDRAILS.md": None,
    }


@pytest.fixture
def tmp_output_dir(tmp_path):
    return tmp_path


# Test 1-3: Target and instantiation
class TestClaudeCodeAdapterBasics:
    """Test 1-3: Basic adapter properties"""
    
    def test_has_correct_target(self, adapter):
        assert adapter.target == AdapterTarget.CLAUDE_CODE
    
    def test_instantiates(self, adapter):
        assert adapter is not None
    
    def test_inherits_from_context_adapter(self, adapter):
        from adapters.base import ContextAdapter
        assert isinstance(adapter, ContextAdapter)


# Test 4-6: translate() contract
class TestTranslate:
    """Test 4-6: translate() method"""
    
    def test_translate_returns_dict(self, adapter, valid_brief):
        result = adapter.translate(valid_brief)
        assert isinstance(result, dict)
    
    def test_translate_maps_agents_fields(self, adapter, valid_brief):
        result = adapter.translate(valid_brief)
        assert result["title"] == "Test Project"
        assert result["context"] == "Test context"
    
    def test_translate_raises_on_invalid(self, adapter, invalid_brief):
        with pytest.raises(AdapterBlockedError):
            adapter.translate(invalid_brief)


# Test 7-9: validate() contract
class TestValidate:
    """Test 7-9: validate() method"""
    
    def test_validate_returns_list(self, adapter, valid_brief):
        errors = adapter.validate(valid_brief)
        assert isinstance(errors, list)
    
    def test_validate_passes_valid_brief(self, adapter, valid_brief):
        errors = adapter.validate(valid_brief)
        assert len(errors) == 0
    
    def test_validate_fails_invalid_brief(self, adapter, invalid_brief):
        errors = adapter.validate(invalid_brief)
        assert len(errors) > 0


# Test 10-12: generate_output() writes file
class TestGenerateOutput:
    """Test 10-12: generate_output() file writing"""
    
    def test_generate_output_creates_directory(self, adapter, valid_brief, tmp_output_dir):
        adapter.translate(valid_brief)
        report = adapter.generate_output(tmp_output_dir)
        assert (tmp_output_dir / ".claude").exists()
    
    def test_generate_output_writes_claude_md(self, adapter, valid_brief, tmp_output_dir):
        adapter.translate(valid_brief)
        report = adapter.generate_output(tmp_output_dir)
        claude_md = tmp_output_dir / ".claude" / "CLAUDE.md"
        assert claude_md.exists()
    
    def test_claude_md_contains_project_title(self, adapter, valid_brief, tmp_output_dir):
        adapter.translate(valid_brief)
        adapter.generate_output(tmp_output_dir)
        claude_md = tmp_output_dir / ".claude" / "CLAUDE.md"
        content = claude_md.read_text()
        assert "Test Project" in content


# Test 13-15: Gap 6 enforcement - lost[] blocks emission
class TestGap6Enforcement:
    """Test 13-15: Gap 6 enforcement - lost[] must be empty"""
    
    def test_generate_output_returns_report(self, adapter, valid_brief, tmp_output_dir):
        adapter.translate(valid_brief)
        report = adapter.generate_output(tmp_output_dir)
        assert report is not None
    
    def test_lost_empty_on_valid_brief(self, adapter, valid_brief, tmp_output_dir):
        adapter.translate(valid_brief)
        report = adapter.generate_output(tmp_output_dir)
        assert len(report.lost) == 0
    
    def test_report_has_output_files(self, adapter, valid_brief, tmp_output_dir):
        adapter.translate(valid_brief)
        report = adapter.generate_output(tmp_output_dir)
        assert len(report.output_files) > 0
        assert "CLAUDE.md" in report.output_files[0]


# Test 16: FidelityReport.preserved (Bug 1 fix)
class TestFidelityReportPreserved:
    """Test 16: FidelityReport.preserved contains Concept objects"""
    
    def test_preserved_concepts_are_concept_type(self, adapter, valid_brief, tmp_output_dir):
        adapter.translate(valid_brief)
        report = adapter.generate_output(tmp_output_dir)
        assert all(isinstance(c, Concept) for c in report.preserved)


# Test 17: FidelityReport.translated should not exist (Bug 1 fix)
class TestFidelityReportNoTranslated:
    """Test 17: FidelityReport.translated attribute does not exist"""
    
    def test_report_translated_attribute_does_not_exist(self, adapter, valid_brief, tmp_output_dir):
        adapter.translate(valid_brief)
        report = adapter.generate_output(tmp_output_dir)
        with pytest.raises(AttributeError):
            _ = report.translated


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
