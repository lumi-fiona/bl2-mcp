# Game feel (configtweaks)

Source file: `D:/SteamLibrary/steamapps/common/Borderlands 2/sdk_mods/bl2_modern/features/configtweaks.py`

**Purpose.** Turns off mouse smoothing and landing camera shake, and sets the PhysX level and texture pool size, by writing each into the game's ini files and (for the two booleans) also into the running game.

## Claims

### 1. bEnableMouseSmoothing=False lands under [Engine.PlayerInput] in WillowInput.ini.

- proven today: **partly**
- evidence: Read this session: WillowInput.ini:8 under [Engine.PlayerInput] reads `bEnableMouseSmoothing=False`. No automated check asserts it — regress.py:1-99 covers only grinder and levelless.
- reachable: filesystem_only
- missing capability: (none)

**How to prove it:**

Runnable offline against the real file:
import pathlib
p = pathlib.Path.home()/'Documents/My Games/Borderlands 2/WillowGame/Config/WillowInput.ini'
sec = None
found = None
for ln in p.read_text(encoding='utf-8', errors='replace').splitlines():
    s = ln.strip()
    if s.startswith('[') and s.endswith(']'): sec = s
    elif sec == '[Engine.PlayerInput]' and s.lower().startswith('benablemousesmoothing='):
        found = s.split('=', 1)[1]
assert found == 'False', found

### 2. bLandingShake=False lands under [WillowGame.WillowPlayerController] in WillowGame.ini.

- proven today: **partly**
- evidence: Read this session: WillowGame.ini:189 under [WillowGame.WillowPlayerController] reads `bLandingShake=False`. The pristine backup at WillowGame.ini.bl2_modern_original:189 reads `bLandingShake=true`, so the pack made the change.
- reachable: filesystem_only
- missing capability: (none)

**How to prove it:**

Same scanner as above against WillowGame.ini with section '[WillowGame.WillowPlayerController]' and key 'blandingshake'; assert the value is exactly 'False'.

### 3. Both booleans take effect immediately, in the running session (configtweaks.py:42 and :55, 'Takes effect immediately').

- proven today: **no**
- evidence: (none)
- reachable: bridge_only
- missing capability: (none)

**How to prove it:**

Bridge — this is the single most important unrun check in this file:
from mods_base import get_pc
import unrealsdk
pc = get_pc()
print('live pc.bLandingShake      :', pc.bLandingShake)
print('live PlayerInput smoothing:', pc.PlayerInput.bEnableMouseSmoothing)
print('CDO bLandingShake         :', unrealsdk.find_class('WillowPlayerController').ClassDefaultObject.bLandingShake)
assert pc.bLandingShake is False
assert pc.PlayerInput.bEnableMouseSmoothing is False

### 4. `live = True` after ConsoleCommand means the console half actually worked (configtweaks.py:131-132, logged as 'and is live now').

- proven today: **no**
- evidence: (none)
- reachable: bridge_only
- missing capability: (none)

**How to prove it:**

Bridge, demonstrate the claim is unfounded then replace it with a real read-back:
pc.ConsoleCommand('set Engine.PlayerInput bNoSuchPropertyAtAll True')  # does not raise
# the honest version of line 132:
pc.ConsoleCommand('set WillowGame.WillowPlayerController bLandingShake False')
live = (pc.bLandingShake is False)
assert live

### 5. The game writes OUR in-memory value back into the file on exit, rather than undoing us (configtweaks.py:13-15).

- proven today: **no**
- evidence: (none)
- reachable: filesystem_only
- missing capability: (none)

**How to prove it:**

Three steps with the tooling that exists: (1) hand-edit WillowInput.ini so bEnableMouseSmoothing=True; (2) mcp__bl2__game_launch, wait for the main-menu apply, mcp__bl2__game_quit; (3) re-read the file and assert the value is 'False' and the file's mtime moved. If it comes back 'True', the in-memory half never reached the object the config writer serialises from.

### 6. Writing capitalised 'False' makes the setting settle, so no launch after the first reports a change (configtweaks.py:122-125).

- proven today: **no**
- evidence: (none)
- reachable: filesystem_only
- missing capability: (none)

**How to prove it:**

Launch, quit, launch again, then grep pyunrealsdk.log for 'configtweaks:' lines from the second launch and assert none of them contain 'went from'.

### 7. A no-change outcome reported as 'already off' is distinguishable from a feature that has quietly stopped working (configtweaks.py:149-152).

- proven today: **no**
- evidence: (none)
- reachable: filesystem_only
- missing capability: (none)

**How to prove it:**

Runnable offline right now — it demonstrates the claim is false:
from bl2_modern.gamefiles import apply_ini_edits
out, changed = apply_ini_edits(['[Engine.PlayerInput]\r\n','bEnableMouseSmoothing=False\r\n'],
                               '[Engine.PlayerInput]', {'bMisspelledKey': 'False'})
assert changed == {}   # passes: an absent key is reported identically to an already-correct one
out, changed = apply_ini_edits(['[Engine.PlayerInput]\r\n','bEnableMouseSmoothing=False\r\n'],
                               '[Wrong.Section]', {'bEnableMouseSmoothing': 'False'})
