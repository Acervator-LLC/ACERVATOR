# LOOP003 str-concat-in-loop: the corrected form dev_harness/sigils/code_loop.py holds in OWN
import io

words = ["Eric", "John", "Michael"]
buffer = io.StringIO()
for word in words:
    buffer.write(word)
text = buffer.getvalue()
