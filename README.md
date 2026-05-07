# Reporting

Power BI report project with an HTML release-note generator.

## Generate release notes

Run the generator from the repository root:

```powershell
python generate_release_notes_improved.py --repo . --out release-notes.html
```

The generated `release-notes.html` includes:

- a Power BI project snapshot with pages, visuals, model tables, columns, and data sources;
- a release index from git tags;
- categorized changes from conventional commits and common pull-request merge branches.

## Commit message format

Use clear conventional commits so future release notes stay readable:

```text
feat: add employee comments table
fix: correct employee data refresh issue
data: update reporting seed data
docs: document release-note workflow
```

Supported categories are `feat`, `fix`, `data`, `removed`, and maintenance types such as `docs`, `chore`, `refactor`, `test`, `build`, and `ci`.
