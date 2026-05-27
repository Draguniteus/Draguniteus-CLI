"""Entry point: python -m draguniteus"""
import sys
# Fix stdout encoding early on Windows so Rich/emoji output works
if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from draguniteus.cli import main

if __name__ == "__main__":
    # Invoke typer to handle argument parsing from sys.argv
    from draguniteus.cli import app
    app()