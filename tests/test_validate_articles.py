import sys
import textwrap
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import validate_articles as va


class TestParseFrontmatter:
    def test_basic(self):
        text = textwrap.dedent("""\
            ---
            title: My Article
            summary: A short summary
            ---
            # Body
        """)
        fm = va.parse_frontmatter(text)
        assert fm is not None
        assert fm["title"] == "My Article"

    def test_list_items(self):
        text = textwrap.dedent("""\
            ---
            topics:
              - python
              - docker
            ---
        """)
        fm = va.parse_frontmatter(text)
        assert fm["topics"] == ["python", "docker"]

    def test_no_frontmatter(self):
        assert va.parse_frontmatter("# Just a heading\nSome text") is None

    def test_unclosed(self):
        text = textwrap.dedent("""\
            ---
            title: Oops
            no closing delimiter
        """)
        assert va.parse_frontmatter(text) is None

    def test_quoted_values(self):
        text = textwrap.dedent("""\
            ---
            title: "Quoted Title"
            ---
        """)
        fm = va.parse_frontmatter(text)
        assert fm["title"] == "Quoted Title"


class TestValidateArticle:
    def _write_article(self, tmp_path, content):
        path = tmp_path / "test-article.md"
        path.write_text(textwrap.dedent(content))
        return path

    def _valid_content(self):
        return """\
            ---
            title: Test Article
            topics:
              - python
              - docker
            summary: A valid summary
            skills:
              - my-skill
            last-updated: 2026-06-12
            ---
            # Test Article

            Some content here.
        """

    def test_valid_article_passes(self, tmp_path):
        path = self._write_article(tmp_path, self._valid_content())
        errors = va.validate_article(path)
        assert errors == []

    def test_missing_frontmatter(self, tmp_path):
        path = self._write_article(tmp_path, "# No frontmatter\nSome text")
        errors = va.validate_article(path)
        assert any("frontmatter" in e for e in errors)

    def test_missing_title(self, tmp_path):
        content = """\
            ---
            topics:
              - python
            summary: A summary
            last-updated: 2026-06-12
            ---
        """
        path = self._write_article(tmp_path, content)
        errors = va.validate_article(path)
        assert any("title" in e for e in errors)

    def test_missing_topics(self, tmp_path):
        content = """\
            ---
            title: Test
            summary: A summary
            last-updated: 2026-06-12
            ---
        """
        path = self._write_article(tmp_path, content)
        errors = va.validate_article(path)
        assert any("topics" in e for e in errors)

    def test_missing_summary(self, tmp_path):
        content = """\
            ---
            title: Test
            topics:
              - python
            last-updated: 2026-06-12
            ---
        """
        path = self._write_article(tmp_path, content)
        errors = va.validate_article(path)
        assert any("summary" in e for e in errors)

    def test_missing_last_updated(self, tmp_path):
        content = """\
            ---
            title: Test
            topics:
              - python
            summary: A summary
            ---
        """
        path = self._write_article(tmp_path, content)
        errors = va.validate_article(path)
        assert any("last-updated" in e for e in errors)

    def test_empty_topics_list(self, tmp_path):
        content = """\
            ---
            title: Test
            topics:
            summary: A summary
            last-updated: 2026-06-12
            ---
        """
        path = self._write_article(tmp_path, content)
        errors = va.validate_article(path)
        assert any("empty" in e for e in errors)

    def test_empty_summary_string(self, tmp_path):
        content = """\
            ---
            title: Test
            topics:
              - python
            summary: ""
            last-updated: 2026-06-12
            ---
        """
        path = self._write_article(tmp_path, content)
        errors = va.validate_article(path)
        assert any("summary" in e and "empty" in e for e in errors)

    def test_invalid_topic_tag_uppercase(self, tmp_path):
        content = """\
            ---
            title: Test
            topics:
              - Python
            summary: A summary
            last-updated: 2026-06-12
            ---
        """
        path = self._write_article(tmp_path, content)
        errors = va.validate_article(path)
        assert any("topic" in e.lower() for e in errors)

    def test_invalid_topic_tag_underscore(self, tmp_path):
        content = """\
            ---
            title: Test
            topics:
              - python_web
            summary: A summary
            last-updated: 2026-06-12
            ---
        """
        path = self._write_article(tmp_path, content)
        errors = va.validate_article(path)
        assert any("topic" in e.lower() for e in errors)

    def test_topics_as_string_not_list(self, tmp_path):
        content = """\
            ---
            title: Test
            topics: python
            summary: A summary
            last-updated: 2026-06-12
            ---
        """
        path = self._write_article(tmp_path, content)
        errors = va.validate_article(path)
        assert any("list" in e for e in errors)

    def test_skills_as_string_not_list(self, tmp_path):
        content = """\
            ---
            title: Test
            topics:
              - python
            summary: A summary
            skills: my-skill
            last-updated: 2026-06-12
            ---
        """
        path = self._write_article(tmp_path, content)
        errors = va.validate_article(path)
        assert any("list" in e for e in errors)

    def test_invalid_skill_slug(self, tmp_path):
        content = """\
            ---
            title: Test
            topics:
              - python
            summary: A summary
            skills:
              - Invalid_Slug
            last-updated: 2026-06-12
            ---
        """
        path = self._write_article(tmp_path, content)
        errors = va.validate_article(path)
        assert any("slug" in e.lower() for e in errors)

    def test_exceeds_line_limit(self, tmp_path):
        header = ["---", "title: Test", "topics:", "  - python",
                  "summary: A summary", "last-updated: 2026-06-12", "---"]
        lines = header + ["content"] * 500
        content = "\n".join(lines)
        path = tmp_path / "test-article.md"
        path.write_text(content)
        errors = va.validate_article(path)
        assert any("line" in e and "limit" in e for e in errors)

    def test_exactly_500_lines_passes(self, tmp_path):
        header = ["---", "title: Test", "topics:", "  - python",
                  "summary: A summary", "last-updated: 2026-06-12", "---"]
        body_lines = 500 - len(header)
        lines = header + ["content"] * body_lines
        content = "\n".join(lines)
        path = tmp_path / "test-article.md"
        path.write_text(content)
        errors = va.validate_article(path)
        assert not any("line" in e and "limit" in e for e in errors)

    def test_valid_skill_slugs_pass(self, tmp_path):
        content = """\
            ---
            title: Test
            topics:
              - python
            summary: A summary
            skills:
              - build-thing
              - create-other
            last-updated: 2026-06-12
            ---
        """
        path = self._write_article(tmp_path, content)
        errors = va.validate_article(path)
        assert not any("slug" in e.lower() for e in errors)

    def test_multiple_errors_collected(self, tmp_path):
        content = """\
            ---
            topics: not-a-list
            ---
        """
        path = self._write_article(tmp_path, content)
        errors = va.validate_article(path)
        assert len(errors) >= 2
