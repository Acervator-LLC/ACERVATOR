"""A build recipe that reads a name the packager does not bind.

`BUILD_LABEL` is assigned nowhere and injected by nothing, so the coding
archetype still reports it undefined and `known_bad.spec` exits 1.
"""

analysis = Analysis(
    ["main.py"],
    pathex=[SPECPATH, HOMEPATH],
    binaries=[],
    datas=[(SPEC, "."), (WARNFILE, ".")],
    hiddenimports=[],
    excludes=[],
)
archive = PYZ(analysis.pure, analysis.zipped_data)
executable = EXE(
    archive,
    analysis.scripts,
    name=BUILD_LABEL,
    console=False,
)
collected = COLLECT(executable, analysis.binaries, name=specnm)
staged = (DISTPATH, HOMEPATH, workpath)
