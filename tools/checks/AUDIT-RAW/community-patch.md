# Community Patch

Source file: `D:/SteamLibrary/steamapps/common/Borderlands 2/sdk_mods/bl2_modern/features/communitypatch.py`

**Purpose.** Turns the Unofficial Community Patch 5.0.4 into 19 on/off switches in the mod menu, so the player can pick which of its ~5,200 console commands the pack fires at the main menu.

## Claims

### 1. Every one of the 19 switch names matches a real <category name=...> inside data/patch.txt, so no switch is a dead menu row.

- proven today: **yes**
- evidence: patchsections.py:136-144 (assert not missing / assert not unlisted / per-name EXPECTED_COUNTS assert); ran 2026-08-19, exit 0
- reachable: filesystem_only
- missing capability: (none)

**How to prove it:**

cd sdk_mods/bl2_modern && python patchsections.py  -> asserts `missing = [n for n in names if n not in found]` is empty and that each section's command count still equals EXPECTED_COUNTS. I ran it today: 'all 19 switches match the shipped patch, command counts unchanged'.

### 2. Ticking a section OFF stops that section's commands being sent to the console.

- proven today: **partly**
- evidence: patchfile.py:244-245 proves the parser only; nothing proves feature->core->parser
- reachable: bridge_only
- missing capability: (none)

**How to prove it:**

