# C419 unnecessary-comprehension-in-call: the lines above the Example block python -m ruff rule C419 prints define its free names
from types import SimpleNamespace
bar = [SimpleNamespace(id=1, val=2)]
any([x.id for x in bar])
all([x.id for x in bar])
sum([x.val for x in bar])
min([x.val for x in bar])
max([x.val for x in bar])
