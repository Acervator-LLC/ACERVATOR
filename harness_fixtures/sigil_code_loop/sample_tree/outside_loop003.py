# LOOP003 str-concat-in-loop: the same statement outside any loop, beside a loop that reads the list
words = ["Eric", "John", "Michael"]
text = ""
text += words[0]
upper = [word.upper() for word in words]
