# Fixture: a complete test statement whose inputs rule is all

Item #1633. Ground truth: the Truth Archetype reports no T009 finding on this
file. The inputs part takes every task folder, sorted, so a T009 finding here
is a defect in the rule.

```test-statement
{
  "question": "On every task, does the sigil arm finish with correct, clean code more often than the plain arm?",
  "arms": {
    "plain": "the archetype runs with sigil feedback switched off",
    "sigil": "the archetype reads the sigil lines as advice"
  },
  "unit": "one run of one task in one arm",
  "measure": {
    "reading": "passed in the Coding Archetype report on the file the run leaves",
    "checks": ["dev_harness/harness/coding_archetype.py"],
    "calibration": "harness_fixtures/truth_archetype/test_statement/calibration.json"
  },
  "inputs": {
    "rule": "all",
    "population": "harness_fixtures/truth_archetype/test_statement/tasks",
    "items": [
      "Task_01_Sum_Rows",
      "Task_02_Parse_Dates",
      "Task_03_Dedupe_Names",
      "Task_04_Read_Config",
      "Task_05_Merge_Totals",
      "Task_06_Clip_Prices",
      "Task_07_Count_Words",
      "Task_08_Split_Batches"
    ]
  },
  "runs": {
    "rounds": 3,
    "per_round": 16,
    "total": 48,
    "alpha": 0.05,
    "power": [
      {"test": "exact sign", "pairs": 24, "first_rate": 0.3, "second_rate": 0.9, "power": 0.99},
      {"test": "exact sign", "pairs": 24, "first_rate": 0.45, "second_rate": 0.65, "power": 0.19}
    ]
  },
  "expected": {
    "source": "dev_harness/skills/canonized-workflow/SKILL.md",
    "statement": "Step 2 pooled 15 of 24 against 11 of 24, which Fisher's exact test reads at p 0.39."
  },
  "pass": {"test": "exact sign", "group": "the 24 task pairs", "alpha": 0.05, "leading_arm": "sigil"},
  "harm": {"test": "exact sign", "group": "the 24 task pairs", "alpha": 0.05, "leading_arm": "plain"},
  "interim": {"reads": ["voids"]},
  "adversarial": [
    {
      "question": "what makes this result wrong",
      "answer": "A run that reads the other arm's folder, which the scorer voids.",
      "evidence": "dev_harness/skills/ocir/SKILL.md"
    },
    {
      "question": "what does the measure miss",
      "answer": "Quality no check reads; minutes and tokens are reported beside the result.",
      "evidence": "dev_harness/skills/truth-check/SKILL.md"
    },
    {
      "question": "what is the cheapest way to pass without the behaviour",
      "answer": "Hard-coding the stated examples, which the hidden checks read.",
      "evidence": "dev_harness/skills/two-sided-control/SKILL.md"
    },
    {
      "question": "does any input sit at a ceiling or a floor",
      "answer": "The plain arm may pass near the top on the first two tasks.",
      "evidence": "dev_harness/skills/canonized-workflow/SKILL.md"
    }
  ]
}
```
