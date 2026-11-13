# RUF048 map-int-version-parsing: the lines above the Use instead block python -m ruff rule RUF048 prints define its free names
import matplotlib
import packaging.version as version

version.parse(matplotlib.__version__)
