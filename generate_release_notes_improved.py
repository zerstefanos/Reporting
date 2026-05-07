#!/usr/bin/env python3
"""
Generate release-notes.html for a Power BI project.

The report combines git history with lightweight project inspection so the
release note is useful even when older commits do not follow Conventional
Commits. The generated HTML is safe to publish as a static artifact.

Examples:
    python generate_release_notes_improved.py --repo .
    python generate_release_notes_improved.py --repo . --out release-notes.html
    python generate_release_notes_improved.py --repo . --title "Reporting Release Notes"
    python generate_release_notes_improved.py --repo . --ref-url-template "https://github.com/org/repo/issues/{ref}"
"""

from __future__ import annotations

import argparse
import html
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, Iterator

COMMIT_TYPE_MAP = {
    "feat": "feat",
    "feature": "feat",
    "fix": "fix",
    "bugfix": "fix",
    "hotfix": "fix",
    "revert": "fix",
    "remove": "removed",
    "removed": "removed",
    "deprecate": "removed",
    "deprecated": "removed",
    "refactor": "maint",
    "chore": "maint",
    "build": "maint",
    "ci": "maint",
    "docs": "maint",
    "test": "maint",
    "perf": "maint",
    "style": "maint",
    "data": "data",
}

CATEGORY_LABEL = {
    "feat": "Feature",
    "fix": "Fix",
    "removed": "Removed",
    "maint": "Maintenance",
    "data": "Data",
}

BADGE_CLASS = {
    "feat": "badge-feat",
    "fix": "badge-fix",
    "removed": "badge-removed",
    "maint": "badge-maint",
    "data": "badge-data",
}

CATEGORY_ORDER = {"feat": 0, "fix": 1, "data": 2, "removed": 3, "maint": 4}

CC_RE = re.compile(
    r"^(?P<type>[a-zA-Z]+)(?:\([^)]*\))?(?P<breaking>!)?\s*:\s*(?P<desc>.+)$"
)
MERGE_BRANCH_RE = re.compile(r"[Mm]erge\s+branch\s+[\"'](?P<branch>[^\"']+)[\"']")
MERGE_PR_RE = re.compile(r"[Mm]erge\s+pull\s+request\s+#(?P<pr>\d+)\s+from\s+[^/]+/(?P<branch>.+)")
BUG_RE = re.compile(r"(?<![A-Za-z0-9_])(BUG-\d+|ISSUE-\d+|#\d+)(?![A-Za-z0-9_])", re.IGNORECASE)
GENERIC_SKIP_RE = re.compile(r"^(merge remote-tracking branch|merge branch ['\"]?release/)", re.IGNORECASE)


@dataclass(frozen=True)
class Entry:
    category: str
    description: str
    refs: tuple[str, ...] = ()


@dataclass(frozen=True)
class Release:
    version: str
    date: str
    entries: list[Entry]
    upcoming: bool = False


@dataclass(frozen=True)
class ProjectSummary:
    pages: list[str]
    visuals: dict[str, int]
    tables: dict[str, int]
    data_sources: list[str]


# Git helpers are kept small and explicit so failures are easy to understand.
def git(repo: Path, *args: str) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True,
            text=True,
            check=True,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("Git is not installed or not available on PATH.") from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "").strip()
        cmd = "git " + " ".join(args)
        raise RuntimeError(f"Command failed: {cmd}\n{detail}") from exc
    return result.stdout.strip()


def is_git_repo(repo: Path) -> bool:
    try:
        return git(repo, "rev-parse", "--is-inside-work-tree") == "true"
    except RuntimeError:
        return False


def get_tags(repo: Path) -> list[str]:
    raw = git(repo, "tag", "--sort=-version:refname", "--list", "v[0-9]*")
    return [tag for tag in raw.splitlines() if tag]


def tag_date(repo: Path, tag: str) -> str:
    ts = git(repo, "log", "-1", "--format=%cI", tag)
    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    return dt.strftime("%Y-%m-%d")


def commits_between(repo: Path, from_ref: str | None, to_ref: str) -> list[str]:
    rev_range = f"{from_ref}..{to_ref}" if from_ref else to_ref
    raw = git(repo, "log", rev_range, "--pretty=format:%s")
    return [line.strip() for line in raw.splitlines() if line.strip()]


