# PIE794 duplicate-class-field-definition: the lines above the Use instead block python -m ruff rule PIE794 prints define its free names
Tom = "Tom"
class Person:
    name = Tom
    ...
