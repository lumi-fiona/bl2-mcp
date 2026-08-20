# Save backup and Sanity Saver - checks for the claims in AUDIT-RAW/save-backup.md
# and AUDIT-RAW/sanity-saver.md
# Run: bash bl2-mcp/tools/ask.sh bl2-mcp/tools/checks/save-backup-and-sanity.py
#
# NOTHING HERE TOUCHES A REAL SAVE. Every savebackup call runs against a throwaway folder under
# the system temp dir, and _back_up() is only ever reached through _back_up_here(), which refuses
# to run while the module still points at the owner's real SaveData folder. The saves themselves
# are read-only in this file - the on-disk half lives in save-backup-and-sanity-files.py.
#
# Sanity Saver is never disabled. Audit claim 4 ("if it is off, mod.enable() turns it on") would
# need a real disable, and a window with its hooks unregistered is exactly the window in which the
# game deletes items it does not recognise. That claim is left unchecked on purpose.
#
# The pack's own logging is RECORDED, not forwarded: the -files.py half counts 'savebackup:' lines
# in unrealsdk.log per launch, and fake lines written from here would silently break that count.

reset()

import shutil as real_shutil
import sys
import tempfile
import types
from pathlib import Path

from mods_base import mod_list

from bl2_modern import core
from bl2_modern.core import Feature

# Both feature modules are taken out of sys.modules rather than imported. The pack loaded them
# at startup, and importing either one FRESH has a side effect worth avoiding: savebackup runs
# _back_up() against the owner's real SaveData folder at module level (savebackup.py:89), and
# sanitysaver would register a second copy of the feature with the core.
SB = sys.modules.get("bl2_modern.features.savebackup")
SS = sys.modules.get("bl2_modern.features.sanitysaver")
if SB is None or SS is None:
    msg = (
        f"savebackup loaded={SB is not None}, sanitysaver loaded={SS is not None} - importing "
        "them from here would rotate the real backups, so this check stops instead"
    )
    raise RuntimeError(msg)


class LogSpy:
    """Stands in for unrealsdk.logging and remembers what the feature said."""

    def __init__(self):
        self.lines = []

    def info(self, message):
        self.lines.append(str(message))

    def warning(self, message):
        self.lines.append(str(message))

    def error(self, message):
        self.lines.append(str(message))

    def dev_warning(self, message):
        self.lines.append(str(message))

    def misc(self, message):
        self.lines.append(str(message))

    def text(self):
        return " | ".join(self.lines)


class BrokenCopy:
    """
    A shutil whose copy2 leaves a half-written file behind and then fails, as a real one does.

    `only` names the save it refuses; everything else it copies for real. It used to refuse
    EVERY copy, which meant the check below - "one save failing does not stop the others" -
    could not pass no matter what the code did, because there was no second save left to
    succeed. A test of a partial failure has to be partial.
    """

    def __init__(self, only=None):
        self.only = only
        self.refused = []

    def copy2(self, src, dst):
        if self.only is None or Path(src).name == self.only:
            self.refused.append(Path(src).name)
            Path(dst).write_bytes(b"half a save")
            raise OSError("simulated disk full")
        return REAL_SHUTIL.copy2(src, dst)


REAL_SAVEDATA = SB.savedata_dir
REAL_LOGGING = SB.logging
REAL_SHUTIL = SB.shutil
REAL_WARN_MB = SB.WARN_MB
REAL_NAME = SS.NAME
REAL_SS_LOGGING = SS.logging
REAL_CORE_LOGGING = core.logging
REAL_FEATURES = list(core._features)

spy = LogSpy()
temp_roots = []


def generations(backups, name):
    """The first byte of each of .1 to .5, or None where that generation is absent."""
    out = []
    for i in range(1, SB.DEPTH + 1):
        path = backups / f"{name}.{i}"
        out.append(path.read_bytes()[:1] if path.is_file() else None)
    return out


def new_root():
    root = Path(tempfile.mkdtemp(prefix="sw_savecheck_"))
    temp_roots.append(root)
    return root


def account_with(root, folder="76561198000000000", saves=(("Save0001.sav", b"A" * 100),)):
    acct = root / folder
    acct.mkdir()
    for name, data in saves:
        (acct / name).write_bytes(data)
    return acct


def back_up_here():
    """_back_up(), but only ever against a temp folder."""
    if SB.savedata_dir is REAL_SAVEDATA:
        raise RuntimeError("refusing to run _back_up against the real save folder")
    spy.lines.clear()
    SB._back_up()
    return spy.text()