assert changed == {}   # passes: a wrong section is reported identically too

### 8. PhysXLevel=0 lands under [SystemSettings] in WillowEngine.ini and not in any other section.

- proven today: **partly**
- evidence: Read this session: WillowEngine.ini:1280 under [SystemSettings] reads `PhysXLevel=0`; the backup WillowEngine.ini.bl2_modern_original:1280 reads `PhysXLevel=2`, so the pack made the change. Exactly one PhysXLevel line exists in the file.
- reachable: filesystem_only
- missing capability: (none)

**How to prove it:**

Section-aware scan of WillowEngine.ini asserting exactly one PhysXLevel line, under '[SystemSettings]', equal to '0'.

### 9. The section scoping means the right PoolSize is edited and the unrelated one is untouched.

- proven today: **partly**
- evidence: Verified this session: WillowEngine.ini has two PoolSize keys — line 689 under [TextureStreaming] (changed 512 -> 160 by the pack) and line 2226 under [Wwise.ComponentPool] (still 200, untouched). The diff against WillowEngine.ini.bl2_modern_original shows only line 689 among the two.
- reachable: filesystem_only
- missing capability: (none)

**How to prove it:**

assert the file has PoolSize under [TextureStreaming] set by the option AND PoolSize under [Wwise.ComponentPool] still at its original value:
# scan WillowEngine.ini; expect {'[TextureStreaming]': '160', '[Wwise.ComponentPool]': '200'}

### 10. The texture-buffer option defaults OFF so the owner's PoolSize=512 stays (configtweaks.py:90-97 'Her setting stays').

- proven today: **no**
- evidence: (none)
- reachable: filesystem_only
- missing capability: (none)

**How to prove it:**

Runnable offline right now — it fails:
import json
s = json.load(open(r'D:\\SteamLibrary\\steamapps\\common\\Borderlands 2\\sdk_mods\\settings\\bl2_modern.json'))
assert s['options']['Game feel']['Keep the texture buffer at its stock size'] is False
# and the consequence on disk:
# assert PoolSize under [TextureStreaming] in WillowEngine.ini == '512'

### 11. Toggling one of these options in the mod menu writes the new value into the ini.

- proven today: **no**
- evidence: (none)
- reachable: bridge_only
- missing capability: (none)

**How to prove it:**

Bridge — fails today:
import pathlib
from bl2_modern.features import configtweaks as ct
p = pathlib.Path.home()/'Documents/My Games/Borderlands 2/WillowGame/Config/WillowEngine.ini'
opt = ct.NUMBERS[0][0]
before = p.read_text(encoding='utf-8', errors='replace')
opt.value = not opt.value
assert p.read_text(encoding='utf-8', errors='replace') != before, 'toggling the option wrote nothing'

### 12. The numbers take effect on the next launch (configtweaks.py:80, :106).

- proven today: **no**
- evidence: (none)
- reachable: filesystem_only
- missing capability: (none)

**How to prove it:**

Bridge + filesystem + lifecycle: toggle the option, immediately mcp__bl2__game_quit, then read WillowEngine.ini and assert the new value is present. It will not be, because nothing writes it until the next main-menu or character-load apply — so the engine only reads it the launch after that.

### 13. The file half is still done when the live half fails (configtweaks.py:133 comment).

- proven today: **no**
- evidence: (none)
- reachable: bridge_only
- missing capability: (none)

**How to prove it:**

Bridge — fails today:
import bl2_modern.features.configtweaks as ct
import pathlib
p = pathlib.Path.home()/'Documents/My Games/Borderlands 2/WillowGame/Config/WillowInput.ini'
_real = ct.get_pc
ct.get_pc = lambda *a, **k: (_ for _ in ()).throw(IndexError('no local player'))
try:
    ct._apply()          # must still reach edit_ini
    print('survived, ini half ran')
except Exception as ex:
    print('FAILED before any ini write:', repr(ex))
finally:
    ct.get_pc = _real

### 14. The .bl2_modern_original file is the file as it was before the pack ever touched it, so restoring is a rename (gamefiles.py:20-21, 128-131).

- proven today: **no**
- evidence: (none)
- reachable: filesystem_only
- missing capability: (none)

**How to prove it:**

Runnable offline right now — it fails:
import filecmp, pathlib
d = pathlib.Path.home()/'Documents/My Games/Borderlands 2/WillowGame/Config'
assert not filecmp.cmp(d/'WillowInput.ini', d/'WillowInput.ini.bl2_modern_original', shallow=False), \\
    'the pristine backup is byte-identical to the modified file'

## Suspected bugs

- **[breaks_the_feature]** configtweaks.py:119
  - `pc = get_pc()` sits outside every try block; the first `try:` does not start until line 130. mods_base's willow get_pc is `ENGINE._get_field(_GAME_PLAYERS_PROP)[0]._get_field(_ACTOR_PROP)` (mods_base/__init__.py:160-161), which raises IndexError on an empty GamePlayers rather than returning None.
  - bites: The comment at line 133 states the design intent explicitly — `except Exception as ex:  # noqa: BLE001 - the file half is still worth doing`. But if get_pc itself raises, `_apply()` dies before the loop starts and NEITHER ini write happens. core.py:464-466 then marks the whole 'Game feel' feature failed. The one guarantee the author wrote a comment to protect is the one the ordering breaks.

