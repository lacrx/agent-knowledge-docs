import sys
import textwrap
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import validate_skills as vs


class TestParseFrontmatter:
    def test_basic(self):
        text = textwrap.dedent("""\
            ---
            name: my-skill
            summary: A short summary
            ---
        """)
        fm = vs.parse_frontmatter(text)
        assert fm is not None
        assert fm["name"] == "my-skill"

    def test_list_items(self):
        text = textwrap.dedent("""\
            ---
            topics:
              - python
              - docker
            ---
        """)
        fm = vs.parse_frontmatter(text)
        assert fm["topics"] == ["python", "docker"]

    def test_no_frontmatter(self):
        assert vs.parse_frontmatter("# Just a heading\nSome text") is None

    def test_unclosed(self):
        text = textwrap.dedent("""\
            ---
            name: oops
            no closing delimiter
        """)
        assert vs.parse_frontmatter(text) is None


class TestValidateSkill:
    def _write_skill(self, tmp_path, content, filename="my-skill.md"):
        path = tmp_path / filename
        path.write_text(textwrap.dedent(content))
        return path

    def _valid_content(self, name="my-skill"):
        return f"""\
            ---
            name: {name}
            topics:
              - python
            summary: A valid summary
            references:
              - QUICK-REF.md
            last-updated: 2026-06-12
            ---
            # My Skill

            ## Prerequisites

            - Python 3.12+

            ## Steps

            ### Step 1: Do something

            ## Constraints

            | Constraint | Rationale |
            |---|---|

            ## Outputs

            - Output file
        """

    def _setup_refs(self, tmp_path):
        (tmp_path / "QUICK-REF.md").write_text("# Quick Ref")

    def test_valid_skill_passes(self, tmp_path):
        self._setup_refs(tmp_path)
        path = self._write_skill(tmp_path, self._valid_content())
        errors = vs.validate_skill(path, root=tmp_path)
        assert errors == []

    def test_missing_frontmatter(self, tmp_path):
        path = self._write_skill(tmp_path, "# No frontmatter\nSome text")
        errors = vs.validate_skill(path, root=tmp_path)
        assert any("frontmatter" in e for e in errors)

    def test_missing_name(self, tmp_path):
        content = """\
            ---
            topics:
              - python
            summary: A summary
            references:
              - QUICK-REF.md
            last-updated: 2026-06-12
            ---
            ## Prerequisites
            ## Steps
            ## Constraints
            ## Outputs
        """
        self._setup_refs(tmp_path)
        path = self._write_skill(tmp_path, content)
        errors = vs.validate_skill(path, root=tmp_path)
        assert any("name" in e for e in errors)

    def test_missing_topics(self, tmp_path):
        content = """\
            ---
            name: my-skill
            summary: A summary
            references:
              - QUICK-REF.md
            last-updated: 2026-06-12
            ---
            ## Prerequisites
            ## Steps
            ## Constraints
            ## Outputs
        """
        self._setup_refs(tmp_path)
        path = self._write_skill(tmp_path, content)
        errors = vs.validate_skill(path, root=tmp_path)
        assert any("topics" in e for e in errors)

    def test_missing_summary(self, tmp_path):
        content = """\
            ---
            name: my-skill
            topics:
              - python
            references:
              - QUICK-REF.md
            last-updated: 2026-06-12
            ---
            ## Prerequisites
            ## Steps
            ## Constraints
            ## Outputs
        """
        self._setup_refs(tmp_path)
        path = self._write_skill(tmp_path, content)
        errors = vs.validate_skill(path, root=tmp_path)
        assert any("summary" in e for e in errors)

    def test_missing_references(self, tmp_path):
        content = """\
            ---
            name: my-skill
            topics:
              - python
            summary: A summary
            last-updated: 2026-06-12
            ---
            ## Prerequisites
            ## Steps
            ## Constraints
            ## Outputs
        """
        path = self._write_skill(tmp_path, content)
        errors = vs.validate_skill(path, root=tmp_path)
        assert any("references" in e for e in errors)

    def test_missing_last_updated(self, tmp_path):
        content = """\
            ---
            name: my-skill
            topics:
              - python
            summary: A summary
            references:
              - QUICK-REF.md
            ---
            ## Prerequisites
            ## Steps
            ## Constraints
            ## Outputs
        """
        self._setup_refs(tmp_path)
        path = self._write_skill(tmp_path, content)
        errors = vs.validate_skill(path, root=tmp_path)
        assert any("last-updated" in e for e in errors)

    def test_name_mismatch_filename(self, tmp_path):
        content = """\
            ---
            name: wrong-name
            topics:
              - python
            summary: A summary
            references:
              - QUICK-REF.md
            last-updated: 2026-06-12
            ---
            ## Prerequisites
            ## Steps
            ## Constraints
            ## Outputs
        """
        self._setup_refs(tmp_path)
        path = self._write_skill(tmp_path, content, filename="my-skill.md")
        errors = vs.validate_skill(path, root=tmp_path)
        assert any("does not match" in e for e in errors)

    def test_invalid_topic_tag(self, tmp_path):
        content = """\
            ---
            name: my-skill
            topics:
              - Python
            summary: A summary
            references:
              - QUICK-REF.md
            last-updated: 2026-06-12
            ---
            ## Prerequisites
            ## Steps
            ## Constraints
            ## Outputs
        """
        self._setup_refs(tmp_path)
        path = self._write_skill(tmp_path, content)
        errors = vs.validate_skill(path, root=tmp_path)
        assert any("topic" in e.lower() for e in errors)

    def test_topics_as_string_not_list(self, tmp_path):
        content = """\
            ---
            name: my-skill
            topics: python
            summary: A summary
            references:
              - QUICK-REF.md
            last-updated: 2026-06-12
            ---
            ## Prerequisites
            ## Steps
            ## Constraints
            ## Outputs
        """
        self._setup_refs(tmp_path)
        path = self._write_skill(tmp_path, content)
        errors = vs.validate_skill(path, root=tmp_path)
        assert any("list" in e for e in errors)

    def test_references_as_string_not_list(self, tmp_path):
        content = """\
            ---
            name: my-skill
            topics:
              - python
            summary: A summary
            references: some-ref.md
            last-updated: 2026-06-12
            ---
            ## Prerequisites
            ## Steps
            ## Constraints
            ## Outputs
        """
        path = self._write_skill(tmp_path, content)
        errors = vs.validate_skill(path, root=tmp_path)
        assert any("list" in e for e in errors)

    def test_reference_file_not_found(self, tmp_path):
        content = """\
            ---
            name: my-skill
            topics:
              - python
            summary: A summary
            references:
              - articles/missing.md
            last-updated: 2026-06-12
            ---
            ## Prerequisites
            ## Steps
            ## Constraints
            ## Outputs
        """
        path = self._write_skill(tmp_path, content)
        errors = vs.validate_skill(path, root=tmp_path)
        assert any("not found" in e for e in errors)

    def test_reference_file_exists_passes(self, tmp_path):
        ref_dir = tmp_path / "articles"
        ref_dir.mkdir()
        (ref_dir / "existing.md").write_text("# Exists")

        content = """\
            ---
            name: my-skill
            topics:
              - python
            summary: A summary
            references:
              - articles/existing.md
            last-updated: 2026-06-12
            ---
            ## Prerequisites
            ## Steps
            ## Constraints
            ## Outputs
        """
        path = self._write_skill(tmp_path, content)
        errors = vs.validate_skill(path, root=tmp_path)
        assert not any("not found" in e for e in errors)

    def test_missing_prerequisites_section(self, tmp_path):
        content = """\
            ---
            name: my-skill
            topics:
              - python
            summary: A summary
            references:
              - QUICK-REF.md
            last-updated: 2026-06-12
            ---
            ## Steps
            ## Constraints
            ## Outputs
        """
        self._setup_refs(tmp_path)
        path = self._write_skill(tmp_path, content)
        errors = vs.validate_skill(path, root=tmp_path)
        assert any("Prerequisites" in e for e in errors)

    def test_missing_steps_section(self, tmp_path):
        content = """\
            ---
            name: my-skill
            topics:
              - python
            summary: A summary
            references:
              - QUICK-REF.md
            last-updated: 2026-06-12
            ---
            ## Prerequisites
            ## Constraints
            ## Outputs
        """
        self._setup_refs(tmp_path)
        path = self._write_skill(tmp_path, content)
        errors = vs.validate_skill(path, root=tmp_path)
        assert any("Steps" in e for e in errors)

    def test_missing_constraints_section(self, tmp_path):
        content = """\
            ---
            name: my-skill
            topics:
              - python
            summary: A summary
            references:
              - QUICK-REF.md
            last-updated: 2026-06-12
            ---
            ## Prerequisites
            ## Steps
            ## Outputs
        """
        self._setup_refs(tmp_path)
        path = self._write_skill(tmp_path, content)
        errors = vs.validate_skill(path, root=tmp_path)
        assert any("Constraints" in e for e in errors)

    def test_missing_outputs_section(self, tmp_path):
        content = """\
            ---
            name: my-skill
            topics:
              - python
            summary: A summary
            references:
              - QUICK-REF.md
            last-updated: 2026-06-12
            ---
            ## Prerequisites
            ## Steps
            ## Constraints
        """
        self._setup_refs(tmp_path)
        path = self._write_skill(tmp_path, content)
        errors = vs.validate_skill(path, root=tmp_path)
        assert any("Outputs" in e for e in errors)

    def test_section_inside_code_block_not_counted(self, tmp_path):
        content = """\
            ---
            name: my-skill
            topics:
              - python
            summary: A summary
            references:
              - QUICK-REF.md
            last-updated: 2026-06-12
            ---
            ## Prerequisites

            ```markdown
            ## Steps
            ```

            ## Constraints
            ## Outputs
        """
        self._setup_refs(tmp_path)
        path = self._write_skill(tmp_path, content)
        errors = vs.validate_skill(path, root=tmp_path)
        assert any("Steps" in e for e in errors)

    def test_exceeds_line_limit(self, tmp_path):
        header = ["---", "name: my-skill", "topics:", "  - python",
                  "summary: A summary", "references:", "  - QUICK-REF.md",
                  "last-updated: 2026-06-12", "---",
                  "## Prerequisites", "## Steps", "## Constraints", "## Outputs"]
        lines = header + ["content"] * 500
        content = "\n".join(lines)
        self._setup_refs(tmp_path)
        path = tmp_path / "my-skill.md"
        path.write_text(content)
        errors = vs.validate_skill(path, root=tmp_path)
        assert any("line" in e and "limit" in e for e in errors)

    def test_empty_topics_list(self, tmp_path):
        content = """\
            ---
            name: my-skill
            topics:
            summary: A summary
            references:
              - QUICK-REF.md
            last-updated: 2026-06-12
            ---
            ## Prerequisites
            ## Steps
            ## Constraints
            ## Outputs
        """
        self._setup_refs(tmp_path)
        path = self._write_skill(tmp_path, content)
        errors = vs.validate_skill(path, root=tmp_path)
        assert any("empty" in e for e in errors)

    def test_multiple_errors_collected(self, tmp_path):
        content = """\
            ---
            topics: not-a-list
            ---
        """
        path = self._write_skill(tmp_path, content)
        errors = vs.validate_skill(path, root=tmp_path)
        assert len(errors) >= 2


class TestFindSkills:
    def test_no_dir(self, tmp_path, monkeypatch):
        monkeypatch.setattr(vs, "SKILLS_DIR", tmp_path / "nonexistent")
        assert vs.find_skills() == []

    def test_with_files(self, tmp_path, monkeypatch):
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        (skills_dir / "s1.md").write_text("# S1")
        (skills_dir / "s2.md").write_text("# S2")
        monkeypatch.setattr(vs, "SKILLS_DIR", skills_dir)
        result = vs.find_skills()
        assert len(result) == 2

    def test_empty_dir(self, tmp_path, monkeypatch):
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        monkeypatch.setattr(vs, "SKILLS_DIR", skills_dir)
        assert vs.find_skills() == []
