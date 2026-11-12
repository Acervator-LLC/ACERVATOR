class Resource:
    def __init__(self, name: str) -> None:
        self.name = name

r = Resource('x')
print(r.name)  # OK
print(r.id)  # Error: "Resource" has no attribute "id"  [attr-defined]
r.id = 5  # Error: "Resource" has no attribute "id"  [attr-defined]
