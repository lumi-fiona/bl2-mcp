# Sanity Saver

Source file: `D:/SteamLibrary/steamapps/common/Borderlands 2/sdk_mods/bl2_modern/features/sanitysaver.py`

**Purpose.** Make sure apple1417's Sanity Saver mod is not merely installed but actually switched on, so the game stops silently deleting items it does not recognise when a save loads.

## Claims

### 1. A mod named exactly 'Sanity Saver' is present in mods_base' mod list

- proven today: **partly**
- evidence: Human/log-observed once: sanitysaver.py:9-10 records 'Measured 2026-08-15: it registered as version 2.2 with enabled=False'. No automated check. The current D:/SteamLibrary/steamapps/common/Borderlands 2/Binaries/Win32/Plugins/unrealsdk.log contains no 'sanitysaver:' line at all, because that session never reached the main menu.
- reachable: bridge_only
- missing capability: (none)

**How to prove it:**

from mods_base import mod_list
from bl2_modern.features import sanitysaver as S
found = [m for m in mod_list.mod_list if m.name == S.NAME]
assert len(found) == 1, sorted(m.name for m in mod_list.mod_list)
print(found[0].name, found[0].version)

### 2. `from mods_base import mod_list` yields the module (so `mod_list.mod_list` is the list)

- proven today: **no**
- evidence: Relies on an import side effect: mods_base/__init__.py:38 does `from .mod_list import (...)`, which binds the submodule as an attribute of the package. sanitysaver.py:33 dereferences `mod_list.mod_list` OUTSIDE the try that wraps the import (sanitysaver.py:27-31), so a rename would raise past the guard.
- reachable: bridge_only
- missing capability: (none)

**How to prove it:**

import types
from mods_base import mod_list
assert isinstance(mod_list, types.ModuleType), type(mod_list)
assert isinstance(mod_list.mod_list, list)

### 3. If it is absent, the failure is loud and names every registered mod

- proven today: **no**
- evidence: Untested branch (sanitysaver.py:34-40).
- reachable: bridge_only
- missing capability: (none)

**How to prove it:**

from bl2_modern.features import sanitysaver as S
real = S.NAME
S.NAME = 'Definitely Not Installed'
S._enable()
S.NAME = real
# then read the tail of unrealsdk.log and assert the ERROR line with the mod list is there

### 4. If it is off, calling mod.enable() actually turns it on

- proven today: **no**
- evidence: Untested. The only evidence anywhere is the log line format at sanitysaver.py:53, and no such line exists in the current log.
- reachable: bridge_only
- missing capability: (none)

**How to prove it:**

from mods_base import mod_list
from bl2_modern.features import sanitysaver as S
m = [x for x in mod_list.mod_list if x.name == S.NAME][0]
m.disable()
assert m.is_enabled is False
S._enable()
assert m.is_enabled is True

### 5. is_enabled == True means Sanity Saver's hooks are really registered (i.e. it is doing something)

- proven today: **no**
- evidence: Nothing checks hooks. And mods_base sets the flag before doing the work: Mod.enable() assigns `self.is_enabled = True` at mods_base/mod.py:267 and only calls on_enable at mods_base/mod.py:276-277.
- reachable: bridge_only
- missing capability: (none)

**How to prove it:**

import sys
from unrealsdk.hooks import Type, has_hook
from legacy_compat.unrealsdk import _translate_hook_func_name
ss = next(m for k, m in sys.modules.items() if k.endswith('SanitySaver.hooks'))
missing = [f for f in ss.AllHooks
           if not has_hook(_translate_hook_func_name(f), Type.PRE,
                           'legacy_compat.unrealsdk:Sanity Saver')]
print(len(ss.AllHooks), 'declared,', len(missing), 'missing')
assert not missing, missing

### 6. 'already on' really means on - the early return at sanitysaver.py:43-45 is safe

- proven today: **no**
- evidence: Untested, and unsound: because mods_base/mod.py:267 sets is_enabled before mods_base/mod.py:276 runs on_enable, an on_enable that throws leaves the flag True with no hooks registered. Every subsequent run then takes the 'already on' branch.
- reachable: bridge_only
- missing capability: (none)

**How to prove it:**

import sys
from mods_base import mod_list
from unrealsdk.hooks import Type, has_hook
from legacy_compat.unrealsdk import _translate_hook_func_name
from bl2_modern.features import sanitysaver as S
m = [x for x in mod_list.mod_list if x.name == S.NAME][0]
ss = next(mm for k, mm in sys.modules.items() if k.endswith('SanitySaver.hooks'))
live = sum(1 for f in ss.AllHooks
           if has_hook(_translate_hook_func_name(f), Type.PRE,
                       'legacy_compat.unrealsdk:Sanity Saver'))
