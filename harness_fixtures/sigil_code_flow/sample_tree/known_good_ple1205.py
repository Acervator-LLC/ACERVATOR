# PLE1205 logging-too-many-args: the lines above the Use instead block python -m ruff rule PLE1205 prints define its free names
function = print
import logging

try:
    function()
except Exception as e:
    logging.error("%s error occurred: %s", type(e), e)
    raise