# Commit parsing is based on the real change commits. Git Flow merge commits are
# release bookkeeping, so they are skipped to avoid double-counting features.
def parse_commit(msg: str) -> Entry | None:
    if GENERIC_SKIP_RE.match(msg):
        return None

    conventional = CC_RE.match(msg)
    if conventional:
        commit_type = conventional.group("type").lower()
        category = COMMIT_TYPE_MAP.get(commit_type)
        if category is None:
            return None
        desc = conventional.group("desc").strip()
        if conventional.group("breaking") == "!":
            desc = f"BREAKING: {desc}"
        return Entry(category, clean_desc(desc), extract_refs(desc))

    if MERGE_PR_RE.search(msg) or MERGE_BRANCH_RE.search(msg):
        return None

    if msg.lower().startswith("fix "):
        return Entry("fix", clean_desc(msg[4:]))
    if msg.lower().startswith(("add ", "added ")):
        return Entry("feat", clean_desc(msg))
    if "data" in msg.lower():
        return Entry("data", clean_desc(msg))

    return None


def category_from_branch(branch: str) -> str | None:
    prefix = branch.split("/", 1)[0].lower()
    if prefix in {"feature", "feat", "ft"}:
        return "feat"
    if prefix in {"fix", "bugfix", "hotfix"}:
        return "fix"
    if prefix in {"data", "dataset"}:
        return "data"
    if prefix in {"release", "main", "develop"}:
        return None
    return "maint"


def branch_summary(branch: str) -> str:
    name = branch.split("/", 1)[-1]
    name = re.sub(r"[-_]+", " ", name).strip()
    return name[:1].upper() + name[1:] if name else "Branch update"


def extract_refs(text: str) -> tuple[str, ...]:
    refs: list[str] = []
    for match in BUG_RE.finditer(text):
        ref = match.group(0).upper()
        if ref not in refs:
            refs.append(ref)
    return tuple(refs)


def clean_desc(text: str) -> str:
    cleaned = BUG_RE.sub("", text)
    cleaned = re.sub(r"\s+", " ", cleaned)
    cleaned = re.sub(r"\s+([,.;:])", r"\1", cleaned)
    return cleaned.strip(" .-,;") or "No description provided"


def parse_entries(commits: Iterable[str]) -> list[Entry]:
    seen: set[tuple[str, str, tuple[str, ...]]] = set()
    entries: list[Entry] = []
    for commit in commits:
        entry = parse_commit(commit)
        if entry is None:
            continue
        key = (entry.category, entry.description.lower(), entry.refs)
        if key in seen:
            continue
        seen.add(key)
        entries.append(entry)
    return sorted(entries, key=lambda item: (CATEGORY_ORDER[item.category], item.description.lower()))


# Project inspection adds release context that cannot be recovered from commits.
def inspect_project(repo: Path) -> ProjectSummary:
    report_dir = find_report_dir(repo)
    model_dir = find_model_dir(repo)
    pages = read_pages(report_dir) if report_dir else []
    visuals = count_visuals(report_dir) if report_dir else {}
    tables = read_tables(model_dir) if model_dir else {}
    data_sources = read_data_sources(model_dir) if model_dir else []
    return ProjectSummary(pages=pages, visuals=visuals, tables=tables, data_sources=data_sources)


def find_report_dir(repo: Path) -> Path | None:
    for pbip_path in repo.glob("*.pbip"):
        data = read_json(pbip_path)
        for artifact in data.get("artifacts", []):
            report = artifact.get("report")
            if report and report.get("path"):
                candidate = repo / report["path"]
                if candidate.exists():
                    return candidate
    return next(repo.glob("*.Report"), None)


def find_model_dir(repo: Path) -> Path | None:
    return next(repo.glob("*.SemanticModel"), None)


def read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}


def read_pages(report_dir: Path) -> list[str]:
    pages_root = report_dir / "definition" / "pages"
    metadata = read_json(pages_root / "pages.json")
    page_order = metadata.get("pageOrder") or []
    pages: list[str] = []

    for page_id in page_order:
        page = read_json(pages_root / page_id / "page.json")
        display_name = page.get("displayName") or page.get("name") or page_id
        pages.append(str(display_name))

    if pages:
        return pages

    for page_file in sorted(pages_root.glob("*/page.json")):
        page = read_json(page_file)
        pages.append(str(page.get("displayName") or page.get("name") or page_file.parent.name))
    return pages


def count_visuals(report_dir: Path) -> dict[str, int]:
    counts: dict[str, int] = {}
    for visual_file in report_dir.glob("definition/pages/*/visuals/*/visual.json"):
        visual = read_json(visual_file).get("visual", {})
        visual_type = str(visual.get("visualType") or "unknown")
        counts[visual_type] = counts.get(visual_type, 0) + 1
    return dict(sorted(counts.items()))


