# E701 multiple-statements-on-one-line-colon: the lines above the Example block python -m ruff rule E701 prints define its free names
foo, do_blah_thing = "blah", print
if foo == "blah": do_blah_thing()