- **[breaks_the_feature]** configtweaks.py:148-152 (and the identical pattern at coopfixes.py:59-60)
  - `else:` / `logging.info(f"configtweaks: {key} is already {state} in {filename}")`, reached whenever `edit_ini` returns an empty dict. gamefiles.py:121-122 returns `{}` for 'already correct', and apply_ini_edits (gamefiles.py:88-89, `if low not in wanted or low in done: continue`) also produces no entry when the key is absent or the section name is wrong.
  - bites: A typo in a key name, a renamed section, or the game dropping a setting all report 'bLandingShake is already off in WillowGame.ini' — a confident success message for a write that never happened. The comment at lines 149-152 claims this branch is precisely what 'distinguishes it from a feature that has quietly stopped working'. It does not distinguish those cases at all; it merges them. This is the pack's stated primary failure mode reproduced inside the guard against it.

- **[breaks_the_feature]** configtweaks.py:95-97 vs sdk_mods/settings/bl2_modern.json:49 and WillowEngine.ini:689
  - The option is declared `BoolOption("Keep the texture buffer at its stock size", False, ...)` with a long comment at lines 90-94 explaining the default was corrected to OFF so 'Her setting stays' at 512. The saved settings file records `"Keep the texture buffer at its stock size": true` and WillowEngine.ini:689 reads `PoolSize=160` against `PoolSize=512` in WillowEngine.ini.bl2_modern_original.
  - bites: Changing a BoolOption's default does not migrate an already-saved settings file — mods_base/settings.py:36-42 loads the stored value whenever the identifier is present, which overwrites the new default. The 'correction' never took effect: the texture pool is sitting at 160 right now, the owner's 512 was overwritten, and the comment in the source asserts the opposite. This also proves settings loading works, so the mismatch cannot be explained away by settings never being read.

- **[wrong_in_an_edge_case]** configtweaks.py:33-115 (no on_change_anytime on any of the four BoolOptions) vs the descriptions at lines 42 and 55
  - Both TWEAKS descriptions end 'Takes effect immediately.' but neither option has an on_change_anytime callback, unlike coopfixes.py:77 which sets one for exactly this reason.
  - bites: Toggling 'Turn off mouse smoothing' in the mod menu runs no console command and writes no file. The value only reaches anything at the next `_apply_all()` — core.py:457-466 at the main menu, which is guarded to run once per process (core.py:452-454), or core.py:180-193 via register_save_options(on_load=apply_all) at the next character load. Toggle it at the main menu and quit and nothing was applied at all. The one word 'immediately' is false for the only path a player will ever use.

- **[wrong_in_an_edge_case]** configtweaks.py:130-132 and the log string at line 146
  - `pc.ConsoleCommand(f"set {owner} {key} ...")` followed unconditionally by `live = True`, and the log then prints `' and is live now' if live else ' but is NOT live this session'`.
  - bites: ConsoleCommand not raising proves nothing — UnrealScript's `set` silently does nothing for an unknown class or property, and it targets the class default object rather than the already-instantiated PlayerInput/PlayerController. So the log asserts liveness that was never read back, and the docstring's stronger claim at lines 13-14 ('Into the value the game is holding in memory right now') may well be false for the current session's objects. A one-line read-back — `live = (pc.bLandingShake is False)` — would turn the claim into a measurement.

- **[breaks_the_feature]** gamefiles.py:128-131, reached from configtweaks.py:137
  - `untouched = path.with_suffix(path.suffix + ORIGINAL_SUFFIX)` / `if not untouched.exists(): shutil.copy2(path, untouched)` — the pristine copy is taken lazily, at the moment of the first edit that happens to report a change, with nothing recording that the pack had already modified the file on an earlier run.
  - bites: Verified on disk this session: `cmp WillowInput.ini WillowInput.ini.bl2_modern_original` reports the two files byte-identical, and both read `bEnableMouseSmoothing=False` at line 8. The file named 'the file as it was before this pack ever touched it' (gamefiles.py:20-21) does not contain the owner's original value, so the promised restore-by-rename leaves mouse smoothing off. The pack's change to WillowInput.ini is currently unrevertable and nothing reports that.

- **[wrong_in_an_edge_case]** gamefiles.py:129-131, reached from configtweaks.py:166
  - The backup is a whole-file snapshot taken at an arbitrary moment, not a record of the keys the pack changed.
  - bites: Diffed this session: WillowEngine.ini.bl2_modern_original carries `ResX=2416`, `ResY=1360` and `FramerateLocking=6` while the live file carries `1920`, `1080` and `3`. None of those are keys the pack writes — the owner changed them after the snapshot. Restoring the backup to undo PhysXLevel and PoolSize would silently also revert the owner's resolution and framerate cap. A restore is advertised as safe and is not.
