# Did the mods Lumi asked for actually load?
# Run: bash bl2-mcp/tools/ask.sh bl2-mcp/tools/checks/bundled-mods.py
#
# Every other check in this folder tests Second Wind's own code. This one tests the thing nobody
# was watching: that the other mods in sdk_mods/ are present, imported, and switched on. A mod
# that fails to load is invisible - the mod menu simply has one fewer row, and nobody counts rows.
#
# NOTHING IS HARDCODED, on purpose. It counts what is on disk and asks the loader about each one.
# A list of eight names in here would go stale the first time a mod is added or renamed, and a
# stale list fails for the wrong reason, which is worse than not checking at all.
#
# Three outcomes per thing on disk, and the middle one is the reason this is not a two-way test:
#
#   loaded with a row   the loader knows it and the mod menu shows it. Normal.
#   loaded, no row      the module imported but registered no mod - which is exactly what a
#                       library like uemath or coroutines is meant to do. Not a failure.
#   not loaded at all   the module is not even in sys.modules. That is the real failure: the
#                       file is sitting there doing nothing.
#
# Read-only. It changes nothing, so there is nothing to put back.

import sys
import zipfile
from pathlib import Path

from mods_base import MODS_DIR, get_ordered_mod_list

reset()

# Folders in sdk_mods/ that are not mods.
NOT_MODS = {"settings", ".stubs", "__pycache__", ".git"}


def on_disk():
    """
    Everything in sdk_mods/ that claims to be a mod, as (what it is called on disk, module name).

    The module name for a .sdkmod is read out of the archive rather than guessed from the file
    name: they usually match, but the loader imports the folder INSIDE the zip, and that is the
    name that has to line up with what the loader reports.
    """
    found = []
    for path in sorted(Path(MODS_DIR).iterdir()):
        if path.is_dir():
            if path.name in NOT_MODS or not (path / "__init__.py").exists():
                continue
            found.append((path.name, path.name, "a folder"))
            continue
        if path.suffix != ".sdkmod":
            continue
        module, how = path.stem, "the file name (the archive could not be read)"
        try:
            with zipfile.ZipFile(path) as archive:
                tops = {name.split("/")[0] for name in archive.namelist() if "/" in name}
                if len(tops) == 1:
                    module, how = tops.pop(), "read out of the archive"
        except Exception as ex:
            how = f"the file name ({ex!r})"
        found.append((path.name, module, how))
    return found


things = on_disk()
print(f"{len(things)} things in {MODS_DIR} look like mods")

try:
    rows = list(get_ordered_mod_list())
    listed = "the loader answered"
except Exception as ex:
    rows = []
    listed = repr(ex)

check(
    "the loader will tell us what it has loaded",
    bool(rows),
    f"{len(rows)} rows in the mod menu - {listed}",
)

# Mods are matched to files by the settings file they save to, because that file is named after
# the module (mods_base/mod_factory.py:70). The display name is free text and cannot be relied on:
# alt_use_vendors calls itself "Alt Use Vendors", firing_fix calls itself something else again.
by_module = {}
for row in rows:
    settings_file = getattr(row, "settings_file", None)
    if settings_file is not None:
        by_module[settings_file.stem] = row

missing = []
no_row = []
disabled = []
disabled_library = []
report = []


def _is_library(row):
    """
    True if the mod menu itself already categorises this row as a library, not a mod.

    Same test already used at the bottom of this file for the "(library)"/"(mod)" tag. A real
    mods_base Library is always ON and cannot be switched off at all - its __post_init__
    enables itself once and then locks (mods_base/mod.py). The only way a library-typed row can
    show OFF here is a legacy mod wrapped through legacy_compat, where "library" is computed
    from Priority rather than forced on. UserFeedback is exactly that: its own description says
    it "does not do anything by itself", it declares no hooks or network methods, and it never
    opts into remembering its enabled state between launches - so OFF is its normal resting
    state every single launch, not a sign it failed to load.
    """
    return getattr(row, "mod_type", None) is not None and row.mod_type.name == "Library"


for disk_name, module, how in things:
    row = by_module.get(module)
    imported = module in sys.modules
    if row is not None:
        state = "ON " if row.is_enabled else "OFF"
        report.append(f"  {state}  {disk_name:<28} {row.name} {row.version}")
        if not row.is_enabled:
            (disabled_library if _is_library(row) else disabled).append(
                f"{row.name} ({disk_name})",
            )
    elif imported:
        no_row.append(f"{disk_name} (imported as {module})")
        report.append(f"  lib  {disk_name:<28} imported as {module}, registers no menu row")
    else:
        missing.append(f"{disk_name} (looked for the module {module}, {how})")
        report.append(f"  ??   {disk_name:<28} NOT LOADED - no module called {module}")

print("\n".join(report))

check(
    "every mod file in the folder actually got loaded by the game",
    not missing,
    f"{len(things) - len(missing)} of {len(things)} loaded; not loaded: {missing}",
)

check(
    "every ordinary (non-library) mod with a row in the menu is switched on",
    not disabled,
    f"switched off: {disabled} - a mod can be off because Lumi turned it off, so read this one "
    f"before treating it as a fault",
)

if disabled_library:
    print(
        f"\n{len(disabled_library)} library row(s) show OFF, and that is normal: a legacy "
        f"library's enabled flag does not gate anything, so this is not counted as a fault: "
        f"{disabled_library}",
    )

# A negative control, so a pass above cannot be a pass by accident. If this comes back saying a
# made-up mod IS loaded, the matching is broken and every line above is meaningless.
check(
    "a mod that does not exist is correctly reported as not loaded",
    "ThisModDoesNotExist" not in by_module and "ThisModDoesNotExist" not in sys.modules,
    "looked for ThisModDoesNotExist and did not find it",
)

if no_row:
    print(
        f"\n{len(no_row)} of them registered no menu row, which is what a library is supposed to "
        f"do: {no_row}",
    )

print(
    "\nEvery mod the loader knows about, including any that are not files in this folder:\n"
    + "\n".join(
        f"  {'ON ' if r.is_enabled else 'OFF'}  {r.name}  {r.version}  "
        f"({'library' if getattr(r, 'mod_type', None) is not None and r.mod_type.name == 'Library' else 'mod'})"
        for r in rows
    ),
)

summary()
