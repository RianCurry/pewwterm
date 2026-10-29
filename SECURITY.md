# Security policy

## Supported versions

Security fixes are provided for the current `0.1.x` line. Older snapshots and
unmaintained forks are not supported.

## Reporting a vulnerability

Do not open a public issue for a suspected vulnerability.

Use GitHub's private vulnerability reporting for this repository:

1. Open the repository's **Security** tab.
2. Choose **Advisories** and create a private report.

If private reporting is not enabled, contact the maintainers through the
repository owner's GitHub profile and ask for a private channel. Include:

- affected version and Python version,
- operating system and terminal,
- a minimal reproduction,
- impact and any suggested fix,
- whether the issue is already public.

Please allow time for a fix before public disclosure.

## Security model and hardening

PewwTerm is a read-only browser. It does not implement copy, move, delete or
rename operations.

External programs are invoked with argument lists and without a shell. Bounded
operations use captured output, `check=False` and a 20-second timeout. Optional
tools are discovered on `PATH` at call time.

Preview output is bounded before it reaches the terminal. Text files with a NUL
byte in the sampled prefix are treated as binary. Markdown is rendered by Rich,
not executed. Chafa output is parsed as ANSI text.

`mpv` is an external program with its own attack surface and configuration. The
application passes a video path to it and waits for it to exit; it does not
sandbox `mpv`. Treat media files and `mpv` itself as untrusted input.

## Not in scope

- Vulnerabilities in `mpv`, FFmpeg, Poppler, Chafa, Textual, Rich or Pillow that
  are fixed in their current releases.
- Terminal emulator or display-server vulnerabilities.
- Denial of service caused by intentionally malformed media when the relevant
  external tool crashes; PewwTerm should still report the failure without
  crashing its own process.
- Files or paths intentionally shared by the user in screenshots or logs.
