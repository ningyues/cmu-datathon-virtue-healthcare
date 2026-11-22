"""Shared local configuration for both agents; never executes shell expressions."""
import os
from pathlib import Path
import re
import shlex

DEFAULT_ENV_FILE = Path(__file__).resolve().parent / ".env"


class EnvConfigError(ValueError):
    pass


def load_env_file(path: Path = DEFAULT_ENV_FILE) -> None:
    """Read KEY=VALUE entries without shell execution; file values take priority."""
    path = Path(path)
    if path == DEFAULT_ENV_FILE and not path.exists():
        return
    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
        pending = {}
        for number, line in enumerate(lines, 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            match = re.fullmatch(r"(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)", line)
            if not match:
                raise ValueError(f"Invalid env entry on line {number}")
            lexer = shlex.shlex(match[2], posix=True)
            lexer.whitespace_split = True
            lexer.commenters = "#"
            parts = list(lexer)
            if len(parts) > 1:
                raise ValueError(f"Quote env values containing spaces on line {number}")
            pending[match[1]] = parts[0] if parts else ""
        for name, value in pending.items():
            os.environ[name] = value
    except (OSError, ValueError) as exc:
        raise EnvConfigError("Cannot read env file; use one KEY=VALUE entry per line.") from exc