Parser half is proven offline (patchfile.py:244-245 `none_wanted, _, _ = commands_from(SWITCHED_OFF, set()); assert none_wanted == []`). The wiring half is unproven. In-game: `from bl2_modern.features import communitypatch as cp; from bl2_modern import core; import pathlib; from bl2_modern.patchfile import commands_from; cp._section_options['Cosmetic Changes'].value = False; t = pathlib.Path(core.__file__).parent.joinpath('data/patch.txt').read_text(encoding='utf-8',errors='replace'); c,h,_ = commands_from(t, cp.wanted_sections()); assert not any('cosmetic' in str(x).lower() for x in []) ; print(len(c)+len(h))` and assert the total drops by exactly 1119 (Cosmetic Changes' count from patchsections.py:76).

### 3. The commands the pack sends actually change the live objects — i.e. `pc.ConsoleCommand(cmd)` is not a no-op the way `exec` was.

- proven today: **no**
- evidence: (none)
- reachable: bridge_only
- missing capability: (none)

**How to prove it:**

This is the big one and nothing checks it. In game_eval, run the sentinel-sandwich on a numeric-valued sample:
```
import unrealsdk, pathlib, random
from bl2_modern.patchfile import commands_from
from bl2_modern.features.communitypatch import wanted_sections
pc = unrealsdk.find_all('WillowPlayerController')[-1]
t = pathlib.Path(r'D:/SteamLibrary/steamapps/common/Borderlands 2/sdk_mods/bl2_modern/data/patch.txt').read_text(encoding='utf-8', errors='replace')
cmds, hot, _ = commands_from(t, wanted_sections())
every = cmds + [c for lvl, c in hot if lvl in ('None','')]
landed = nochange = unresolved = 0; misses = []
for cmd in random.Random(0).sample(every, 300):
    p = cmd.split(None, 3)
    if len(p) < 4 or p[0].lower() != 'set': continue
    _, path, prop, want = p
    base = prop.split('[')[0].split('.')[0]
    try:
        o = unrealsdk.find_object('Object', path); before = str(getattr(o, base))
    except Exception:
        unresolved += 1; continue
    if not before.replace('.','',1).replace('-','',1).isdigit(): continue
    pc.ConsoleCommand(f'set {path} {prop} 123456')
    mid = str(getattr(o, base))
    pc.ConsoleCommand(cmd)
    after = str(getattr(o, base))
    if after != mid: landed += 1
    else:
        nochange += 1
        if len(misses) < 20: misses.append((path, prop, mid, after))
print('landed', landed, 'inert', nochange, 'unresolvable', unresolved); print(misses)
assert nochange == 0, misses
```
The sentinel removes the 'it was already correct' confound.

### 4. The log line 'N commands run, M failed' is evidence the patch worked.

- proven today: **no**
- evidence: (none)
- reachable: bridge_only
- missing capability: (none)

**How to prove it:**

It is not evidence and this is provable by reading core.py:303-317: `_run` increments `ran` whenever `pc.ConsoleCommand(command)` does not raise. `ConsoleCommand` returns nothing and does not raise on a bad object path, so `ran` == len(commands) and `failed` == 0 essentially always. Falsify it in one line: `pc.ConsoleCommand('set No.Such.Object NoSuchProp 1')` and confirm no exception is raised — then `core._run(['set No.Such.Object NoSuchProp 1'])` must return `(1, 0)`. assert core._run(['set No.Such.Object NoSuchProp 1']) == (1, 0)

### 5. 3,669 commands run at the main menu at documented defaults (8 sections on, 0 extras); 4,511 at the settings currently on disk.

- proven today: **yes**
- evidence: measured 2026-08-19 with sdk_mods/bl2_modern/patchfile.py:150 commands_from over data/patch.txt
- reachable: filesystem_only
- missing capability: (none)

**How to prove it:**

Offline count against the shipped data file: `commands_from(patch.txt, {n for n,s,on,w in SECTIONS if on})` -> 1907 plain + 1762 level='None' hotfixes = 3669, plus 370 held for maps. With the live bl2_modern.json set (16 sections ticked) it is 4511 + 479 held. I ran this today.

### 6. 370 of the patch's commands are map-gated at defaults (479 with the live settings, 675 if every switch is on), spread over 80 distinct map names once case is folded, and each set runs when its map loads.

- proven today: **no**
- evidence: counts measured 2026-08-19; delivery unmeasured
- reachable: needs_map_travel
- missing capability: an unattended way to fast-travel, or a save per target map so game_load_character lands in each one

**How to prove it:**

The counts are measured (filesystem). The *delivery* is not. In-game, after a character is loaded: `from bl2_modern import core; import unrealsdk; pc = unrealsdk.find_all('WillowPlayerController')[-1]; print(len(core._by_level), sum(len(v) for v in core._by_level.values()), core._map_done, core._current_map(pc)); assert core._map_done is not None and core._map_done in core._by_level` — proves the watcher matched THIS map. Repeat per map for coverage.

### 7. Map names are compared case-insensitively, so both 'BackBurner_P' and 'Backburner_P' (the patch spells it both ways) are honoured.

- proven today: **partly**
- evidence: measured 2026-08-19: {'backburner_p': {'BackBurner_P','Backburner_P'}} in the enabled hotfix set; core.py:291 and core.py:364 both .lower()
- reachable: bridge_only
- missing capability: (none)

**How to prove it:**

I confirmed the two spellings exist in the enabled set today and that core.py:291 lowercases (`_by_level.setdefault(level.lower(), ...)`) and core.py:364 lowercases what the game reports. Assert it end to end: `from bl2_modern import core; assert 'backburner_p' in core._by_level and len(core._by_level['backburner_p']) == 4` — 4 is the measured count of BackBurner_P + Backburner_P commands at shipped defaults.

### 8. A section the player ticks runs whole, including the commands the UCP authors flagged off — 'the only way an opt-in extra can ever do anything'.

- proven today: **partly**
- evidence: patchfile.py:237-238 for the parser; the 1-command side effect measured 2026-08-19
- reachable: filesystem_only
- missing capability: (none)

**How to prove it:**

Parser proven offline: patchfile.py:237-238 `chosen, _, _ = commands_from(SWITCHED_OFF, {'An extra'}); assert chosen == ['set Extra.Object Prop 3']`. What is NOT checked is the side effect on the eight always-on sections. Measured today: exactly 1 UCP-disabled command lives inside a default-on section (Fixes > ... > Pete's Death Explosion > No Explosion, patch.txt line 999) and Second Wind fires it anyway. Assert deliberately: `c,h,_ = commands_from(text, {'Fixes'}); assert sum(1 for x in c+[y[1] for y in h] if 'BodyDeath_Iris_Raid_PyroPete' in x) == 1` and decide whether that is intended.

### 9. The eleven optional extras are off by default, so a fresh install behaves like the patch does.

- proven today: **no**
- evidence: read sdk_mods/settings/bl2_modern.json (written 2026-08-19 13:10): 8 extras true
- reachable: filesystem_only
- missing capability: (none)

**How to prove it:**

The constructor default is right (`_switch(name, short, False, what)`, communitypatch.py:69) but nothing asserts the settings file agrees, and it currently does not: sdk_mods/settings/bl2_modern.json has 8 of the 11 extras `true`, including 'Less Dumb Visuals v3.2.0' (664 commands). Filesystem check: `import json; from bl2_modern.patchsections import EXTRAS; d = json.load(open(r'D:/.../sdk_mods/settings/bl2_modern.json'))['options']['Community Patch']; on = [n for n,*_ in EXTRAS if d.get(n)]; assert not on, on`

### 10. Turning the master switch off makes none of the sections below run.

- proven today: **no**
- evidence: (none)
- reachable: bridge_only
- missing capability: (none)

**How to prove it:**

`from bl2_modern.features import communitypatch as cp; cp.enabled.value = False; assert cp.wanted_sections() is None` then `from bl2_modern import core; core._patch_has_run = False; core._by_level.clear(); core._repeat_on_level_load.clear(); core.run_bundled_patch(); assert not core._by_level` (the Community Patch is the only feature contributing map-gated commands other than 4 from Text Fixes, so assert the count is exactly 4 with extras on).

### 11. A changed switch takes effect next launch and never mid-session.

- proven today: **partly**
- evidence: core.py:215-217 early return on _patch_has_run
- reachable: bridge_only
- missing capability: (none)

**How to prove it:**

Guaranteed structurally by core.py:213 `_patch_has_run` and core.py:214 `_main_menu_done`, both one-shot. Assert it: `from bl2_modern import core; assert core._patch_has_run and core._main_menu_done` after the menu, and confirm returning to the main menu does not re-run by reading the log for a second 'Community Patch applied' line: `game_log(only='Community Patch applied')` must show exactly one line per launch.

### 12. Renaming the switch identifier from 'Community Patch' to 'Use the Community Patch' removes the once-per-launch `'True' is not a valid value for option 'Community Patch'` log line.

- proven today: **no**
- evidence: (none)
- reachable: bridge_only
- missing capability: (none)

**How to prove it:**

The module names its own stop condition (communitypatch.py:40-42). Run it: quit, relaunch, then `game_log(lines=400, only='is not a valid value for option')` and assert the result is empty. If a line remains naming a different option, the hypothesis is dead and the comment must be corrected.

### 13. The 'Skip rendered cutscenes' extra actually skips cutscenes; 'Hide damage numbers' actually hides them; 'Calmer visual effects' actually calms them.

- proven today: **no**
- evidence: (none)
- reachable: needs_screenshot
- missing capability: screen capture, plus a human to say whether a cutscene was skipped

**How to prove it:**

These are the three switches whose effect is only visible on screen. The reachable half is object-state: for 'Hide Damage Numbers/Critical/Resist' (4 commands) pull the commands out of the file, resolve each target with `unrealsdk.find_object('Object', path)` and assert the property now equals the patched value. The 'looks right on screen' half cannot be reached.

## Suspected bugs

- **[breaks_the_feature]** core.py:303-317, `_run` — reported through this feature's only log line at core.py:296-300
  - `for command in commands: try: pc.ConsoleCommand(command) except ...: failed += 1 else: ran += 1`. `ConsoleCommand` on a `set` naming an unloaded or misspelled object neither raises nor returns a status, so `ran` is just `len(commands)` and `failed` is essentially always 0.
  - bites: The pack's entire evidence that the Community Patch works is the line 'Community Patch applied, 4511 commands run, 0 failed'. That line would print identically if every single command silently did nothing — which is exactly the failure mode core.py:238-241 says it exists to catch. The count is of calls made, not effects landed.

- **[wrong_in_an_edge_case]** core.py:366-381, `_current_map` — `if not _logged_map_name: _logged_map_name = True; logging.info(f"Second Wind: the game calls this map {found}, and the patch {'names it too' if matching else 'has nothing for it'}")`
  - The flag is latched on the very first call. core.py:401-408 documents that at spawn time the game still calls the map 'loader'; `on_tick` starts sampling immediately after, so the first successful read is very likely 'loader'.
  - bites: The one diagnostic guarding 370-479 map-gated commands reports on the loader map, prints 'has nothing for it', and then never speaks again for the rest of the session. A genuine name mismatch on every real map would look exactly like a healthy launch.

- **[wrong_in_an_edge_case]** communitypatch.py:69 vs sdk_mods/settings/bl2_modern.json
  - `_extra_options = {name: _switch(name, short, False, what) for name, short, what in EXTRAS}` documents extras as off by default, but the live settings file has 8 of 11 true, including `"Less Dumb Visuals v3.2.0": true` — the 664-command visual overhaul patchfile.py:102-104 explicitly calls out as something the patch authors deliberately left off.
  - bites: The machine is running 4,990 patch commands where the documented default is 4,039 and the UCP itself ships 4,072. Nothing in the pack ever compares the settings file to the declared defaults, so a stray toggle in a menu whose rows are known to overlap (patchsections.py:64-67) is permanent and invisible.

- **[cosmetic]** communitypatch.py:87-93, `register(Feature(name="Community Patch", patch_sections=wanted_sections, options=[...]))`
  - No `patch_file` is given, so it defaults to core.py:80 `patch_file: str = "patch.txt"`. The Extras feature sets `patch_file="extras.txt"` and registers second (features/__init__.py:24-26), so on any collision extras wins.
  - bites: Not currently a defect — I measured 0 overlapping (object, property) pairs between the UCP's 4,039 default commands and the extras' 36. But it is undefended: adding a fifth extra that touches a UCP target would silently override the patch, with nothing logging the collision. The check is cheap and does not exist.
