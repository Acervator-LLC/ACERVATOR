# `splash_screen.py`

731 source lines. The row is **not convertible**. The running program never
imports this file and never builds the `SplashScreen` class inside it.

The file is a ten-slide presentation deck, not an application screen. What it
paints is in
[splash_screen.png](../../docs/audits/2026-09-06_row_by_row/splash_screen.png).

## Edits

`docs/manual/08-tabs.md` — the Bridge cell of the `splash_screen.py` row
changed from `yes` to `no`. No other cell and no sentence changed.

The item's issue body — the same row, the same cell.

`docs/audits/2026-09-06_row_by_row/splash_screen.png` — added. It is the ten
slides `splash_screen.py` paints today under Qt, one frame each.

`splash_screen.py` — unchanged.

## Errors detected

**No program error.** The file was run under the debugger and it finished.

```
python -X dev -X faulthandler -m pdb -c continue <renderer> <repo> <png>
```

```
wrote splash_pdb.png 2000 x 3330
The program finished and will be restarted
```

`pdb` reported no traceback and entered no post-mortem frame. `PYTHONWARNINGS=error`
was set, so a warning would have become a traceback. None appeared.

**Nothing in the application reaches the file.** The search below finds a
top-level import of a module. It finds three real importers of `screen_fx`, so
it can report an import when one exists.

```
grep -rn "^import screen_fx|^from screen_fx|^import splash_screen|^from splash_screen" --include=*.py .

./cartoon_screen.py:25:import screen_fx
./cartoon_screen.py:26:from screen_fx import AnimatedScreenBase, ease, scene_alpha, tag_font
./investor_screen.py:34:import screen_fx
./investor_screen.py:35:from screen_fx import AnimatedScreenBase, ease, scene_alpha, tag_font
./splash_screen.py:27:import screen_fx
./splash_screen.py:28:from screen_fx import AnimatedScreenBase, ease, scene_alpha, tag_font
```

No file imports `splash_screen`. The docstring of `screen_fx` states the same
thing about the three decks it serves.

**Nothing builds the class.** A search for `SplashScreen(` finds two class
statements and one construction. The construction in `main.py` builds the
`SplashScreen` that `main.py` declares itself, not the one in
`splash_screen.py`.

```
./main.py:826:    class SplashScreen(_QW):
./main.py:1044:    _splash = SplashScreen(crypto_window)
./splash_screen.py:105:class SplashScreen(AnimatedScreenBase):
```

**The Bridge cell named the wrong screen.** `src/core/desktop_bridge.py`
imports `splash_screen_surface` and registers `splash_screen_surface.view_model`
under `splash_screen_surface.METHOD`. It does not import `splash_screen`. The
two files describe different screens, and the texts prove it. A count of `1`
means the text is in that file and `0` means it is not.

```
                                  main.py  surface  splash_screen.py
"An Accumulation Trading Platform"      1        1                 0
"click anywhere to continue"            1        1                 0
"fadeout"                               3        2                 0
"The market doesn't sleep"              0        0                 1
```

`splash_screen_surface.paint_ops` describes the splash `main.py` paints.
`splash_screen.py` shares none of its text and none of its phases.

**A React host can exist this early.** The order `main.py` uses is a plain
`QApplication`, with no shared-context attribute set before it.

```
python -X dev -X faulthandler -c "... QApplication(sys.argv) ... QWebEngineView()"

QApplication built, AA_ShareOpenGLContexts set before it: False
QWebEngineView constructed OK: QWebEngineView
```

This row fails on reach, not on timing. A React page could be hosted at splash
time. The application never draws this splash, so React has nothing to replace.

**One defect inside the file, left in place.** The loop in `_rajdhani` returns
on its first pass, so the fallback names after `Rajdhani` are never reached and
the size and weight always go to `Rajdhani`. The file is not reached by the
application, and repairing an unreached file makes it load-bearing.

## Resolution

No code changed, so the reruns measure the same file.

`splash_screen.py` reads no variant name. The search finds `src/_variant.py`,
which does read one, so it can report a reader when one exists.

```
grep -rn "ACERVATOR_VARIANT" splash_screen.py screen_fx.py     (no output)
grep -rln "ACERVATOR_VARIANT" --include=*.py src/              src/_variant.py
```

Both variants were run anyway, and both painted the same Qt deck.

```
ACERVATOR_VARIANT=react  exit=0  wrote splash_react.png 2000 x 3330
ACERVATOR_VARIANT=qt     exit=0  wrote splash_qt.png    2000 x 3330
```

The archetypes report `passed` on the file:

```
coding_archetype splash_screen.py   passed=True   exit 0
gui_archetype    splash_screen.py   passed=True   exit 0
```

Every tool in both runs reported `ok`, and both runs recorded no errors.

The fixture controls were run first. `known_good` exits 0 and `known_bad`
exits 1 for the coding, GUI and docs archetypes, so a green from them carries
a meaning.

The table row now reads `no` in every mark column, with `shelved` in the scope
column. That is the true state of a file the running program does not reach.
