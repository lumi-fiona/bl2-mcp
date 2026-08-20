# Extras

Source file: `D:/SteamLibrary/steamapps/common/Borderlands 2/sdk_mods/bl2_modern/features/extras.py`

**Purpose.** Bundles four small community text mods (Text Fixes, DLC scaling fix, free respec, cheaper dying) as switches through the same patch machinery, plus a three-line reimplementation of 'hide undiscovered missions'.

## Claims

### 1. Every switch in this menu points at a section that really exists in data/extras.txt.

- proven today: **partly**
- evidence: verified by hand 2026-08-19; no automated check exists (patchsections.py's missing-name assert covers patch.txt only)
- reachable: filesystem_only
- missing capability: (none)

**How to prove it:**

True today, unproven by any check. I verified by hand: `sections_in(extras.txt)` == {'Text Fixes': 31, 'DLC scaling fix': 3, 'Free respec': 1, 'Cheaper dying': 1} and every SOURCES section name is present. Make it a check: `from bl2_modern.patchfile import sections_in; from bl2_modern.build_extras import SOURCES; import pathlib; found = sections_in(pathlib.Path(r'D:/.../data/extras.txt').read_text(encoding='utf-8')); missing = [s for _f, s, _w in SOURCES if s not in found]; assert not missing, missing` — this is the exact assert patchsections.py:136-137 already makes for the Community Patch and that extras.txt does not have.

### 2. Sharing the SOURCES list with build_extras.py makes an invisible switch impossible (extras.py:8-11).

- proven today: **no**
- evidence: (none)
- reachable: filesystem_only
- missing capability: (none)

**How to prove it:**

This claim is false as written and the proof is build_extras.py:68-70: `if not path.is_file(): print(f"  MISSING {filename} - section {section!r} will not exist"); continue`. The switch is built from SOURCES, the section is built from the file — a missing download at build time yields exactly the invisible switch the docstring says cannot happen. Reproduce offline: `python build_extras.py <empty folder>` then assert the round-trip check at build_extras.py:114-116 does NOT fire (counts is empty, so the loop has nothing to assert) and that SOURCES still has 4 entries while sections_in(extras.txt) has 0.

### 3. The 36 extras commands land on live objects.

- proven today: **no**
- evidence: (none)
- reachable: bridge_only
- missing capability: (none)

**How to prove it:**

Same sentinel sandwich as the Community Patch, but small enough to run whole:
```
import unrealsdk, pathlib
from bl2_modern.patchfile import commands_from
from bl2_modern.features.extras import wanted_sections
pc = unrealsdk.find_all('WillowPlayerController')[-1]
t = pathlib.Path(r'D:/.../data/extras.txt').read_text(encoding='utf-8')
c, h, _ = commands_from(t, wanted_sections())
for cmd in c + [x[1] for x in h if x[0] in ('None','')]:
    _, path, prop, want = cmd.split(None, 3)
    o = unrealsdk.find_object('Object', path)
    print(path, prop, repr(str(getattr(o, prop.split('[')[0])))[:80], '||', want[:60])
```
assert every object resolves and every property already reads back the patched value (the patch ran at the menu). 32 of the 36 must pass; the 4 map-gated ones (Ice_P x3, SouthernShelf_P x1) are expected to fail unless you are in those maps.

### 4. Text Fixes' 4 map-gated commands (Ice_P x3, SouthernShelf_P x1) eventually run.

- proven today: **no**
- evidence: (none)
- reachable: needs_map_travel
- missing capability: a save inside Ice_P (Three Horns Valley area) so game_load_character lands there without walking

**How to prove it:**

`from bl2_modern import core; assert 'ice_p' in core._by_level and len(core._by_level['ice_p']) == 3` proves they were held. Proving they RUN needs standing in Ice_P: after arriving, `assert core._map_done == 'ice_p'` and then resolve each of the 3 targets and assert the property equals the patched value.

### 5. 'Free respec' makes respeccing cost nothing.

- proven today: **no**
- evidence: (none)
- reachable: bridge_only
- missing capability: (none)

**How to prove it:**

Only 1 command, so read the target directly. `c, _, _ = commands_from(extras_text, {'Free respec'}); print(c)` gives the object+property; then `o = unrealsdk.find_object('Object', path); assert float(getattr(o, prop)) == 0.0`. The play-level claim (the respec screen shows $0) additionally needs a screen.

### 6. 'Cheaper dying' costs 1% of your money instead of 7%.

- proven today: **no**
- evidence: (none)
- reachable: bridge_only
- missing capability: (none)

**How to prove it:**

Object-state half: resolve the single command's target and assert the property is 0.01. Behaviour half is stronger and reachable: `m0 = pc.PlayerReplicationInfo.GetCurrencyOnHand(0)` (or the AddCurrencyOnHand/read pair regress.py:7 uses), kill the pawn via `pc.Pawn.Died(None, None, pc.Pawn.Location)` or `pc.CausePlayerDeath()`, wait for the New-U, then assert `(m0 - m1) / m0` is within 0.002 of 0.01.

### 7. 'Hide undiscovered missions' sets bShowUndiscoveredMissions on whichever controller actually exists — 'three lines and always right' (extras.py:17-19).

- proven today: **no**
- evidence: (none)
- reachable: bridge_only
- missing capability: (none)

**How to prove it:**

`import unrealsdk; from bl2_modern.features import extras as E; pcs = list(unrealsdk.find_all('WillowPlayerController')); assert pcs; assert all(bool(p.bShowUndiscoveredMissions) == (not E.hide_missions.value) for p in pcs)`. Run once after a level load. Note this asserts the value, not the visual effect.

### 8. 'Takes effect immediately' (extras.py:43).

- proven today: **no**
- evidence: (none)
- reachable: bridge_only
- missing capability: (none)

**How to prove it:**

It does not, and one line falsifies it: `import unrealsdk; from bl2_modern.features import extras as E; pc = unrealsdk.find_all('WillowPlayerController')[-1]; before = bool(pc.bShowUndiscoveredMissions); E.hide_missions.value = not E.hide_missions.value; assert bool(pc.bShowUndiscoveredMissions) != before, 'the option text says immediately but nothing writes the property until the next SpawningProcessComplete'`. This assert will FAIL today — that is the point.

### 9. The mission log visibly lists only picked-up quests.

- proven today: **no**
- evidence: (none)
- reachable: needs_screenshot
- missing capability: screen capture of the mission log, or a verified read of the tracker list

**How to prove it:**

Not reachable by property read alone — the property is the mechanism, the log contents are the promise. Semi-reachable: read the mission tracker's own list, e.g. `mp = pc.GetWillowPlayerPawn()` / `pc.MissionPlaythroughs[pc.GetCurrentPlaythrough()].MissionList` and assert every entry has Status != MS_NotStarted. Confirm the field name with `game_function('WillowPlayerController', 'GetMissionStatus')` before trusting it.

### 10. Setting the property on a co-op partner's controller is harmless / correct.

- proven today: **no**
- evidence: (none)
- reachable: needs_second_player
- missing capability: a second connected client

**How to prove it:**

With two players connected: `pcs = list(unrealsdk.find_all('WillowPlayerController'))`; assert len(pcs) >= 2 and that the local one (`unrealsdk.find_all('WillowPlayerController')[-1]` per the convention regress.py:4 uses) has the intended value and that setting it on the remote one did not raise and did not change the remote player's HUD.

### 11. A switch turned off means its section's commands are not sent.

- proven today: **no**
- evidence: (none)
- reachable: filesystem_only
- missing capability: (none)

**How to prove it:**

`from bl2_modern.features import extras as E; from bl2_modern.patchfile import commands_from; E._switches['Text Fixes'].value = False; c, h, _ = commands_from(text, E.wanted_sections()); assert len(c) + len(h) == 5` (36 total minus Text Fixes' 31).

## Suspected bugs

- **[breaks_the_feature]** extras.py:38-45 — `hide_missions = BoolOption("Hide undiscovered missions", True, description=("... Takes effect immediately."))`
  - The description promises immediate effect, but the only writer is the `SpawningProcessComplete` hook at extras.py:53-64. There is no `on_change_anytime` on this option (contrast difficulty.py:431 and difficulty.py:461-464, which the same author wired up precisely because callbacks are needed for live changes).
  - bites: A player toggles it in the mod menu mid-game, sees no change, toggles it back, and concludes the feature is broken. The fix is one line: `hide_missions.on_change_anytime = lambda _o, v: setattr(get_pc(), 'bShowUndiscoveredMissions', not v)`.

- **[wrong_in_an_edge_case]** extras.py:8-11 docstring — "a switch pointing at a section name that does not exist is invisible ... Sharing the list makes that impossible."
  - Sharing SOURCES does not make it impossible. build_extras.py:68-70 skips a missing source file with a printed warning and still leaves the switch in the menu, and the round-trip assert at build_extras.py:114-116 iterates `counts`, which simply has no entry for the skipped section — so it cannot fire.
  - bites: The Community Patch has a runtime guard for exactly this (patchsections.py:136-137, `assert not missing`). The extras file has none. A rebuild done in the wrong folder ships a menu with switches that tick and do nothing, and nothing anywhere notices.

- **[wrong_in_an_edge_case]** extras.py:61-64 — `try: obj.bShowUndiscoveredMissions = not hide_missions.value  except Exception as ex: logging.error(...)`
  - The except only catches a raise. If the write succeeds on a controller that is not the one driving the local HUD (a replicated proxy, or a co-op client's controller arriving on the host), nothing raises and nothing is logged.
  - bites: Silent no-op with a clean log — the same failure shape core.py:238-241 was written to defend against. A read-back assert after the write (`if bool(obj.bShowUndiscoveredMissions) == hide_missions.value: logging.error(...)`) costs one line and turns it loud.

- **[cosmetic]** extras.py:29-36 — `_switches = {section: BoolOption(section, True, ...) for _file, section, what in SOURCES}`
  - All four extras default ON, including 'Text Fixes' (31 commands) and 'DLC scaling fix' (3 commands, 2 of them map-gated to Ice_P/SouthernShelf_P — actually those 4 map-gated commands belong to Text Fixes, measured today). There is no master switch (extras.py:49 says so explicitly) and no equivalent of the Community Patch's `enabled` kill switch.
  - bites: Not wrong by itself, but it means the only way to A/B the pack against vanilla for a text-related bug is to untick four separate switches, and unlike the Community Patch there is no single 'is this pack's extras responsible?' toggle. Worth one BoolOption if debugging a report ever needs it.
