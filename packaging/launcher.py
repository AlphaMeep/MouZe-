"""Entry point used by PyInstaller builds."""

import sys

from mouze.cli import main

if __name__ == "__main__":
    sys.exit(main())