assert (m.is_enabled) == (live == len(ss.AllHooks)), \
    f'is_enabled={m.is_enabled} but {live}/{len(ss.AllHooks)} hooks live'

### 7. It runs at the main menu, after the bundled patch and before any character can load (sanitysaver.py:12-17)

- proven today: **no**
- evidence: The ordering is real in the code - core.py:455 runs run_bundled_patch() before the writes_game_data loop at core.py:457-466, and sanitysaver is index 5 in features/__init__.py FEATURES - but nothing asserts it, and the current log proves the sequence is skipped entirely when the game sits at the title screen (no patch line, no sanitysaver line, only `__init__.py@20 Second Wind 0.17.0 - 15 of 15 loaded`).
- reachable: filesystem_only
- missing capability: (none)

**How to prove it:**

import re, pathlib
log = pathlib.Path(r'D:/SteamLibrary/steamapps/common/Borderlands 2/Binaries/Win32/Plugins/unrealsdk.log').read_text(errors='replace').splitlines()
patch = next(i for i, l in enumerate(log) if 'commands run' in l)
sanity = next(i for i, l in enumerate(log) if 'sanitysaver:' in l)
assert patch < sanity, 'sanity saver ran before the patch'
assert not any('LoadPlayerSaveGame' in l for l in log[:sanity])

### 8. The part cache is clear once the pack's data changes have landed - the timing reason this feature exists at all (sanitysaver.py:12-15)

- proven today: **no**
- evidence: Never checked, and the early return at sanitysaver.py:43-45 skips the only thing that clears it. `SanitySaver.Enable()` calls `cached_obj_find.cache_clear()` at sdk_mods/SanitySaver/__init__.py:53; on any launch where the mod auto-enabled from its settings file (SaveEnabledState = LoadWithSettings, sdk_mods/SanitySaver/__init__.py:26), `_enable` returns at line 45 and never clears anything.
- reachable: bridge_only
- missing capability: (none)

**How to prove it:**

import sys
from bl2_modern.features import sanitysaver as S
h = next(m for k, m in sys.modules.items() if k.endswith('SanitySaver.helpers'))
print('cache before patch:', h.cached_obj_find.cache_info())
# ... after core.run_bundled_patch() and S._enable() have both run ...
info = h.cached_obj_find.cache_info()
assert info.currsize == 0, f'{info.currsize} part lookups cached from before the patch ran'

### 9. With it on, an item whose parts the game does not recognise survives a save-and-reload

- proven today: **no**
- evidence: This is the actual promise ('the single non-negotiable part of the pack', sanitysaver.py:7) and nothing tests it - not regress.py, not any note. Everything else in this file tests a flag.
- reachable: needs_input
- missing capability: Step 1 is bridge+filesystem today. Step 2 needs the character reloaded after a restart, which goes through game_load_character (bl2-mcp/server.py:180-208) and steals focus.

**How to prove it:**

# 1. establish the sidecar exists and moves
import unrealsdk, os, time
pc = unrealsdk.find_all('WillowPlayerController')[-1]
p = r'D:/SteamLibrary/steamapps/common/Borderlands 2/sdk_mods/SanitySaver/Saves/Save0104.json.gz'
t0 = os.path.getmtime(p)
pc.SaveGame(); time.sleep(3)
assert os.path.getmtime(p) > t0, 'Sanity Saver did not write its sidecar - it is not running'
# 2. the real end-to-end: note a uid + its part list, save, quit, relaunch, reload, compare
print([(int(i.DefinitionData.UniqueId), str(i.GetShortHumanReadableName()))
       for i in pc.GetPawnInventoryManager().Backpack])

### 10. Enabling it persists, so it is on next launch too

- proven today: **no**
- evidence: Not asserted. It should follow from mods_base/mod.py:279-280 (`if self.auto_enable: self.save_settings()`) plus auto_enable being True for LoadWithSettings (legacy_compat ModObjects.py:242), but nothing reads the file.
- reachable: filesystem_only
- missing capability: (none)

**How to prove it:**

import json, pathlib
from bl2_modern.features import sanitysaver as S
S._enable()
f = pathlib.Path(r'D:/SteamLibrary/steamapps/common/Borderlands 2/sdk_mods/settings/SanitySaver.json')
assert f.is_file(), f
assert json.loads(f.read_text()).get('enabled') is True, f.read_text()

### 11. It stays on for the rest of the session - a mid-session toggle-off is caught

- proven today: **no**
- evidence: core.on_main_menu is once-per-process (core.py:213, 440-441). The only re-check is core.apply_all, which runs from save_options' on_load (bl2_modern/__init__.py:39) - i.e. AFTER the character's items have already been loaded and validated (save_options/hooks.py:163-177 hooks LoadPlayerSaveGame POST, which is after EndLoadGame).
- reachable: bridge_only
- missing capability: (none)

