# A004 builtin-import-shadowing: the Use instead blocks python -m ruff rule A004 prints
from rich import print as rich_print

rich_print("Some message")
import rich

rich.print("Some message")
