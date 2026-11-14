# UP040 non-pep695-type-alias: the Use instead block python -m ruff rule UP040 prints
from typing import Annotated

from annotated_types import Gt

type ListOfInt = list[int]
type PositiveInt = Annotated[int, Gt(0)]
