import sys
import textwrap
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import kb  # noqa: E402

AGENT_CLAUDE = textwrap.dedent("""\
    # Knowledge Base Agent Instructions

    ## When to Fetch
    Only fetch KB content when the task involves: python, testing, agent-workflow, docker, fastapi, aws, fargate.
    If the task does not involve these topics, skip KB lookup entirely.

    ## How to Fetch
    Fetch files with gh api.
""")

POLICY_CLAUDE = textwrap.dedent("""\
    # Policy Knowledge Base Agent Instructions

    ## When to Fetch (Continuous)
    Fetch whenever the task touches: ca-housing-law, land-use-analysis, sb-79, adu-law.

    Unlike engineering knowledge bases (fetched once during planning), this KB is a runtime reference.

    ## How to Fetch
""")

QUICK_REF = textwrap.dedent("""\
    <!-- auto-generated -->
    # Quick Reference

    | Topics | Article | Skills |
    |--------|---------|--------|
    | ssh, keys, hardening | [ssh](articles/networking/ssh.md) | — |
    | vm, rdp, autostart | [vm-lifecycle](articles/vm-management/vm-lifecycle.md) | [boot](skills/boot.md), [boot](skills/boot.md) |
    | neovim, nvim, claude-code | [nvim-config](tools/nvim-config/README.md) | — |
""")


class TestParseWhenToFetch:
    def test_planning_kb(self):
        topics, mode = kb.parse_when_to_fetch(AGENT_CLAUDE)
        assert topics == ["python", "testing", "agent-workflow", "docker", "fastapi", "aws", "fargate"]
        assert mode == "planning"

    def test_continuous_kb_stops_at_sentence_end(self):
        topics, mode = kb.parse_when_to_fetch(POLICY_CLAUDE)
        assert topics == ["ca-housing-law", "land-use-analysis", "sb-79", "adu-law"]
        assert mode == "continuous"

    def test_no_section(self):
        assert kb.parse_when_to_fetch("# Docs\n\n## Fetching content\n") == ([], "always")


class TestParseRows:
    def test_rows_tags_and_unique_paths(self):
        rows = kb.parse_rows(QUICK_REF)
        assert len(rows) == 3
        assert rows[0]["tags"] == ["ssh", "keys", "hardening"]
        assert rows[1]["paths"] == ["articles/vm-management/vm-lifecycle.md", "skills/boot.md"]

    def test_skips_header_and_separator(self):
        assert all(r["tags"][0] != "topics" for r in kb.parse_rows(QUICK_REF))


class TestTermIn:
    def test_whole_word(self):
        assert kb.term_in("vm", kb._norm("restart the VM please"))
        assert not kb.term_in("vm", kb._norm("the vmware host"))

    def test_plural_and_ing_forms(self):
        assert kb.term_in("doors", kb._norm("add a door on the south wall"))
        assert kb.term_in("drawing", kb._norm("draw a bedroom"))
        assert kb.term_in("testing", kb._norm("add pytest tests"))
        assert not kb.term_in("class", kb._norm("the cla module"))

    def test_hyphenated_matches_spaces(self):
        assert kb.term_in("claude-code", kb._norm("claude code in nvim"))
        assert kb.term_in("sb-79", kb._norm("does SB 79 apply"))


def _kbs():
    return [
        {"kb": "lan", "repo": "lan-knowledge-docs", "branch": "main", "description": "",
         "topics": ["ssh", "workhorse"], "mode": "planning"},
        {"kb": "policy", "repo": "policy-knowledge-docs", "branch": "master", "description": "",
         "topics": ["sb-79"], "mode": "continuous"},
    ]


class TestRoute:
    def fetch(self, k):
        return QUICK_REF if k["kb"] == "lan" else "| Topics | Article | Skills |\n|---|---|---|\n"

    def test_gate_and_rows(self):
        res = kb.route("harden ssh keys on workhorse", _kbs(), fetch_index=self.fetch)
        assert [r["kb"]["kb"] for r in res] == ["lan"]
        assert res[0]["gate"] == ["ssh", "workhorse"]
        assert res[0]["rows"][0][2]["paths"] == ["articles/networking/ssh.md"]

    def test_policy_gate_without_rows(self):
        res = kb.route("does SB 79 allow this project", _kbs(), fetch_index=self.fetch)
        assert [r["kb"]["kb"] for r in res] == ["policy"]
        assert res[0]["rows"] == []

    def test_skip(self):
        assert kb.route("write a haiku about autumn", _kbs(), fetch_index=self.fetch) == []


class TestTopicCap:
    def test_fetches_at_most_max(self, monkeypatch, capsys):
        many = "| Topics | Article | Skills |\n|---|---|---|\n" + "".join(
            "| vm | [a%d](articles/a%d.md) | — |\n" % (i, i) for i in range(8))
        fetched = []
        monkeypatch.setattr(kb, "quick_ref", lambda k: many)
        monkeypatch.setattr(kb, "raw", lambda repo, path, branch: fetched.append(path) or "body")
        kb.cmd_topic(_kbs(), ["lan", "vm", "--max", "3"])
        out = capsys.readouterr().out
        assert fetched == ["articles/a0.md", "articles/a1.md", "articles/a2.md"]
        assert "not fetched" in out and "articles/a7.md" in out


class TestKbByName:
    def test_short_and_repo_name(self):
        assert kb.kb_by_name("policy", _kbs())["branch"] == "master"
        assert kb.kb_by_name("lan-knowledge-docs", _kbs())["kb"] == "lan"

    def test_unknown(self):
        try:
            kb.kb_by_name("nope", _kbs())
        except kb.KbError as e:
            assert "have: lan, policy" in str(e)
        else:
            raise AssertionError("expected KbError")
