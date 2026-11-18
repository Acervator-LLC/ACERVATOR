# PLE0604 invalid-all-object: the line above the Use instead block python -m ruff rule PLE0604 prints defines its free names
Foo = Bar = Baz = 1
__all__ = ["Foo", "Bar", "Baz"]
