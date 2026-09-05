"""The build variant seam, the accumulating dist names, and the version reach.

Three behaviours are pinned here.

A build names its output after the version it resolved and the variant it
was asked for, and never claims a name already on disk. The application
resolves the variant it was built as and hands the History tab the matching
table class. And the version the package resolves is the version every
consumer reports, with no literal shadowing it.

No PyInstaller build runs. A full build takes minutes and would write into
``dist``, which the operator runs live executables from.
"""

from __future__ import annotations

import os

import pytest

from src import _variant
from src._variant import (
    DEFAULT_VARIANT,
    QT,
    REACT,
    VARIANTS,
    normalise,
    resolve_variant,
)
from tools.build_variants import (
    output_basename,
    requested_variant,
    sanitise,
    unique_output_basename,
    windows_file_version,
)


def test_the_output_name_carries_both_the_version_and_the_variant():
    name = output_basename("3.28.0", REACT)
    assert "3.28.0" in name, f"the version is missing from {name!r}"
    assert REACT in name, f"the variant is missing from {name!r}"


def test_two_variants_of_one_version_do_not_share_a_name():
    react = output_basename("3.28.0", REACT)
    qt = output_basename("3.28.0", QT)
    assert react != qt, f"both variants claimed the same folder {react!r}"


def test_two_versions_of_one_variant_do_not_share_a_name():
    older = output_basename("3.28.0", REACT)
    newer = output_basename("3.28.1", REACT)
    assert older != newer, f"both versions claimed the same folder {older!r}"


def test_a_local_version_segment_does_not_reach_the_folder_name():
    name = output_basename("3.28.0+dev.5.gabc1234", REACT)
    assert "+" not in name, f"'+' survived into the path name {name!r}"
    assert "dev.5.gabc1234" in name, f"the local segment was lost from {name!r}"


def test_sanitise_never_answers_empty():
    assert sanitise("+++") == "unknown", "an all-unsafe version produced no name"


def test_a_first_build_claims_the_plain_name(tmp_path):
    name = unique_output_basename(str(tmp_path), "3.28.0", REACT)
    assert name == output_basename(
        "3.28.0", REACT
    ), f"an empty dist should give the plain name, got {name!r}"


def test_a_rebuild_of_the_same_version_claims_a_new_name(tmp_path):
    first = unique_output_basename(str(tmp_path), "3.28.0", REACT)
    (tmp_path / first).mkdir()
    second = unique_output_basename(str(tmp_path), "3.28.0", REACT)
    assert (
        second != first
    ), f"the rebuild claimed {second!r}, the folder the first build holds"
    assert (tmp_path / first).exists(), "the first build was removed"


def test_repeated_rebuilds_keep_every_earlier_build(tmp_path):
    claimed = []
    for _ in range(4):
        name = unique_output_basename(str(tmp_path), "3.28.0", QT)
        (tmp_path / name).mkdir()
        claimed.append(name)
    assert len(set(claimed)) == 4, f"names collided across rebuilds: {claimed}"
    for name in claimed:
        assert (tmp_path / name).exists(), f"{name} was removed by a later build"


def test_naming_a_build_reads_the_disk_and_writes_nothing(tmp_path):
    unique_output_basename(str(tmp_path), "3.28.0", REACT)
    assert list(tmp_path.iterdir()) == [], "naming a build created something in dist"


def test_an_unset_build_variant_falls_back_to_the_default():
    assert requested_variant({}) == DEFAULT_VARIANT


def test_the_build_variant_is_read_from_the_environment():
    assert requested_variant({_variant.ENV_VAR: QT}) == QT


def test_an_unknown_build_variant_falls_back_rather_than_raising():
    answer = requested_variant({_variant.ENV_VAR: "electron"})
    assert answer == DEFAULT_VARIANT, f"an unknown variant answered {answer!r}"


@pytest.mark.parametrize("name", VARIANTS)
def test_every_declared_variant_normalises_to_itself(name):
    assert normalise(name) == name


def test_normalise_refuses_a_name_that_is_not_a_variant():
    assert normalise("qt6") == "", "an unknown name was accepted as a variant"


def test_a_baked_variant_is_what_a_bundle_reports(tmp_path, monkeypatch):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / _variant.BAKED_FILENAME).write_text("qt\n", encoding="utf-8")
    monkeypatch.setattr(_variant, "is_frozen", lambda: True)
    monkeypatch.setenv(_variant.ENV_VAR, REACT)
    assert (
        resolve_variant(tmp_path) == QT
    ), "an environment variable overrode the variant baked into the bundle"


