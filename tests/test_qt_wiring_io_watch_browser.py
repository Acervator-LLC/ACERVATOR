"""The shared io watch records a browser call without starting a browser.

``io_watched`` reports ``webbrowser`` in ``touched`` for a driven
``webbrowser.open``, ``open_new`` or ``open_new_tab``, and the probe reaches
none of the routes those functions dispatch through.
"""

from __future__ import annotations

from tests.fixtures.qt_wiring_counts import io_watched

WATCHED_MODULE = "src.core.log_paths"

WATCH_LAUNCHES = (
    "import os, subprocess, webbrowser\n"
    "launched = []\n"
    "class _Proc:\n"
    "    def wait(self):\n"
    "        return 0\n"
    "def _seen(kind):\n"
    "    def fire(*a, **k):\n"
    "        launched.append(kind)\n"
    "        return _Proc()\n"
    "    return fire\n"
    "for _name in ('startfile', 'system', 'posix_spawn', 'posix_spawnp'):\n"
    "    if hasattr(os, _name):\n"
    "        setattr(os, _name, _seen(_name))\n"
    "subprocess.Popen = _seen('Popen')\n"
    "subprocess.call = _seen('call')\n"
    "webbrowser.register(\n"
    "    'probe', None, webbrowser.GenericBrowser('probe-browser %s'),\n"
    "    preferred=True)\n"
)


def test_a_driven_browser_call_is_recorded_and_dispatches_nothing():
    """A driven ``webbrowser.open`` reached the operator's default browser."""
    answered = io_watched(
        WATCHED_MODULE,
        WATCH_LAUNCHES + "webbrowser.open('https://example.invalid')\n"
        "webbrowser.open_new('https://example.invalid')\n"
        "webbrowser.open_new_tab('https://example.invalid')\n"
        "assert launched == [], launched\n",
    )
    assert answered["touched"] == ["webbrowser"], answered


def test_the_launch_watch_reports_a_dispatch_it_is_shown():
    """POSITIVE CONTROL for ``WATCH_LAUNCHES``.

    A browser controller driven past ``refuse`` reaches ``subprocess.Popen``
    and is counted.
    """
    answered = io_watched(
        WATCHED_MODULE,
        WATCH_LAUNCHES + "webbrowser.get('probe').open('https://example.invalid')\n"
        "assert launched == ['Popen'], launched\n",
    )
    assert answered["touched"] == [], answered
