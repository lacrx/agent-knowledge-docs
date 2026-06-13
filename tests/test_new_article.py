import sys
import textwrap
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import new_article as na


class TestSlugPattern:
    def test_valid_simple(self):
        assert na.SLUG_PATTERN.match("my-article")

    def test_valid_single_word(self):
        assert na.SLUG_PATTERN.match("article")

    def test_valid_with_numbers(self):
        assert na.SLUG_PATTERN.match("my-article-2")

    def test_valid_numbers_only(self):
        assert na.SLUG_PATTERN.match("123")

    def test_invalid_uppercase(self):
        assert not na.SLUG_PATTERN.match("My-Article")

    def test_invalid_underscore(self):
        assert not na.SLUG_PATTERN.match("my_article")

    def test_invalid_leading_hyphen(self):
        assert not na.SLUG_PATTERN.match("-my-article")

    def test_invalid_trailing_hyphen(self):
        assert not na.SLUG_PATTERN.match("my-article-")

    def test_invalid_double_hyphen(self):
        assert not na.SLUG_PATTERN.match("my--article")

    def test_invalid_empty(self):
        assert not na.SLUG_PATTERN.match("")

    def test_invalid_spaces(self):
        assert not na.SLUG_PATTERN.match("my article")

    def test_invalid_dots(self):
        assert not na.SLUG_PATTERN.match("my.article")


class TestListCategories:
    def test_returns_sorted_dirs(self, tmp_path, monkeypatch):
        articles_dir = tmp_path / "articles"
        articles_dir.mkdir()
        (articles_dir / "zebra").mkdir()
        (articles_dir / "alpha").mkdir()
        monkeypatch.setattr(na, "ARTICLES_DIR", articles_dir)
        result = na.list_categories()
        assert result == ["alpha", "zebra"]

    def test_ignores_files(self, tmp_path, monkeypatch):
        articles_dir = tmp_path / "articles"
        articles_dir.mkdir()
        (articles_dir / "category").mkdir()
        (articles_dir / "readme.md").write_text("# Readme")
        monkeypatch.setattr(na, "ARTICLES_DIR", articles_dir)
        result = na.list_categories()
        assert result == ["category"]

    def test_no_articles_dir(self, tmp_path, monkeypatch):
        monkeypatch.setattr(na, "ARTICLES_DIR", tmp_path / "nonexistent")
        assert na.list_categories() == []

    def test_empty_articles_dir(self, tmp_path, monkeypatch):
        articles_dir = tmp_path / "articles"
        articles_dir.mkdir()
        monkeypatch.setattr(na, "ARTICLES_DIR", articles_dir)
        assert na.list_categories() == []


class TestCreateArticle:
    def test_creates_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr(na, "ARTICLES_DIR", tmp_path / "articles")
        path = na.create_article("my-article", "testing")
        assert path.exists()

    def test_file_has_frontmatter(self, tmp_path, monkeypatch):
        monkeypatch.setattr(na, "ARTICLES_DIR", tmp_path / "articles")
        path = na.create_article("my-article", "testing")
        content = path.read_text()
        assert content.startswith("---")

    def test_title_derived_from_slug(self, tmp_path, monkeypatch):
        monkeypatch.setattr(na, "ARTICLES_DIR", tmp_path / "articles")
        path = na.create_article("my-cool-article", "testing")
        content = path.read_text()
        assert "My Cool Article" in content

    def test_creates_category_dir(self, tmp_path, monkeypatch):
        articles_dir = tmp_path / "articles"
        monkeypatch.setattr(na, "ARTICLES_DIR", articles_dir)
        na.create_article("my-article", "new-category")
        assert (articles_dir / "new-category").is_dir()

    def test_duplicate_raises(self, tmp_path, monkeypatch):
        monkeypatch.setattr(na, "ARTICLES_DIR", tmp_path / "articles")
        na.create_article("my-article", "testing")
        with pytest.raises(FileExistsError):
            na.create_article("my-article", "testing")

    def test_invalid_name_raises(self, tmp_path, monkeypatch):
        monkeypatch.setattr(na, "ARTICLES_DIR", tmp_path / "articles")
        with pytest.raises(ValueError):
            na.create_article("Invalid Name", "testing")

    def test_invalid_category_raises(self, tmp_path, monkeypatch):
        monkeypatch.setattr(na, "ARTICLES_DIR", tmp_path / "articles")
        with pytest.raises(ValueError):
            na.create_article("my-article", "Invalid_Category")

    def test_has_template_sections(self, tmp_path, monkeypatch):
        monkeypatch.setattr(na, "ARTICLES_DIR", tmp_path / "articles")
        path = na.create_article("my-article", "testing")
        content = path.read_text()
        assert "## Overview" in content
        assert "## Details" in content
        assert "## Trade-offs" in content
        assert "## References" in content

    def test_date_in_frontmatter(self, tmp_path, monkeypatch):
        monkeypatch.setattr(na, "ARTICLES_DIR", tmp_path / "articles")
        path = na.create_article("my-article", "testing")
        content = path.read_text()
        assert "last-updated:" in content
