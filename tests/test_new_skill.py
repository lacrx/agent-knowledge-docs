import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import new_skill as ns


class TestSlugPattern:
    def test_valid_simple(self):
        assert ns.SLUG_PATTERN.match("my-skill")

    def test_valid_single_word(self):
        assert ns.SLUG_PATTERN.match("skill")

    def test_valid_with_numbers(self):
        assert ns.SLUG_PATTERN.match("my-skill-2")

    def test_invalid_uppercase(self):
        assert not ns.SLUG_PATTERN.match("My-Skill")

    def test_invalid_underscore(self):
        assert not ns.SLUG_PATTERN.match("my_skill")

    def test_invalid_leading_hyphen(self):
        assert not ns.SLUG_PATTERN.match("-my-skill")

    def test_invalid_trailing_hyphen(self):
        assert not ns.SLUG_PATTERN.match("my-skill-")

    def test_invalid_double_hyphen(self):
        assert not ns.SLUG_PATTERN.match("my--skill")

    def test_invalid_spaces(self):
        assert not ns.SLUG_PATTERN.match("my skill")

    def test_invalid_dots(self):
        assert not ns.SLUG_PATTERN.match("my.skill")

    def test_invalid_empty(self):
        assert not ns.SLUG_PATTERN.match("")


class TestCreateSkill:
    def test_creates_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr(ns, "SKILLS_DIR", tmp_path / "skills")
        path = ns.create_skill("my-skill")
        assert path.exists()

    def test_creates_skills_dir(self, tmp_path, monkeypatch):
        skills_dir = tmp_path / "skills"
        monkeypatch.setattr(ns, "SKILLS_DIR", skills_dir)
        ns.create_skill("my-skill")
        assert skills_dir.is_dir()

    def test_file_has_frontmatter(self, tmp_path, monkeypatch):
        monkeypatch.setattr(ns, "SKILLS_DIR", tmp_path / "skills")
        path = ns.create_skill("my-skill")
        content = path.read_text()
        assert content.startswith("---")

    def test_has_template_sections(self, tmp_path, monkeypatch):
        monkeypatch.setattr(ns, "SKILLS_DIR", tmp_path / "skills")
        path = ns.create_skill("my-skill")
        content = path.read_text()
        assert "## Prerequisites" in content
        assert "## Steps" in content
        assert "## Constraints" in content
        assert "## Outputs" in content

    def test_date_in_frontmatter(self, tmp_path, monkeypatch):
        monkeypatch.setattr(ns, "SKILLS_DIR", tmp_path / "skills")
        path = ns.create_skill("my-skill")
        content = path.read_text()
        assert "last-updated:" in content

    def test_duplicate_raises(self, tmp_path, monkeypatch):
        monkeypatch.setattr(ns, "SKILLS_DIR", tmp_path / "skills")
        ns.create_skill("my-skill")
        with pytest.raises(FileExistsError):
            ns.create_skill("my-skill")

    def test_invalid_name_raises(self, tmp_path, monkeypatch):
        monkeypatch.setattr(ns, "SKILLS_DIR", tmp_path / "skills")
        with pytest.raises(ValueError):
            ns.create_skill("Invalid Name")

    def test_invalid_name_uppercase_raises(self, tmp_path, monkeypatch):
        monkeypatch.setattr(ns, "SKILLS_DIR", tmp_path / "skills")
        with pytest.raises(ValueError):
            ns.create_skill("My-Skill")

    def test_name_appears_in_frontmatter(self, tmp_path, monkeypatch):
        monkeypatch.setattr(ns, "SKILLS_DIR", tmp_path / "skills")
        path = ns.create_skill("my-skill")
        content = path.read_text()
        assert "name: my-skill" in content
