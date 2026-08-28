Code Comments

Applies to all code in this repo.

## Almost never write code comments

Code comments are of little to no value. Default to **no comment**. The code is the source of truth -- a reader gets more from clear names and structure than from prose describing them. 

- When a comment is warranted at all, it describes the **functionality of the function or method** -- what it does, its inputs/outputs, its contract. Nothing else. 
- **Never** write narrative, storytelling, or running-commentary comments. Period.
- Do not restate what the code already says. If the comment paraphrases the line below it, delete it.
- No `vXX.XX.XX` version names, no Item numbers, no PR numbers, ever. The commit -> PR -> story chain and `git blame` already record all decisions and why a change was made. 
- Docstrings are allowed to maintain **Light** narrative to explain their integration with the application
- Docstrings should not contain version names pull request or issue numbers, item numbers etc... They should describe the function or method and how it ties into the code. 

```python
# ❌ has a version, memory, item, identifier number to something outside of codebase
# MEM-220 This is a thing
def my_func
...
end

# ❌ narrative or story
# my_func exists because a user had a problem with the formatting of an issue, we went back and forth and ultimately decided on this
def my_func
...
end

# ❌ restates the code outside of docstring
# capitalize capitalizes a word
def capitalize
...
end

# ✅ A docstring explains what the code does and how it ties in 
def capitalize_helper
"""a helper to capitalize words, available as an import in other files throughout the app"""
...
end
```

## When generating code (AI assistant)

AI-generated code tends to overcomment. Default to **no comment**. When in doubt, leave it out -- a reviewer can always ask for a comment, but noise is harder to remove later. 