def read_tables(model_dir: Path) -> dict[str, int]:
    tables: dict[str, int] = {}
    for table_file in sorted((model_dir / "definition" / "tables").glob("*.tmdl")):
        table_name = table_file.stem
        column_count = 0
        for line in read_lines(table_file):
            stripped = line.strip()
            if stripped.startswith("table "):
                table_name = stripped.removeprefix("table ").strip()
            elif stripped.startswith("column "):
                column_count += 1
        tables[table_name] = column_count
    return tables


def read_data_sources(model_dir: Path) -> list[str]:
    sources: list[str] = []
    source_re = re.compile(r"(PostgreSQL|Sql|Excel|Csv|SharePoint|Web)\.([A-Za-z]+)\(([^)]*)\)")
    for table_file in sorted((model_dir / "definition" / "tables").glob("*.tmdl")):
        text = "\n".join(read_lines(table_file))
        for match in source_re.finditer(text):
            source = f"{match.group(1)}.{match.group(2)}({match.group(3)})"
            if source not in sources:
                sources.append(source)
    return sources


def read_lines(path: Path) -> Iterator[str]:
    try:
        yield from path.read_text(encoding="utf-8-sig").splitlines()
    except OSError:
        return


HTML_HEAD = """\
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{title}</title>
  <style>
    :root {{
      --primary: #2563eb;
      --primary-dark: #1e40af;
      --success: #15803d;
      --danger: #b91c1c;
      --warning: #b45309;
      --data: #0f766e;
      --muted: #64748b;
      --bg: #f8fafc;
      --surface: #ffffff;
      --surface-soft: #f1f5f9;
      --border: #e2e8f0;
      --text: #0f172a;
    }}
    *, *::before, *::after {{ box-sizing: border-box; }}
    body {{ margin: 0; font-family: "Segoe UI", system-ui, -apple-system, sans-serif; background: var(--bg); color: var(--text); line-height: 1.55; }}
    a {{ color: var(--primary); text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    .container {{ max-width: 1060px; margin: 0 auto; padding: 32px 16px 56px; }}
    header {{ display: flex; justify-content: space-between; gap: 24px; align-items: flex-end; margin-bottom: 24px; padding-bottom: 18px; border-bottom: 2px solid var(--border); }}
    h1 {{ margin: 0; font-size: 1.7rem; line-height: 1.2; }}
    header p {{ margin: 6px 0 0; color: var(--muted); font-size: 0.9rem; }}
    .stamp {{ text-align: right; color: var(--muted); font-size: 0.78rem; white-space: nowrap; }}
    .summary-grid {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; margin-bottom: 20px; }}
    .metric {{ background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 14px; }}
    .metric strong {{ display: block; font-size: 1.4rem; line-height: 1.1; }}
    .metric span {{ color: var(--muted); font-size: 0.8rem; }}
    .panel {{ background: var(--surface); border: 1px solid var(--border); border-radius: 8px; margin-bottom: 20px; overflow: hidden; }}
    .panel h2 {{ margin: 0; padding: 12px 16px; font-size: 1rem; border-bottom: 1px solid var(--border); }}
    .details {{ display: grid; grid-template-columns: 1fr 1fr; gap: 18px; padding: 16px; }}
    .details h3 {{ margin: 0 0 8px; font-size: 0.82rem; color: var(--muted); text-transform: uppercase; letter-spacing: 0.06em; }}
    .details ul {{ margin: 0; padding-left: 18px; }}
    .details li {{ margin-bottom: 4px; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 0.88rem; }}
    th {{ background: var(--surface-soft); color: var(--muted); font-size: 0.72rem; letter-spacing: 0.06em; text-transform: uppercase; text-align: left; }}
    th, td {{ padding: 9px 14px; border-bottom: 1px solid var(--border); vertical-align: top; }}
    tr:last-child td {{ border-bottom: none; }}
    .toc td:first-child {{ font-weight: 700; }}
    .release {{ scroll-margin-top: 16px; }}
    .release-title {{ display: flex; align-items: baseline; gap: 12px; padding: 14px 16px; border-bottom: 1px solid var(--border); }}
    .release-title h2 {{ margin: 0; padding: 0; border: 0; color: var(--primary-dark); }}
    .release-title span {{ color: var(--muted); font-size: 0.82rem; }}
    .release-title.upcoming {{ background: #fffbeb; }}
    .badge {{ display: inline-block; min-width: 88px; padding: 2px 8px; border-radius: 4px; font-size: 0.74rem; font-weight: 700; text-align: center; white-space: nowrap; }}
    .badge-feat {{ background: #dbeafe; color: var(--primary-dark); }}
    .badge-fix {{ background: #dcfce7; color: var(--success); }}
    .badge-data {{ background: #ccfbf1; color: var(--data); }}
    .badge-maint {{ background: #f1f5f9; color: #475569; }}
    .badge-removed {{ background: #fee2e2; color: var(--danger); }}
    .empty-row td {{ color: var(--muted); font-style: italic; }}
    .col-type {{ width: 132px; }}
    .col-ref {{ width: 110px; color: var(--muted); white-space: nowrap; }}
    footer {{ color: var(--muted); font-size: 0.78rem; text-align: right; margin-top: 24px; }}
    @media (max-width: 760px) {{
      .container {{ padding: 20px 10px 40px; }}
      header {{ display: block; }}
      .stamp {{ text-align: left; margin-top: 10px; }}
      .summary-grid {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
      .details {{ grid-template-columns: 1fr; }}
      .panel {{ overflow-x: auto; }}
      table {{ min-width: 620px; }}
    }}
  </style>
</head>
<body>
<div class="container">
  <header>
    <div>
      <h1>{title}</h1>
      <p>{subtitle}</p>
    </div>
    <div class="stamp">Generated {generated}</div>
  </header>
"""

