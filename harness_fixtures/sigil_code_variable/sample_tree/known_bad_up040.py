# UP040 non-pep695-type-alias: the Example block python -m ruff rule UP040 prints
from typing import Annotated, TypeAlias, TypeAliasType

from annotated_types import Gt

ListOfInt: TypeAlias = list[int]
PositiveInt = TypeAliasType("PositiveInt", Annotated[int, Gt(0)])
