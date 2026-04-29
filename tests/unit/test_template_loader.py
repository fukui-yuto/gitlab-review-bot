import tempfile
from pathlib import Path

import pytest

from review_bot.services.template_loader import TemplateLoader


class TestTemplateLoader:
    def test_load_all_templates(self, templates_dir: Path):
        loader = TemplateLoader(templates_dir)
        names = loader.available_names()
        assert "general" in names
        assert "code_quality" in names
        assert "security" in names
        assert "test" in names

    def test_get_existing_template(self, templates_dir: Path):
        loader = TemplateLoader(templates_dir)
        t = loader.get("general")
        assert t is not None
        assert t.name == "general"
        assert t.display_name == "総合レビュー"
        assert t.system_prompt
        assert t.output_format
        assert len(t.checklist) > 0

    def test_get_nonexistent_template(self, templates_dir: Path):
        loader = TemplateLoader(templates_dir)
        assert loader.get("nonexistent") is None

    def test_list_templates(self, templates_dir: Path):
        loader = TemplateLoader(templates_dir)
        templates = loader.list_templates()
        assert len(templates) == 4

    def test_format_help(self, templates_dir: Path):
        loader = TemplateLoader(templates_dir)
        help_text = loader.format_help()
        assert "/review general" in help_text
        assert "/review security" in help_text
        assert "利用可能なレビューテンプレート" in help_text

    def test_template_has_required_fields(self, templates_dir: Path):
        loader = TemplateLoader(templates_dir)
        for t in loader.list_templates():
            assert t.name
            assert t.display_name
            assert t.system_prompt
            assert t.output_format
            assert t.parameters.temperature >= 0

    def test_missing_directory_raises(self):
        with pytest.raises(RuntimeError, match="not found"):
            TemplateLoader("/nonexistent/path")

    def test_empty_directory_raises(self):
        with tempfile.TemporaryDirectory() as d:
            with pytest.raises(RuntimeError, match="No templates"):
                TemplateLoader(d)

    def test_invalid_yaml_raises(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "bad.yaml"
            p.write_text("invalid: [")
            with pytest.raises(RuntimeError, match="Failed to load"):
                TemplateLoader(d)

    def test_checklist_structure(self, templates_dir: Path):
        loader = TemplateLoader(templates_dir)
        t = loader.get("code_quality")
        assert t is not None
        for item in t.checklist:
            assert item.id
            assert item.label
            assert len(item.points) > 0
