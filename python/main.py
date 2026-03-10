"""DCS Backup & Restore - Entry point."""

from src.app import App
from src.version import __version__


def main():
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