HTML_FOOT = """\
  <footer>Generated by generate_release_notes_improved.py</footer>
</div>
</body>
</html>
"""


def safe_anchor(version: str) -> str:
    anchor = re.sub(r"[^a-zA-Z0-9_-]+", "-", version).strip("-")
    return anchor or "release"


def count_by(entries: list[Entry], key: str) -> str:
    count = sum(1 for entry in entries if entry.category == key)
    return str(count) if count else "-"


def render_project_summary(summary: ProjectSummary) -> str:
    visual_total = sum(summary.visuals.values())
    column_total = sum(summary.tables.values())
    cards = [
        (len(summary.pages), "Report pages"),
        (visual_total, "Visuals"),
        (len(summary.tables), "Model tables"),
        (column_total, "Model columns"),
    ]
    metrics = "\n".join(
        f'    <div class="metric"><strong>{value}</strong><span>{html.escape(label)}</span></div>'
        for value, label in cards
    )
    page_items = render_list(summary.pages or ["No report pages found"])
    visual_items = render_list([f"{name}: {count}" for name, count in summary.visuals.items()] or ["No visuals found"])
    table_items = render_list([f"{name}: {count} columns" for name, count in summary.tables.items()] or ["No model tables found"])
    source_items = render_list(summary.data_sources or ["No data source detected"])
    return f"""
  <section class="summary-grid">
{metrics}
  </section>
  <section class="panel">
    <h2>Project Snapshot</h2>
    <div class="details">
      <div><h3>Pages</h3>{page_items}</div>
      <div><h3>Visuals</h3>{visual_items}</div>
      <div><h3>Semantic Model</h3>{table_items}</div>
      <div><h3>Data Sources</h3>{source_items}</div>
    </div>
  </section>
"""


def render_list(items: list[str]) -> str:
    escaped = "".join(f"<li>{html.escape(item)}</li>" for item in items)
    return f"<ul>{escaped}</ul>"


def render_toc(releases: list[Release]) -> str:
    rows = []
    for release in releases:
        anchor = safe_anchor(release.version)
        rows.append(
            "      <tr>"
            f'<td><a href="#{anchor}">{html.escape(release.version)}</a></td>'
            f"<td>{html.escape(release.date)}</td>"
            f"<td>{count_by(release.entries, 'feat')}</td>"
            f"<td>{count_by(release.entries, 'fix')}</td>"
            f"<td>{count_by(release.entries, 'data')}</td>"
            f"<td>{count_by(release.entries, 'maint')}</td>"
            "</tr>"
        )
    return (
        '  <section class="panel toc">\n'
        "    <h2>Release Index</h2>\n"
        "    <table>\n"
        "      <thead><tr><th>Version</th><th>Date</th><th>Features</th><th>Fixes</th><th>Data</th><th>Maintenance</th></tr></thead>\n"
        "      <tbody>\n"
        + "\n".join(rows)
        + "\n      </tbody>\n    </table>\n  </section>\n"
    )


