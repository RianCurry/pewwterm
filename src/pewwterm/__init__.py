"""PewwTerm: a keyboard-driven multimedia file explorer for the terminal.

The public package exposes only the version string.  Application code lives in
:mod:`pewwterm.app`, while filesystem, search, traversal and preview logic is
kept in small, independently testable modules.
"""

__all__ = ["__version__"]

__version__ = "0.1.0"
