"""Entry point: python -m draguniteus"""
import sys
# Fix stdout encoding early on Windows so Rich/emoji output works
if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def main() -> None:
    """Entry point for the draguniteus CLI — routes through Typer app."""
    from draguniteus.cli import app
    import sys
    # If sys.argv has subcommand already (from direct exe invocation), use it
    # Otherwise use "main" as default command
    args = sys.argv[1:] if len(sys.argv) > 1 else ["main"]
    app(args)


if __name__ == "__main__":
    main()