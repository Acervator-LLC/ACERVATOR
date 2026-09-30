# FIXTURE MANUAL

Reference. Cover page and epigraph, with a body section misplaced onto it.

> A measured page holds what its own contents row says it holds.

> A cover page holds a title and an epigraph, and the contents follow it.

## The drawing

This section belongs in a part file. It prints between the cover and the
contents, so a reader meets it before the contents row that should have led
there.

| Element | What it stands for |
|---|---|
| Frame | The page the section does not belong on |

### How it is built

```python
BODY_SECTION = "a heading below the title, with a table and a code block"
```
