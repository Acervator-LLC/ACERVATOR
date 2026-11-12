# COM818 trailing-comma-on-bare-tuple: the Use instead blocks python -m ruff rule COM818 prints
import json


foo = json.dumps({"bar": 1})
import json


foo = (json.dumps({"bar": 1}),)
