
Documentation

Applies to all documentation in this repo.

## Explain what and not why

Documentation is meant to describe the exact current state of the codebase and how it functions. It is not meant to be an invitation for story telling, or history. 
The documentation should be written in markdown files, and should include crosslinking where necessary. 

- Documents should be grouped in directories according to their area of reference.
- All documentation diagrams should be written in mermaid
- Documentation should be treated as a helpful guide for human consumption. Being overly verbose is not useful here, be concise and to the point.
- No `vXX.XX.XX` version names, no Item numbers, no PR numbers, ever. 
- A citation names a symbol, never a line number. Write the path, a comma, then the function or class: `src/trading/bot_container.py, in guarded_place_order`. A line number stops naming its code as soon as anything above it in the file moves, and the path stays correct, so nothing reports the drift. A symbol survives every edit short of a rename, and a rename is a change its author can see. Rule H006 in the documentation archetype reports each line-anchored citation it finds in a markdown page.
- If a document is growing large, it is a clear indication that the document should be broken apart into subdocuments, crosslinked with a table of contents to the main document.
- The README for the repo should include only general information about the application, what it is meant to acheive, and light documentation about the tech stack. It should not be narrative, or long winded. NOr should it use flowery language.
- the README should not contain a project structure. That is obvious through a glance at the codebase. We do not write directory trees to the readme, but flow charts and diagrams are acceptable where warranted. 

AI tends to try to document everything, from the prompt we gave to the contents of our last chat session. Documentation is not meant to chronicle our interactions.
Documentation is meant to act as a guide for humans to understand how to read the contents of, devlelop against, or interact with this repo. 
