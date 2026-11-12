string_numbers: list[str] = ["1", "2", "three", "4", "5"]

int_numbers: list[int] = []
try:
    for num in string_numbers:
        int_numbers.append(int(num))
except ValueError as e:
    print(f"Couldn't convert to integer: {e}")

number_names: dict[int, str] = {1: "one", 3: "three", 4: "four"}
for number in range(5):
    name = number_names.get(number)
    if name is not None:
        print(f"The name of {number} is {name}")