def test_a_source_checkout_reads_the_variant_from_the_environment(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(_variant, "is_frozen", lambda: False)
    monkeypatch.setenv(_variant.ENV_VAR, QT)
    assert resolve_variant(tmp_path) == QT


def test_an_unstamped_checkout_reports_the_default(tmp_path, monkeypatch):
    monkeypatch.setattr(_variant, "is_frozen", lambda: False)
    monkeypatch.delenv(_variant.ENV_VAR, raising=False)
    assert resolve_variant(tmp_path) == DEFAULT_VARIANT


def test_the_qt_variant_selects_the_qt_table():
    pytest.importorskip("PySide6.QtWidgets")
    from src.gui.history_table_variant import history_table_class

    from src.gui.history_qt_table import HistoryQtTable

    assert history_table_class(QT) is HistoryQtTable


def test_the_react_variant_selects_the_react_table():
    pytest.importorskip("PySide6.QtWebEngineWidgets")
    from src.gui.history_table_variant import history_table_class

    from src.gui.react_history_panel import HistoryWebTable

    assert history_table_class(REACT) is HistoryWebTable


def test_the_two_variants_select_different_tables():
    pytest.importorskip("PySide6.QtWebEngineWidgets")
    from src.gui.history_table_variant import history_table_class

    assert history_table_class(QT) is not history_table_class(REACT), (
        "both variants selected the same table class; "
        "the two builds would be indistinguishable"
    )


def test_both_tables_answer_the_calls_the_history_tab_makes():
    """The tab holds the table through three calls and no others."""
    pytest.importorskip("PySide6.QtWebEngineWidgets")
    from src.gui.history_qt_table import HistoryQtTable
    from src.gui.react_history_panel import HistoryWebTable

    for name in ("set_model", "row_count", "model", "page_ready"):
        assert hasattr(HistoryQtTable, name), f"the Qt table has no {name}"
        assert hasattr(HistoryWebTable, name), f"the React table has no {name}"


def test_the_windows_file_version_follows_the_resolved_version():
    assert windows_file_version("3.28.0") == "3.28.0.0"


def test_a_local_segment_is_dropped_from_the_windows_file_version():
    assert windows_file_version("3.28.0+dev.5.gabc1234") == "3.28.0.0"


def test_the_windows_file_version_is_always_four_numbers():
    for version in ("3.28.0", "3.28.0+dev.5.gabc1234", "0.1.0+unknown", "nonsense"):
        field = windows_file_version(version)
        parts = field.split(".")
        assert len(parts) == 4, f"{version!r} produced {field!r}"
        assert all(p.isdigit() for p in parts), f"{version!r} produced {field!r}"


def test_the_windows_file_version_is_not_the_old_literal():
    """The resource fields read a hardcoded 1.1.0 until this seam existed."""
    assert windows_file_version("3.28.0") != "1.1.0.0"


def test_the_package_version_is_the_resolved_version():
    import src
    from src._version import resolve_version

    assert src.__version__ == resolve_version()


def test_the_setuptools_dynamic_version_reads_the_package():
    """pyproject declares the version dynamic against src.__version__."""
    import tomllib

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, "pyproject.toml"), "rb") as handle:
        config = tomllib.load(handle)
    assert (
        "version" in config["project"]["dynamic"]
    ), "pyproject stopped declaring the version dynamic; a literal would shadow it"
    attr = config["tool"]["setuptools"]["dynamic"]["version"]["attr"]
    assert attr == "src.__version__", f"setuptools reads {attr!r}, not the package"


def test_the_window_title_carries_the_running_version_when_none_is_given():
    """The bridge's default titled the window v0.0.0 while Qt showed the real one."""
    from src import __version__
    from src.gui.main_tabs import main_window_surface as mws

    model = mws.MainWindowModel()
    assert (
        model.version == __version__
    ), f"the surface defaulted to {model.version!r}, not the resolved version"


def test_the_bridge_view_model_titles_the_window_with_the_real_version():
    from src import __version__
    from src.gui.main_tabs import main_window_surface as mws

    title = mws.build_view_model({})["window_title"]
    assert __version__ in title, f"the bridge titled the window {title!r}"
    assert "0.0.0" not in title, f"the shadowing literal reached the title: {title!r}"
