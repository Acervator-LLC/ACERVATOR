"""A build recipe naming every global PyInstaller binds when it execs a spec file.

Every name here is bound by the packager, so the coding archetype reports no
undefined name and `known_good.spec` exits 0.
"""

tree = Tree(SPECPATH, prefix=specnm)
analysis = Analysis(
    ["main.py"],
    pathex=[SPECPATH, HOMEPATH],
    binaries=[],
    datas=[(SPEC, "."), (WARNFILE, ".")],
    hiddenimports=[],
    excludes=[],
)
merged = MERGE((analysis, specnm, specnm))
contents = TOC(analysis.pure)
splash = Splash(SPEC, binaries=analysis.binaries)
archive = PYZ(analysis.pure, analysis.zipped_data)
executable = EXE(
    archive,
    analysis.scripts,
    splash,
    name=specnm,
    console=False,
)
collected = COLLECT(executable, analysis.binaries, tree, name=specnm)
app = BUNDLE(collected, name=specnm, icon=os.fspath(SPEC))
staged = (DISTPATH, workpath)
