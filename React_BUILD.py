"""Build the React surface of Acervator: a double-click needs no argument.

``VARIANT`` is fixed at ``REACT`` and ``main`` hands it to ``launch``, reading
no command line.
"""

from src._variant import REACT
from tools.build_launcher import launch

VARIANT = REACT


def main() -> None:
    """Build the ``VARIANT`` surface through ``launch``, then wait on a keypress."""
    launch((VARIANT,))
    input("\nPress Enter to close...")


if __name__ == "__main__":
    main()
