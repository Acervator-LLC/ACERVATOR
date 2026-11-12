string_numbers: list[str] = ["1", "2", "three", "4", "5"]

# `try`/`except` that could be moved out of the loop:
int_numbers: list[int] = []
for num in string_numbers:
    try:
        int_numbers.append(int(num))
    except ValueError as e:
        print(f"Couldn't convert to integer: {e}")
        break

# `try`/`except` used when "look before you leap" idioms could be used:
number_names: dict[int, str] = {1: "one", 3: "three", 4: "four"}
for number in range(5):
    try:
        name = number_names[number]
    except KeyError:
        continue
    else:
        print(f"The name of {number} is {name}")
