# Development

## Setup

```bash
cd pewwterm
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'
```

The `dev` extra installs pytest, pytest-asyncio and Ruff.

## Test and lint

Run the same checks used by the GitHub workflow:

```bash
.venv/bin/pytest -q
ruff check src tests demo/capture_screens.py
```

The GitHub workflow runs these checks on Python 3.10, 3.12 and 3.14. The suite is
expected to pass on Python 3.10 and newer. Tests use temporary directories and an
isolated preview cache; they do not write into the developer's home cache.

## Test conventions

- Put pure logic tests next to the module they cover (`test_models.py`,
  `test_search.py`, `test_traversal.py`, `test_preview.py`).
- Use Textual's `run_test` pilot for interface behaviour and inject a fake preview
  builder when external media output would make the test nondeterministic.
- Mock `subprocess.run` for external-tool tests and assert that calls use an
  argument list, `check=False`, no shell and bounded output.
- Add regression tests for every bug fix. A test should fail before the fix and
  pass after it.
- Use temporary files rather than fixture media checked into the repository.

## Screenshot generation

The screenshots in the README are generated from the real preview helpers:

```bash
.venv/bin/python demo/capture_screens.py /path/to/media --output demo/screenshots
```

The media directory should contain at least one image, video and PDF to generate
the full set. The script uses Textual's test driver and writes SVG files; it does
not open an interactive terminal.

## Adding a preview backend

1. Add the file type to `config.py`.
2. Extend classification in `models.py` and `FileKind` if needed.
3. Implement bounded work in a dedicated preview module.
4. Dispatch it from `preview.py` and render its `PreviewResult` in `app.py`.
5. Add missing-tool, success and failure tests with mocked subprocesses.
6. Document the tool and fallback behaviour in `docs/previews.md` and the README.

## Adding a keyboard shortcut

1. Add a `Binding` in `PewwTermApp.BINDINGS`.
2. Implement the `action_*` method with error and empty-state handling.
3. Update the help screen, README shortcut table and `docs/usage.md`.
4. Add an application test using `pilot.press`.
5. Keep printable keys usable inside the search input; use a `Ctrl` combination
   for actions that must also work while typing.

## External process checklist

- Pass an argument list and never use `shell=True`.
- Add a timeout for bounded operations.
- Use `check=False` and handle non-zero exits explicitly.
- Capture and truncate output where a tool can produce large output.
- Convert missing binaries, timeouts and decode failures into user-facing text.
- Do not print secrets, file contents or unbounded command output.

## Pull requests

Keep changes focused, include tests and run the full suite plus Ruff before
opening a pull request. See [CONTRIBUTING.md](../CONTRIBUTING.md) for the complete
workflow.
