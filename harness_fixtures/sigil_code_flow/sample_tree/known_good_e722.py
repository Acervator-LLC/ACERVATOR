# E722 bare-except: the lines above the Use instead block python -m ruff rule E722 prints define its free names
do_something_that_might_break, MoreSpecificException, handle_error = print, ValueError, print
try:
    do_something_that_might_break()
except MoreSpecificException as e:
    handle_error(e)
def run_a_function(some_other_fn):
    try:
        some_other_fn()
    except Exception as e:
        print(f"How exceptional! {e}")