try:
    SB.logging = spy
    SS.logging = spy

    # --- what the feature is set to do ---------------------------------------------------

    check(
        "the backup keeps five generations in a folder called bl2_modern_backups",
        (SB.DEPTH, SB.FOLDER, SB.WARN_MB) == (5, "bl2_modern_backups", 500),
        f"DEPTH={SB.DEPTH} FOLDER={SB.FOLDER!r} WARN_MB={SB.WARN_MB}",
    )

    # --- claim 3: depth is exactly five --------------------------------------------------

    root = new_root()
    backups = root / "b"
    backups.mkdir()
    save = root / "Save9999.sav"
    for i in range(7):
        save.write_bytes(bytes([i]) * 100)
        SB._rotate(save, backups)

    kept = sorted(p.name for p in backups.iterdir())
    check(
        "seven backups in a row leave exactly five generations on disk",
        kept == [f"Save9999.sav.{i}" for i in range(1, 6)],
        str(kept),
    )
    ages = [(backups / f"Save9999.sav.{i}").read_bytes()[0] for i in range(1, 6)]
    check(
        "the newest copy is at .1 and the oldest surviving one at .5",
        ages == [6, 5, 4, 3, 2],
        f"first byte of each generation, .1 to .5: {ages} (written 0..6 in order)",
    )

    # --- claim 4: an unchanged save does not consume a slot -------------------------------

    root = new_root()
    backups = root / "b"
    backups.mkdir()
    save = root / "Save9999.sav"
    save.write_bytes(b"unchanged" * 10)
    first = SB._rotate(save, backups)
    second = SB._rotate(save, backups)
    check(
        "backing up the same unchanged save twice only copies it once",
        first is True and second is False,
        f"first call returned {first}, second returned {second}",
    )
    check(
        "an unchanged save does not push a real backup down a generation",
        not (backups / "Save9999.sav.2").exists(),
        sorted(p.name for p in backups.iterdir()),
    )

    # --- claim 5: the copy is byte-identical ---------------------------------------------

    check(
        "the backup holds exactly the bytes of the save it came from",
        (backups / "Save9999.sav.1").read_bytes() == save.read_bytes(),
        f"{(backups / 'Save9999.sav.1').stat().st_size} vs {save.stat().st_size} bytes",
    )
    check(
        "the backup keeps the save's own timestamp, so the two can be compared later on disk",
        (backups / "Save9999.sav.1").stat().st_mtime_ns == save.stat().st_mtime_ns,
        f"{(backups / 'Save9999.sav.1').stat().st_mtime_ns} vs {save.stat().st_mtime_ns}",
    )

    # --- claim 2: every Save*.sav gets a copy, and nothing else does ----------------------

    root = new_root()
    acct = account_with(
        root,
        saves=(
            ("Save0001.sav", b"A" * 100),
            ("Save0002.sav", b"B" * 50),
            ("Save0002.sav.bak", b"the game's own single backup"),
            ("profile.bin", b"not a save"),
        ),
    )
    SB.savedata_dir = lambda: root
    said = back_up_here()
    made = sorted(p.name for p in (acct / SB.FOLDER).iterdir())
    # "SanitySaver" is a FOLDER the feature makes for the item-parts sidecars, not a copied
    # save. Both expectations below were written before sidecars were backed up at all, and had
    # been failing for the feature doing more than it used to rather than less.
    saves_made = sorted(n for n in made if n != "SanitySaver")
    check(
        "every save in the account folder gets a copy, and nothing that is not a save does",
        saves_made == ["Save0001.sav.1", "Save0002.sav.1"],
        f"{made}, alongside a .sav.bak and a profile.bin that must not be copied",
    )
    check(
        "the feature reports how many saves it found and how many it copied",
        "2 saves, 2 newly copied" in said and "5 deep" in said,
        said,
    )
    check(
        "every copy it just made matches its save byte for byte",
        all(
            (acct / SB.FOLDER / f"{n}.1").read_bytes() == (acct / n).read_bytes()
            for n in ("Save0001.sav", "Save0002.sav")
        ),
        "compared Save0001.sav and Save0002.sav against their .1 copies",
    )

    said = back_up_here()
    check(
        "a second launch with nothing changed copies nothing",
        "2 saves, 0 newly copied" in said,
        said,
    )

    (acct / "Save0001.sav").write_bytes(b"C" * 120)
    said = back_up_here()
    check(
        "only the save that changed is copied again",
        "2 saves, 1 newly copied" in said
        and (acct / SB.FOLDER / "Save0001.sav.2").read_bytes() == b"A" * 100,
        f"{said}; .2 now holds the previous contents",
    )

    # --- claim 8: it refuses to guess when the account folder is ambiguous ----------------

    root = new_root()
    account_with(root, folder="76561198000000001")
    account_with(root, folder="76561198000000002")
    SB.savedata_dir = lambda: root
    said = back_up_here()
    check(
        "two account folders make it back off rather than guess",
        "expected one account folder" in said and "nothing backed up" in said,
        said,
    )
    check(
        "backing off means neither account folder is written to at all",
        not any((root / p).joinpath(SB.FOLDER).exists() for p in ("76561198000000001", "76561198000000002")),
        sorted(str(p.relative_to(root)) for p in root.rglob("*")),
    )

    root = new_root()
    (root / "not_a_number").mkdir()
    SB.savedata_dir = lambda: root
    said = back_up_here()
    check(
        "a save folder with no numbered account in it is reported, not silently skipped",
        "expected one account folder" in said and "['none']" in said,
        said,
    )

    root = new_root()
    missing = root / "gone"
    SB.savedata_dir = lambda: missing
    said = back_up_here()
    check(
        "a missing save folder is named in the warning",
        "no save folder at" in said and str(missing) in said,
        said,
    )

    # --- claim 9: it warns when the folder passes the size mark ---------------------------

    root = new_root()
    acct = account_with(root)
    SB.savedata_dir = lambda: root
    SB.WARN_MB = 0
    said = back_up_here()
    check(
        "passing the size mark produces a warning naming the mark and the folder",
        "past the 0 MB mark" in said and str(acct / SB.FOLDER) in said,
        said,
    )
    SB.WARN_MB = REAL_WARN_MB
    said = back_up_here()
    check(
        "a folder under the size mark says nothing about size",
        "mark worth looking at" not in said,
        said,
    )

    # --- the two ways a failed copy costs a real backup (save-backup.md, suspected bugs) --
    #
    # savebackup.py:44-52 unlinks .5 and shifts .1-.4 up BEFORE shutil.copy2 runs, and copies
    # straight onto .1 rather than to a .part it then replaces. Both checks below are expected
    # to FAIL against today's source; they are written as the claim the docstring makes
    # ("a half-copied save is worse than no copy at all"), not as a description of the code.

    root = new_root()
    acct = account_with(
        root,
        saves=(("Save0001.sav", b"A" * 100), ("Save0002.sav", b"B" * 100)),
    )
    backups = acct / SB.FOLDER
    backups.mkdir()
    for i in range(1, 6):
        (backups / f"Save0001.sav.{i}").write_bytes(bytes([i]) * 100)

    was = generations(backups, "Save0001.sav")
    SB.savedata_dir = lambda: root
    SB.shutil = BrokenCopy(only="Save0001.sav")
    failed_with = None
    try:
        back_up_here()
    except Exception as ex:  # noqa: BLE001 - the point of the test is what escapes
        failed_with = repr(ex)
    SB.shutil = REAL_SHUTIL
    now = generations(backups, "Save0001.sav")

    check(
        "a copy that fails halfway costs none of the backups that already existed",
        now == was,
        f"copy2 raised {failed_with}; generations .1 to .5 held {was} before and {now} after - "
        "savebackup.py:44-50 unlinks the oldest and shifts the rest up before it copies",
    )
    check(
        "a copy that fails halfway leaves no half-written file at .1",
        now[0] in (None, was[0]),
        f".1 now starts {now[0]!r}, which is neither absent nor the {was[0]!r} it held before",
    )
    check(
        "one save failing to copy does not stop the others being backed up",
        (backups / "Save0002.sav.1").exists(),
        f"copy2 refused Save0001.sav and copied Save0002.sav; back_up raised {failed_with}. "
        "A raise that escapes the per-save try costs every save after the broken one its backup",
    )

    SB.savedata_dir = REAL_SAVEDATA

    # --- claim 10: one broken feature does not take the pack down ------------------------
    #
    # Run against a scratch feature list, so nothing real is imported, applied or renamed.

    core._features[:] = []
    core.load_features(["no_such_feature_a", "no_such_feature_b"])
    scratch = core.all_features()
    check(
        "a feature that will not import is recorded and the next one is still tried",
        [f.name for f in scratch] == ["no_such_feature_a", "no_such_feature_b"]
        and all(f.failed for f in scratch),
        f"{[f.name for f in scratch]}, failures recorded: {[bool(f.failed) for f in scratch]}",
    )

    core._features[:] = [Feature(name="fine"), Feature(name="broken", failed="boom")]
    check(
        "the status line names the feature that failed",
        core.status_line().endswith("1 of 2 loaded - FAILED: broken"),
        core.status_line(),
    )

    ran = []
    core.logging = spy  # the raising probe below logs an error; keep it out of unrealsdk.log
    core._features[:] = [
        Feature(name="menu only", writes_game_data=True, apply=lambda: ran.append("menu only")),
        Feature(name="raiser", apply=lambda: 1 / 0),
        Feature(name="no data", writes_game_data=False, apply=lambda: ran.append("no data")),
        Feature(name="already broken", failed="boom", apply=lambda: ran.append("already broken")),
    ]
    core.apply_all()
    check(
        "re-applying keeps going after a feature raises, and skips one that failed to load",
        ran == ["menu only", "no data"],
        f"applied {ran}",
    )
    check(
        "re-applying runs every feature with an apply, not only the ones that write game data",
        "no data" in ran,
        "core.apply_all checks `apply is not None` and ignores writes_game_data (core.py:189), "
        "so sanitysaver re-runs on every character load as well as at the main menu",
    )

    core._features[:] = REAL_FEATURES
    core.logging = REAL_CORE_LOGGING

    # --- Sanity Saver: is it there, and is it on -----------------------------------------

    check(
        "mods_base.mod_list is a module whose mod_list is a list",
        isinstance(mod_list, types.ModuleType) and isinstance(mod_list.mod_list, list),
        f"{type(mod_list).__name__}, holding {len(getattr(mod_list, 'mod_list', []))} mods",
    )

    found = [m for m in mod_list.mod_list if m.name == SS.NAME]
    check(
        "exactly one mod called Sanity Saver is registered",
        len(found) == 1,
        f"{len(found)} found among {sorted(m.name for m in mod_list.mod_list)}",
    )

    ss_mod = found[0] if found else None
    check(
        "Sanity Saver is switched on",
        ss_mod is not None and ss_mod.is_enabled,
        f"version {getattr(ss_mod, 'version', '?')}, is_enabled={getattr(ss_mod, 'is_enabled', None)}",
    )

    # --- claims 5 and 6: the flag against the hooks that do the work ----------------------

    # SanitySaver is a legacy-SDK mod: the mod manager imports it as Mods.SanitySaver, and
    # legacy_compat pops every "Mods.*" entry back OUT of sys.modules the moment that one import
    # call returns (legacy_compat/__init__.py, import_compat_handler) - they only live in
    # sys.modules for the length of a `with legacy_compat():` block, which is how Sanity Saver's
    # own hooks see them each time the game calls one. A plain sys.modules scan from outside one
    # of those blocks finds nothing, which is why this used to read 0 hooks no matter what Sanity
    # Saver had declared. Traced 2026-08-20 through __main__.py's import_mods() and the pop-on-
    # exit in legacy_compat/__init__.py's import_compat_handler; not measured against a live game,
    # since this check only runs there. Falls back to a no-op if legacy_compat cannot be imported
    # at all, so a genuinely missing shim still fails the check below instead of crashing here.
    try:
        from legacy_compat import legacy_compat as _legacy_compat
    except Exception:  # noqa: BLE001
        from contextlib import nullcontext as _legacy_compat

    with _legacy_compat():
        ss_hooks = next(
            (m for k, m in list(sys.modules.items()) if k.endswith("SanitySaver.hooks")),
            None,
        )
    check(
        "Sanity Saver's hook table is loaded and not empty",
        ss_hooks is not None and len(ss_hooks.AllHooks) > 0,
        f"{len(ss_hooks.AllHooks) if ss_hooks else 0} hooks declared",
    )

    # The hook identifier is built by legacy_compat as f"{__name__}:{hook_id}"
    # (legacy_compat/unrealsdk/__init__.py:216), and Sanity Saver passes its own name as the id.
    ask_the_sdk = None
    try:
        from legacy_compat.unrealsdk import _translate_hook_func_name
        from unrealsdk.hooks import Type, has_hook

        ask_the_sdk = True
    except Exception as ex:  # noqa: BLE001
        check("the sdk can be asked which hooks are registered", False, repr(ex))

    live = missing_hooks = None
    if ss_hooks is not None and ask_the_sdk:
        missing_hooks = [
            name
            for name in ss_hooks.AllHooks
            if not has_hook(
                _translate_hook_func_name(name), Type.PRE, "legacy_compat.unrealsdk:Sanity Saver",
            )
        ]
        live = len(ss_hooks.AllHooks) - len(missing_hooks)
        check(
            "every hook Sanity Saver declares is actually registered with the sdk",
            not missing_hooks,
            f"{live} of {len(ss_hooks.AllHooks)} live, missing {missing_hooks}",
        )
        check(
            "the enabled flag agrees with the hooks that are really registered",
            bool(ss_mod and ss_mod.is_enabled) == (live == len(ss_hooks.AllHooks)),
            f"is_enabled={getattr(ss_mod, 'is_enabled', None)} with {live} of "
            f"{len(ss_hooks.AllHooks)} hooks live - mods_base sets the flag at mod.py:267 before "
            "calling on_enable at :276, so a throwing Enable() leaves it True with no hooks",
        )

    # --- claim 12: what the feature declares to the core ----------------------------------

    entry = [f for f in core.all_features() if f.name == "Sanity Saver"]
    check(
        "the core holds one Sanity Saver feature, loaded, with an apply and no hooks of its own",
        len(entry) == 1
        and entry[0].writes_game_data is True
        and entry[0].apply is not None
        and entry[0].failed is None
        and entry[0].hooks == [],
        (
            f"{len(entry)} entries"
            + (
                f", writes_game_data={entry[0].writes_game_data}, apply={entry[0].apply is not None}, "
                f"failed={entry[0].failed!r}, hooks={entry[0].hooks}"
                if entry
                else ""
            )
        ),
    )

    # --- claim 3: an absent Sanity Saver fails loudly and names every mod -----------------

    spy.lines.clear()
    SS.NAME = "Definitely Not Installed"
    SS._enable()
    SS.NAME = REAL_NAME
    said = spy.text()
    check(
        "if Sanity Saver is missing the failure says so and names what is registered instead",
        "is not installed" in said and "Sanity Saver" in said and "items can be deleted" in said,
        said[:300],
    )

    # --- claim 8: the part cache, which is the reason this feature exists at all ----------
    #
    # savebackup's sibling bug: _enable returns early when the mod is already on
    # (sanitysaver.py:43-45), and cached_obj_find.cache_clear() only runs inside SanitySaver's
    # own Enable() (SanitySaver/__init__.py:53). Sanity Saver auto-enables from its settings
    # file long before the pack's patch runs, so on every launch after the first the cache is
    # never cleared. The second check below is expected to FAIL, and that is the bug.

    # Same visibility gap as the hooks lookup above: SanitySaver.helpers only sits in
    # sys.modules while a `with legacy_compat():` block is open, so this also has to look from
    # inside one rather than scanning sys.modules cold.
    with _legacy_compat():
        helpers = next(
            (m for k, m in list(sys.modules.items()) if k.endswith("SanitySaver.helpers")),
            None,
        )
    before = helpers.cached_obj_find.cache_info().currsize if helpers else None

    spy.lines.clear()
    SS._enable()
    said = spy.text()
    after = helpers.cached_obj_find.cache_info().currsize if helpers else None

    check(
        "applying the feature again takes the 'already on' path",
        "already on" in said,
        said,
    )
    check(
        "the part cache is empty once the pack's data changes have landed",
        after == 0,
        f"{before} lookups cached before applying, {after} after - anything cached before the "
        "pack's patch ran remembers parts as they were, which is the deletion this feature "
        "exists to prevent",
    )

finally:
    SB.savedata_dir = REAL_SAVEDATA
    SB.logging = REAL_LOGGING
    SB.shutil = REAL_SHUTIL
    SB.WARN_MB = REAL_WARN_MB
    SS.NAME = REAL_NAME
    SS.logging = REAL_SS_LOGGING
    core.logging = REAL_CORE_LOGGING
    core._features[:] = REAL_FEATURES
    for path in temp_roots:
        real_shutil.rmtree(path, ignore_errors=True)
    print(
        f"restored: savedata_dir={SB.savedata_dir is REAL_SAVEDATA} "
        f"WARN_MB={SB.WARN_MB} NAME={SS.NAME!r} features={len(core._features)} "
        f"temp folders removed={sum(1 for p in temp_roots if not p.exists())}/{len(temp_roots)}",
    )

summary()
