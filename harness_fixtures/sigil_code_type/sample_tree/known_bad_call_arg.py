def greet(name: str) -> None:
     print('hello', name)

greet('jack')  # OK
greet('jill', 'jack')  # Error: Too many arguments for "greet"  [call-arg]
