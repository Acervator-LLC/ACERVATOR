# RUF048 map-int-version-parsing: the lines above the Example block python -m ruff rule RUF048 prints define its free names
import matplotlib
tuple(map(int, matplotlib.__version__.split(".")))
