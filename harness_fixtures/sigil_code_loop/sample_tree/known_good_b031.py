# B031 reuse-of-groupby-generator: the lines above the Use instead block python -m ruff rule B031 prints define its free names
data, do_something_with_the_group = "aab", print
import itertools

for name, group in itertools.groupby(data):
    values = list(group)
    for _ in range(5):
        do_something_with_the_group(values)
