import sys
import textwrap
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import generate_topic_index as gen


class TestParseFrontmatter:
    def test_basic_key_value(self):
        text = textwrap.dedent("""\
            ---
            title: My Article
            summary: A short summary
            ---
            # Body
        """)
        fm = gen.parse_frontmatter(text)
        assert fm is not None
        assert fm["title"] == "My Article"
        assert fm["summary"] == "A short summary"

    def test_list_values(self):
        text = textwrap.dedent("""\
            ---
            title: Test
            topics:
              - python
              - docker
            ---
        """)
        fm = gen.parse_frontmatter(text)
        assert fm["topics"] == ["python", "docker"]

    def test_quoted_values_stripped(self):
        text = textwrap.dedent("""\
            ---
            title: "Quoted Title"
            name: 'single-quoted'
            ---
        """)
        fm = gen.parse_frontmatter(text)
        assert fm["title"] == "Quoted Title"
        assert fm["name"] == "single-quoted"

    def test_no_frontmatter_returns_none(self):
        assert gen.parse_frontmatter("# Just a heading\nSome text") is None

    def test_unclosed_frontmatter_returns_none(self):
        text = textwrap.dedent("""\
            ---
            title: Oops
            no closing delimiter
        """)
        assert gen.parse_frontmatter(text) is None

    def test_empty_list_field(self):
        text = textwrap.dedent("""\
            ---
            skills: []
            ---
        """)
        fm = gen.parse_frontmatter(text)
        assert fm["skills"] == "[]"

    def test_empty_list_via_items(self):
        text = textwrap.dedent("""\
            ---
            topics:
            ---
        """)
        fm = gen.parse_frontmatter(text)
        assert fm["topics"] == []

    def test_mixed_inline_and_list(self):
        text = textwrap.dedent("""\
            ---
            title: Mixed
            topics:
              - alpha
              - beta
            summary: inline value
            ---
        """)
        fm = gen.parse_frontmatter(text)
        assert fm["title"] == "Mixed"
        assert fm["topics"] == ["alpha", "beta"]
        assert fm["summary"] == "inline value"


class TestStripQuotes:
    def test_double_quotes(self):
        assert gen._strip_quotes('"hello"') == "hello"

    def test_single_quotes(self):
        assert gen._strip_quotes("'world'") == "world"

    def test_no_quotes(self):
        assert gen._strip_quotes("plain") == "plain"

    def test_mismatched_quotes_unchanged(self):
        assert gen._strip_quotes("\"mixed'") == "\"mixed'"

    def test_whitespace_stripped(self):
        assert gen._strip_quotes("  padded  ") == "padded"


class TestTruncateSummary:
    def test_short_summary_unchanged(self):
        assert gen._truncate_summary("Short") == "Short"

    def test_long_summary_truncated(self):
        long_text = "x" * 200
        result = gen._truncate_summary(long_text, max_len=120)
        assert len(result) <= 120
        assert result.endswith("...")

    def test_exact_length_no_truncation(self):
        text = "a" * 120
        assert gen._truncate_summary(text, max_len=120) == text

    def test_multiline_collapsed(self):
        text = "line one\n  line two\n  line three"
        result = gen._truncate_summary(text)
        assert "\n" not in result
        assert "  " not in result


class TestBuildTopicIndex:
    def test_groups_by_topic(self):
        entries = [
            {"title": "A", "topics": ["python", "docker"]},
            {"title": "B", "topics": ["python"]},
        ]
        index = gen.build_topic_index(entries)
        assert len(index["python"]) == 2
        assert len(index["docker"]) == 1

    def test_empty_entries(self):
        assert gen.build_topic_index([]) == {}

    def test_entry_with_no_topics(self):
        entries = [{"title": "A", "topics": []}]
        assert gen.build_topic_index(entries) == {}


class TestGenerateTopicIndex:
    def test_output_has_header(self):
        entries = [
            {"stem": "my-art", "path": "articles/cat/my-art.md",
             "topics": ["python"], "skills": ["build-thing"],
             "aliases": []}
        ]
        result = gen.generate_topic_index(entries)
        assert "# Topic Index" in result

    def test_topics_in_heading(self):
        entries = [
            {"stem": "my-art", "path": "articles/cat/my-art.md",
             "topics": ["python", "docker"], "skills": [],
             "aliases": []}
        ]
        result = gen.generate_topic_index(entries)
        assert "## python / docker" in result

    def test_no_topics_uses_stem(self):
        entries = [
            {"stem": "fallback", "path": "articles/cat/fallback.md",
             "topics": [], "skills": [], "aliases": []}
        ]
        result = gen.generate_topic_index(entries)
        assert "## fallback" in result

    def test_skills_none_marker(self):
        entries = [
            {"stem": "x", "path": "articles/cat/x.md",
             "topics": ["t"], "skills": [], "aliases": []}
        ]
        result = gen.generate_topic_index(entries)
        assert "_(none)_" in result

    def test_aliases_shown_when_present(self):
        entries = [
            {"stem": "x", "path": "articles/cat/x.md",
             "topics": ["t"], "skills": [],
             "aliases": ["alias1", "alias2"]}
        ]
        result = gen.generate_topic_index(entries)
        assert "Aliases: alias1, alias2" in result

    def test_aliases_hidden_when_empty(self):
        entries = [
            {"stem": "x", "path": "articles/cat/x.md",
             "topics": ["t"], "skills": [], "aliases": []}
        ]
        result = gen.generate_topic_index(entries)
        assert "Aliases" not in result

    def test_empty_entries(self):
        result = gen.generate_topic_index([])
        assert "# Topic Index" in result