def render_refs(refs: tuple[str, ...], ref_url_template: str | None = None) -> str:
    rendered = []
    for ref in refs:
        safe_ref = html.escape(ref)
        if ref_url_template:
            url_ref = ref[1:] if ref.startswith("#") else ref
            url = ref_url_template.format(ref=url_ref, raw_ref=ref)
            rendered.append(f'<a href="{html.escape(url, quote=True)}">{safe_ref}</a>')
        else:
            rendered.append(safe_ref)
    return ", ".join(rendered)


def render_release(release: Release, ref_url_template: str | None = None) -> str:
    header_class = "release-title upcoming" if release.upcoming else "release-title"
    rows = []
    if release.entries:
        for entry in release.entries:
            badge = f'<span class="badge {BADGE_CLASS[entry.category]}">{CATEGORY_LABEL[entry.category]}</span>'
            rows.append(
                "      <tr>"
                f'<td class="col-type">{badge}</td>'
                f"<td>{html.escape(entry.description)}</td>"
                f'<td class="col-ref">{render_refs(entry.refs, ref_url_template)}</td>'
                "</tr>"
            )
    else:
        rows.append('      <tr class="empty-row"><td colspan="3">No release changes recorded.</td></tr>')

    return f"""  <section class="panel release" id="{safe_anchor(release.version)}">
    <div class="{header_class}"><h2>{html.escape(release.version)}</h2><span>{html.escape(release.date)}</span></div>
    <table>
      <thead><tr><th class="col-type">Category</th><th>Description</th><th class="col-ref">Ref</th></tr></thead>
      <tbody>
{chr(10).join(rows)}
      </tbody>
    </table>
  </section>
"""


def build(
    repo: Path,
    out: Path,
    *,
    title: str = "Reporting Release Notes",
    subtitle: str = "Power BI report release history and project snapshot",
    ref_url_template: str | None = None,
    include_project_summary: bool = True,
) -> None:
    tags = get_tags(repo)
    releases: list[Release] = []

    if tags:
        releases.append(Release("vNEXT", "Unreleased", parse_entries(commits_between(repo, tags[0], "HEAD")), upcoming=True))
        for index, tag in enumerate(tags):
            previous_tag = tags[index + 1] if index + 1 < len(tags) else None
            releases.append(Release(tag, tag_date(repo, tag), parse_entries(commits_between(repo, previous_tag, tag))))
    else:
        releases.append(Release("vNEXT", "Unreleased", parse_entries(commits_between(repo, None, "HEAD")), upcoming=True))

    generated = datetime.now().strftime("%Y-%m-%d %H:%M")
    parts = [
        HTML_HEAD.format(title=html.escape(title), subtitle=html.escape(subtitle), generated=html.escape(generated)),
    ]
    if include_project_summary:
        parts.append(render_project_summary(inspect_project(repo)))
    parts.append(render_toc(releases))
    parts.extend(render_release(release, ref_url_template) for release in releases)
    parts.append(HTML_FOOT)

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("".join(parts), encoding="utf-8")
    print(f"Written -> {out} ({len(releases)} releases, {len(tags)} tags)")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate HTML release notes from git tags and Power BI project metadata.")
    parser.add_argument("--repo", default=".", help="Path to the git repository. Default: current directory.")
    parser.add_argument("--out", default="release-notes.html", help="Output HTML file. Default: release-notes.html.")
    parser.add_argument("--title", default="Reporting Release Notes", help="Page title and header.")
    parser.add_argument("--subtitle", default="Power BI report release history and project snapshot", help="Header subtitle.")
    parser.add_argument("--no-project-summary", action="store_true", help="Skip the Power BI project snapshot section.")
    parser.add_argument(
        "--ref-url-template",
        help="Optional URL template for refs. Use {ref} without # or {raw_ref} as written.",
    )
    args = parser.parse_args(argv)

    repo = Path(args.repo).resolve()
    out = Path(args.out).resolve()

    if not repo.exists():
        print(f"ERROR: repository path does not exist: {repo}", file=sys.stderr)
        return 1
    if not is_git_repo(repo):
        print(f"ERROR: {repo} is not inside a git repository.", file=sys.stderr)
        return 1

    try:
        build(
            repo,
            out,
            title=args.title,
            subtitle=args.subtitle,
            ref_url_template=args.ref_url_template,
            include_project_summary=not args.no_project_summary,
        )
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
