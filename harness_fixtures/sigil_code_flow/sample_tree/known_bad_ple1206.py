# PLE1206 logging-too-few-args: the lines above the Example block python -m ruff rule PLE1206 prints define its free names
function = print
import logging

try:
    function()
except Exception as e:
    logging.error("%s error occurred: %s", e)
    raise
