"""Backward-compatible interactive launcher for the legacy JSON export."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent / "src"))

from ispano.legacy import main


if __name__ == "__main__":
    raise SystemExit(main())
