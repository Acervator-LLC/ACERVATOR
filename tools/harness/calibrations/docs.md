# Documentation-Quality Calibration

Domain: technical documentation in Markdown.

## What a documentation peer reviewer looks for

- **Google Developer Documentation Style Guide compliance**: sentence case headings; second person ("you", not "the user"); active voice; present tense; concrete examples; no gerund headings.
- **Microsoft Writing Style Guide**: bias-free language; global-English friendly; no idioms that don't translate.
- **Diataxis mode signal**: opening should indicate whether the doc is a Tutorial (learning by doing), How-to (task recipe), Reference (lookup), or Explanation (understanding). Mixing modes in one document is the most common failure mode.
- **Prose quality**: no cliches ("at the end of the day", "no-brainer", "needless to say"), no weasel words ("very", "basically", "actually"), no corporate speak ("utilize" → "use"), no hyperbole ("literally the best").
- **Document structure**: single H1 title, no duplicate headings, ordered heading hierarchy (no H1→H3 skips), Prerequisites/Steps/Verify/Rollback sections in how-to content.
- **Actionability**: how-to steps have concrete file paths, commands, verification signals. "Sign in. Duh." is not a step.
- **Meta-commentary**: the doc should describe the task, not describe its own defects. Body text that self-narrates ("this is a duplicate heading, oops") is a code smell.
- **Consistency**: same voice/tense/register across sibling documents.

## Severity conventions (peer reviewer)

- **high**: missing H1 title; missing Diataxis mode signal; duplicate headings that break TOC generation; missing Prerequisites/Verify/Rollback sections in how-to content; dismissive tone ("Duh.").
- **medium**: cliches, weasel words, corporate speak; third-person "the user" when second-person is expected; presumptuous assumptions about reader knowledge.
- **low**: title-case vs sentence-case; minor redundancy; passive framing preferences.

## What the mechanical tools already cover (do not duplicate)

- **proselint**: cliches, weasel words, corporate catchphrases, filler exclamations, curly-quote typography. Full check families documented at proselint.com.
- **structure (in-house)**: DOC001 no H1 title; DOC003 no Diataxis mode signal; DOC004 duplicate headings.
- **Vale** (when installed): Google + Microsoft style pack rules, custom dictionary.

Peer review adds VALUE for judgment calls the mechanical tools cannot make: is the tone appropriate for the audience? Are the how-to steps complete? Is the sequence rational?

## What peer review CANNOT reliably do

- Verify code snippets in the doc actually work. Use docstring tests or CI-runnable examples for that.
- Verify screenshots match the current UI. Use image-diff regression tests.

## Output shape peer reviewer must return

```json
{
  "<filename>": {
    "total_issues": N,
    "issues": [
      {"line": N, "severity": "low|medium|high", "description": "..."}
    ]
  }
}
```

Keep response under 500 words. Do not run tools.
