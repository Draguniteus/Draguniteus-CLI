"""Entry point: python -m draguniteus"""
import sys
from draguniteus.cli import main

if __name__ == "__main__":
    # Invoke typer to handle argument parsing from sys.argv
    from draguniteus.cli import app
    app()