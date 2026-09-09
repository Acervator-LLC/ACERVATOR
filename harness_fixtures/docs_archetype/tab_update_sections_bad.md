# Subsystem Tabs

Reference. Two tabs take a heading below, and each update to a tab takes a
dated subsection under the heading for that tab. The Console tab comes first
and its own two updates run backwards.

## Console Tab

The window builds one Console tab and moves it into the position the tab
order sets. The tab owns its own log handler and leaves every logger level
alone.

### 2026-09-09 11:40 - #34 - the emitter pane reads its own sink

The lower pane counts invocations rather than records, so a quiet sink no
longer reads as a stopped timer. The upper pane keeps its own handler level.

### 2026-09-08 08:17 - #34 - the pause button holds the tail

Pausing stops the tail without dropping records. The pane redraws the newest
two hundred lines when the tail resumes.

## History Tab

The History tab lists every fill the fleet booked. One table holds the rows
and one filter narrows them.

### 2026-09-06 09:12 - #450 - the table takes its label from its own surface

The tab bar names this screen History. The bar and the screen cannot carry
two spellings of one name.

### 2026-09-07 15:58 - #450 - the filter keeps the row count in view

The filter leaves the total beside the narrowed count, so a narrow filter
cannot read as an empty table.
