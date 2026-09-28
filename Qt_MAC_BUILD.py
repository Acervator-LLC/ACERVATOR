"""Build the Qt surface of Acervator for macOS: a double-click needs no argument.

``VARIANT`` is fixed at ``QT`` and ``main`` hands it to ``launch_macos``, reading
no command line.
"""

from src._variant import QT
from tools.build_launcher import launch_macos

VARIANT = QT


def main() -> None:
    """Build the ``VARIANT`` surface through ``launch_macos``, then wait on a keypress."""
    launch_macos((VARIANT,))
    input("\nPress Enter to close...")


if __name__ == "__main__":
    main()
