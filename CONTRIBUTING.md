# Contributing to PewwTerm

Thanks for helping improve PewwTerm. This project is a read-only terminal file
explorer with a focus on keyboard navigation, safe external processes and
graceful degradation when optional tools are missing.

## Before you start

- Search existing issues and pull requests before opening a new one.
- Open an issue before a large refactor, new preview backend or new dependency.
- Report security issues privately as described in [SECURITY.md](SECURITY.md).
- Keep changes focused. Separate unrelated fixes and documentation updates.

## Development setup

```bash
cd pewwterm
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'
```

## Required checks

Run both commands before opening a pull request:

```bash
.venv/bin/pytest -q
ruff check src tests demo/capture_screens.py
```

If you add or change behaviour, add a regression test. Tests must not depend on
the developer's real home cache, terminal size or installed optional tools unless
the test explicitly mocks or skips that environment.

## Code guidelines

- Support Python 3.10 and newer.
- Use type hints and the existing `from __future__ import annotations` style.
- Keep filesystem, search, traversal and preview logic out of the Textual layer.
- Use `pathlib.Path` instead of shell strings.
- Keep preview work bounded by size, line, depth or result limits.
- Run external programs with argument lists, never `shell=True`.
- Add a timeout to bounded subprocesses and handle non-zero exits explicitly.
- Treat optional tools as optional: report missing capabilities in the UI instead
  of crashing.
- Long operations belong in workers or `asyncio.to_thread`, not the UI thread.
- Follow the existing CSS and widget patterns for interface changes.
- Update the README, help screen and relevant `docs/` page when user-visible
  behaviour changes.

## Adding tests

- Pure module tests belong in the matching `tests/test_*.py` file.
- Textual tests use `app.run_test(size=(...))` and `pilot.press`.
- Inject a fake preview builder when the test does not need real media output.
- Mock `subprocess.run` for external-tool tests and assert safe invocation.
- Use temporary files and the isolated cache fixture from `tests/conftest.py`.
- Guard symlink tests with the `no_symlink_support` fixture.

## Pull requests

A pull request should include:

- a summary of the user-visible change,
- the tests added or updated,
- the exact commands run and their results,
- documentation changes, if applicable,
- any known limitations or follow-up work.

Keep the diff focused and avoid unrelated formatting churn. Do not include
generated virtual environments, cache directories, secrets or private media.

## Commit messages

Use a concise imperative subject. Examples:

```text
Fix symlink navigation parent path
Add PDF thumbnail cache invalidation test
Document optional preview dependencies
```

## Documentation

The project documentation lives in [docs/](docs/index.md). The README is the
overview and screenshot gallery; detailed guides belong in `docs/`. Keep
commands, shortcut tables and dependency descriptions consistent across both.

## Community expectations

Be respectful, constructive and specific. Assume good intent, focus criticism on
the code and behaviour, and avoid sharing another person's private files, paths or
logs. Harassment or discriminatory behaviour is not welcome. See
[CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).