class TestGenerateQuickRef:
    def test_table_header(self):
        result = gen.generate_quick_ref([])
        assert "| Topics | Article | Skills |" in result

    def test_entry_row_format(self):
        entries = [
            {"stem": "my-art", "path": "articles/cat/my-art.md",
             "topics": ["python", "docker"], "skills": ["build-thing"],
             "aliases": []}
        ]
        result = gen.generate_quick_ref(entries)
        assert "python, docker" in result
        assert "[my-art](articles/cat/my-art.md)" in result
        assert "[build-thing](skills/build-thing.md)" in result

    def test_no_skills_shows_none(self):
        entries = [
            {"stem": "x", "path": "articles/cat/x.md",
             "topics": ["t"], "skills": [], "aliases": []}
        ]
        result = gen.generate_quick_ref(entries)
        assert "_(none)_" in result

    def test_sorted_output(self):
        entries = [
            {"stem": "b", "path": "articles/cat/b.md",
             "topics": ["t"], "skills": [], "aliases": []},
            {"stem": "a", "path": "articles/cat/a.md",
             "topics": ["t"], "skills": [], "aliases": []},
        ]
        result = gen.generate_quick_ref(entries)
        lines = result.strip().splitlines()
        data_lines = [l for l in lines if l.startswith("| ") and "Topics" not in l and "---" not in l]
        assert len(data_lines) == 2


class TestFindArticlesAndSkills:
    def test_find_articles_no_dir(self, tmp_path, monkeypatch):
        monkeypatch.setattr(gen, "ARTICLES_DIR", tmp_path / "nonexistent")
        assert gen.find_articles() == []

    def test_find_articles_with_files(self, tmp_path, monkeypatch):
        articles_dir = tmp_path / "articles"
        articles_dir.mkdir()
        (articles_dir / "one.md").write_text("# One")
        (articles_dir / "two.md").write_text("# Two")
        monkeypatch.setattr(gen, "ARTICLES_DIR", articles_dir)
        result = gen.find_articles()
        assert len(result) == 2
        assert result == sorted(result)

    def test_find_skills_no_dir(self, tmp_path, monkeypatch):
        monkeypatch.setattr(gen, "SKILLS_DIR", tmp_path / "nonexistent")
        assert gen.find_skills() == []

    def test_find_skills_with_files(self, tmp_path, monkeypatch):
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        (skills_dir / "s1.md").write_text("# S1")
        (skills_dir / "s2.md").write_text("# S2")
        monkeypatch.setattr(gen, "SKILLS_DIR", skills_dir)
        result = gen.find_skills()
        assert len(result) == 2


class TestBuildArticleIndex:
    def test_builds_from_articles(self, tmp_path, monkeypatch):
        articles_dir = tmp_path / "articles" / "cat"
        articles_dir.mkdir(parents=True)
        monkeypatch.setattr(gen, "ARTICLES_DIR", tmp_path / "articles")
        monkeypatch.setattr(gen, "ROOT", tmp_path)

        content = textwrap.dedent("""\
            ---
            title: Test Article
            topics:
              - python
            summary: A test
            skills:
              - my-skill
            aliases:
              - test-alias
            ---
            # Body
        """)
        (articles_dir / "test-article.md").write_text(content)
        entries = gen.build_article_index()
        assert len(entries) == 1
        assert entries[0]["title"] == "Test Article"
        assert entries[0]["topics"] == ["python"]
        assert entries[0]["skills"] == ["my-skill"]
        assert entries[0]["aliases"] == ["test-alias"]

    def test_skips_files_without_frontmatter(self, tmp_path, monkeypatch):
        articles_dir = tmp_path / "articles"
        articles_dir.mkdir()
        monkeypatch.setattr(gen, "ARTICLES_DIR", articles_dir)
        monkeypatch.setattr(gen, "ROOT", tmp_path)
        (articles_dir / "no-fm.md").write_text("# No frontmatter here")
        entries = gen.build_article_index()
        assert entries == []

    def test_sorted_by_path(self, tmp_path, monkeypatch):
        articles_dir = tmp_path / "articles"
        articles_dir.mkdir()
        monkeypatch.setattr(gen, "ARTICLES_DIR", articles_dir)
        monkeypatch.setattr(gen, "ROOT", tmp_path)

        for name in ["zebra", "alpha"]:
            content = textwrap.dedent(f"""\
                ---
                title: {name}
                topics:
                  - t
                summary: s
                ---
            """)
            (articles_dir / f"{name}.md").write_text(content)

        entries = gen.build_article_index()
        paths = [e["path"] for e in entries]
        assert paths == sorted(paths)

    def test_empty_dir(self, tmp_path, monkeypatch):
        articles_dir = tmp_path / "articles"
        articles_dir.mkdir()
        monkeypatch.setattr(gen, "ARTICLES_DIR", articles_dir)
        monkeypatch.setattr(gen, "ROOT", tmp_path)
        assert gen.build_article_index() == []
