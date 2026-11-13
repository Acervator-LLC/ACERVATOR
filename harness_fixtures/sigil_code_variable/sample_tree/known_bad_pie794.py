# PIE794 duplicate-class-field-definition: the lines above the Example block python -m ruff rule PIE794 prints define its free names
Tom, Ben = "Tom", "Ben"
class Person:
    name = Tom
    ...
    name = Ben