**How to prove it:**

from mods_base import mod_list
from bl2_modern.core import apply_all
from bl2_modern.features import sanitysaver as S
m = [x for x in mod_list.mod_list if x.name == S.NAME][0]
m.disable()
apply_all()
assert m.is_enabled, 'apply_all did not re-enable it'

### 12. Declaring writes_game_data buys the right timing and nothing here has to know how (sanitysaver.py:15-17)

- proven today: **no**
- evidence: Half true and worth pinning: writes_game_data governs the main-menu pass (core.py:458) but core.apply_all ignores the flag entirely (core.py:189 checks only `apply is not None`), so this feature also re-runs on every character load whether or not that was intended.
- reachable: bridge_only
- missing capability: (none)

**How to prove it:**

from bl2_modern.core import all_features
f = [x for x in all_features() if x.name == 'Sanity Saver'][0]
assert f.writes_game_data is True and f.apply is not None and f.failed is None
assert f.hooks == []

## Suspected bugs

- **[breaks_the_feature]** sanitysaver.py:43-45
    if mod.is_enabled:
        logging.info(f"sanitysaver: {NAME} {mod.version} already on")
        return
  - The early return skips `cached_obj_find.cache_clear()`, which only runs inside SanitySaver's own Enable() (sdk_mods/SanitySaver/__init__.py:53). Sanity Saver declares SaveEnabledState = EnabledSaveType.LoadWithSettings (sdk_mods/SanitySaver/__init__.py:26), which legacy_compat maps to auto_enable=True (legacy_compat/ModMenu/ModObjects.py:242), so once the first successful enable writes the settings file the mod auto-enables at load time - long before core.run_bundled_patch() runs at the main menu.
  - bites: On every launch after the first, this feature takes the 'already on' path and the part cache is never cleared after the pack's ~4000-line patch.txt changes the data. That is precisely the failure the module docstring at sanitysaver.py:12-15 says it exists to prevent: parts cached as not existing. The feature logs a reassuring 'already on' while doing nothing about the one hazard it names.

- **[wrong_in_an_edge_case]** sanitysaver.py:47-53 - `mod.enable()` inside try, then `logging.info(... now enabled={mod.is_enabled})`
  - mods_base sets `self.is_enabled = True` at mods_base/mod.py:267, before calling on_enable at mods_base/mod.py:276-277. If SanitySaver's Enable() throws (it does real work: migrate_all(), unrealsdk.RunHook per hook), the exception is caught here and logged as 'would not switch on' - but is_enabled has already been left True.
  - bites: Every later run (core.apply_all on each character load) then hits the `if mod.is_enabled` early return and logs 'already on'. The mod is registered as enabled with zero hooks live, and the pack reports success forever. Nothing in the codebase checks hooks; has_hook() is available and would settle it in one line (sdk_mods/.stubs/unrealsdk/hooks/__init__.pyi:126).

- **[breaks_the_feature]** sanitysaver.py:53 - the only success signal is a log line
  - The feature's entire verification surface is `logging.info(...)`. The current unrealsdk.log (session of 2026-08-19 11:25) contains no 'sanitysaver:' line at all, and no Second Wind patch line either - the session never reached FrontendGFxMovie:Start. Nothing distinguishes 'ran and succeeded' from 'never ran'.
  - bites: The pack's most safety-critical component has no assertion anywhere. A filesystem check is available and free: sdk_mods/SanitySaver/Saves/ holds per-save sidecars (Save0104.json.gz etc., written by save_manager.py:43-44); their mtime after a save is a real end-to-end signal that the mod is running.

- **[cosmetic]** sanitysaver.py:33 `found = [m for m in mod_list.mod_list if m.name == NAME]` and line 42 `mod = found[0]`
  - `mod_list` is bound only by the import side effect of mods_base/__init__.py:38 (`from .mod_list import (...)`), and the dereference at line 33 is outside the try that guards the import at sanitysaver.py:27-31. Line 42 also silently takes the first of any duplicates.
  - bites: An AttributeError from line 33 escapes the feature's own error handling into core.on_main_menu, which sets feature.failed (core.py:463-465) - and core.apply_all then skips this feature permanently (core.py:189), removing the backstop as well.

- **[wrong_in_an_edge_case]** sdk_mods/SanitySaver/Saves/.json.gz (a file whose save-name stem is empty)
  - SaveManager builds its filename as `Path(save_name).stem + ... + '.json'` (save_manager.py:43). A file literally named `.json.gz` exists in that folder, meaning something constructed a SaveManager with an empty save name.
  - bites: Not this pack's code, but it means at least one save round-trip wrote its item data to an anonymous sidecar. If that ever collides across characters, item parts get restored onto the wrong save. Worth one look before trusting the 'non-negotiable' component.
