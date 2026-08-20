# Level scaling

Source file: `D:/SteamLibrary/steamapps/common/Borderlands 2/sdk_mods/bl2_modern/features/levelscaling.py`

**Purpose.** One slider that changes the per-level growth multiplier (ships at the game's 1.13) so endgame numbers stay small without changing relative difficulty.

## Claims

### 1. The named object exists and can be found at the main menu

- proven today: **no**
- evidence: No test. The only signal is the absence of the error at levelscaling.py:44, and _apply_current deliberately suppresses even that (levelscaling.py:58).
- reachable: bridge_only
- missing capability: (none)

**How to prove it:**

import unrealsdk
from bl2_modern.features import levelscaling as LS
r = unrealsdk.find_object('ConstantAttributeValueResolver', LS.TARGET)
print(r, repr(r.ConstantValue))
assert r is not None

### 2. 113 really is the game's shipped value (VANILLA_PERCENT, levelscaling.py:24)

- proven today: **no**
- evidence: Nobody has read the object's untouched ConstantValue. The number is asserted in the docstring at levelscaling.py:5 and hard-coded at levelscaling.py:24 with no measurement cited - unlike the rest of this codebase, which cites dates.
- reachable: bridge_only
- missing capability: (none)

**How to prove it:**

Launch with steal_focus=False and run this at the title screen, BEFORE FrontendGFxMovie:Start fires (the current unrealsdk.log shows the mod loading at 11:25:39 with no main-menu patch line ever logged, so this window is real):
import unrealsdk
from bl2_modern.features import levelscaling as LS
print(repr(unrealsdk.find_object('ConstantAttributeValueResolver', LS.TARGET).ConstantValue))
assert abs(unrealsdk.find_object('ConstantAttributeValueResolver', LS.TARGET).ConstantValue - 1.13) < 1e-6

### 3. Moving the slider writes percent/100 onto the object

- proven today: **no**
- evidence: No test anywhere. The write is at levelscaling.py:50 (apply path) and levelscaling.py:64-66 (on_change path).
- reachable: bridge_only
- missing capability: (none)

**How to prove it:**

import unrealsdk
from bl2_modern.features import levelscaling as LS
r = unrealsdk.find_object('ConstantAttributeValueResolver', LS.TARGET)
LS.percent.value = 105
assert abs(r.ConstantValue - 1.05) < 1e-5, r.ConstantValue
LS.percent.value = 113
assert abs(r.ConstantValue - 1.13) < 1e-5, r.ConstantValue

### 4. _on_change must use the handed value because the option has not updated yet (levelscaling.py:62)

- proven today: **partly**
- evidence: Verified by reading mods_base: ValueOption.__setattr__ calls on_change_anytime at mods_base/options.py:144-145 BEFORE `super().__setattr__(name, value)` at mods_base/options.py:155. Source-verified, never executed as a check.
- reachable: bridge_only
- missing capability: (none)

**How to prove it:**

from bl2_modern.features import levelscaling as LS
seen = []
LS.percent.on_change_anytime = lambda opt, new: seen.append((opt.value, new))
LS.percent.value = 120
assert seen == [(113, 120)], seen   # the option still reads the OLD value inside the callback

### 5. on_change_anytime is used, not the deprecated on_change, and assigning it after construction actually takes effect (levelscaling.py:71-73)

- proven today: **no**
- evidence: Not asserted. Note the current log DOES carry two `DeprecationWarning: The on_change arg is deprecated` lines at 11:25:39.098-.099 from `<string>:14` and `:16` - so something in this pack still uses the deprecated form, and nothing identifies which.
- reachable: bridge_only
- missing capability: (none)

**How to prove it:**

from bl2_modern.features import levelscaling as LS
assert LS.percent.on_change_anytime is LS._on_change
fired = []
LS.percent.on_change_anytime = lambda o, n: fired.append(n)
LS.percent.value = 118
assert fired == [118]

### 6. The apply path is idempotent - a re-apply at the same percent writes nothing and logs nothing (levelscaling.py:48-49)

- proven today: **no**
- evidence: Never tested, and almost certainly false: ConstantValue is a UE3 FloatProperty (32-bit) while `percent.value / 100` is a Python double, so `resolver.ConstantValue == wanted` compares 1.1299999952316284 against 1.13.
- reachable: bridge_only
- missing capability: (none)

**How to prove it:**

import unrealsdk
from bl2_modern.features import levelscaling as LS
r = unrealsdk.find_object('ConstantAttributeValueResolver', LS.TARGET)
r.ConstantValue = 1.13
print(repr(r.ConstantValue), r.ConstantValue == 1.13)
assert r.ConstantValue == 113 / 100, 'float32 round-trip breaks the equality guard at levelscaling.py:48'

### 7. The change survives a level load ('the change is re-applied on every level load anyway', levelscaling.py:57)

- proven today: **no**
- evidence: There is no level-load hook in this file. Its only re-application paths are core.on_main_menu (core.py:457-466, guarded once per process by core.py:213/440-441) and core.apply_all, which only runs because bl2_modern/__init__.py:39 passes it as save_options' on_load - which itself only happens if some OTHER feature registered a save option (levelless.py:247 or difficulty.py:475).
- reachable: needs_map_travel
- missing capability: Reaching a second map, which needs a loaded character and movement (game_load_character steals focus).

**How to prove it:**

import unrealsdk
from bl2_modern.features import levelscaling as LS
LS.percent.value = 105
r = unrealsdk.find_object('ConstantAttributeValueResolver', LS.TARGET)
print('before travel:', repr(r.ConstantValue))
# travel to another map, then:
r2 = unrealsdk.find_object('ConstantAttributeValueResolver', LS.TARGET)
assert abs(r2.ConstantValue - 1.05) < 1e-5, f'reset to {r2.ConstantValue} after the map load'

### 8. It affects gear numbers - a weapon spawned at the same GameStage really does come out smaller

- proven today: **no**
- evidence: Never measured. The docstring at levelscaling.py:5-7 asserts it.
- reachable: bridge_only
- missing capability: (none)

**How to prove it:**

import unrealsdk
from bl2_modern.features import levelscaling as LS
from bl2_modern.features import grinder as g
pc = unrealsdk.find_all('WillowPlayerController')[-1]
pool = unrealsdk.find_object('ItemPoolDefinition', g.POOLS[('weapon', 3)])
r = unrealsdk.find_object('ConstantAttributeValueResolver', LS.TARGET)
r.ConstantValue = 1.13
hi = [m.InstantHitDamage for m in g._spawn_from_pool(pc, pool, 50)]
r.ConstantValue = 1.05
lo = [m.InstantHitDamage for m in g._spawn_from_pool(pc, pool, 50)]
print(hi, lo)
assert min(lo) < min(hi), 'the constant did not move weapon damage at a fixed GameStage'

### 9. It affects enemies the same way, so relative difficulty is unchanged (levelscaling.py:6-7)

- proven today: **no**
- evidence: Never measured, on either side. This is the load-bearing claim of the whole feature and no number exists for it.
- reachable: needs_map_travel
- missing capability: Enemies must respawn after the constant changes, which needs a map round trip.

**How to prove it:**

import unrealsdk
from bl2_modern.features import levelscaling as LS
r = unrealsdk.find_object('ConstantAttributeValueResolver', LS.TARGET)
r.ConstantValue = 1.13
a = [(str(p.Name), p.GetGameStage(), p.GetMaxHealth()) for p in unrealsdk.find_all('WillowAIPawn')][:5]
r.ConstantValue = 1.05
# travel out and back so enemies respawn, then:
b = [(str(p.Name), p.GetGameStage(), p.GetMaxHealth()) for p in unrealsdk.find_all('WillowAIPawn')][:5]
print(a); print(b)
# then compare the enemy-health ratio against the weapon-damage ratio from the previous check
assert abs((b[0][2]/a[0][2]) - (lo_dmg/hi_dmg)) < 0.05, 'enemies and gear did not move together'

### 10. Already-spawned things keep their old numbers ('takes effect on things that spawn afterwards', levelscaling.py:34)

- proven today: **no**
- evidence: Never checked.
- reachable: bridge_only
- missing capability: (none)

**How to prove it:**

import unrealsdk
from bl2_modern.features import levelscaling as LS
pawn = next(p for p in unrealsdk.find_all('WillowAIPawn') if p.Health > 0)
hp = pawn.GetMaxHealth()
unrealsdk.find_object('ConstantAttributeValueResolver', LS.TARGET).ConstantValue = 1.02
assert pawn.GetMaxHealth() == hp, f'a live enemy changed from {hp} to {pawn.GetMaxHealth()}'

### 11. Installing the pack changes nothing until you move the slider (levelscaling.py:11)

- proven today: **no**
- evidence: Untested, and it depends on the unverified VANILLA_PERCENT claim above plus the float32 round-trip: at 113 the code still performs a write (since the equality guard at levelscaling.py:48 never fires).
- reachable: bridge_only
- missing capability: (none)

**How to prove it:**

Combine two reads: (a) the pre-apply value at the title screen (see the VANILLA_PERCENT check), (b) the post-apply value at the main menu.
import unrealsdk
from bl2_modern.features import levelscaling as LS
before = unrealsdk.find_object('ConstantAttributeValueResolver', LS.TARGET).ConstantValue
LS._apply()
after = unrealsdk.find_object('ConstantAttributeValueResolver', LS.TARGET).ConstantValue
assert before == after, f'applying at the default changed {before} -> {after}'

### 12. If apple1417's Scaling Adjuster is also loaded, whichever wrote last wins and neither breaks (levelscaling.py:8-9)

- proven today: **no**
- evidence: Scaling Adjuster is not installed - it does not appear in the sdk_mods listing. The claim is untestable here as written.
- reachable: bridge_only
- missing capability: The Scaling Adjuster mod would have to be installed.

**How to prove it:**

from mods_base import mod_list
names = sorted(m.name for m in mod_list.mod_list)
print(names)
assert 'Scaling Adjuster' in names, 'not installed - the compatibility claim cannot be checked at all'

## Suspected bugs

- **[cosmetic]** levelscaling.py:48 `if resolver.ConstantValue == wanted: return`
  - Exact float equality between a UE3 32-bit FloatProperty read back as a Python double and `percent.value / 100`. For 113 that is 1.1299999952316284 == 1.13, which is False.
  - bites: The guard never fires, so every apply re-writes the value and logs 'levelscaling: per-level growth set to 113%' (levelscaling.py:51) - including on every character load through core.apply_all. Harmless numerically, but it makes the log line meaningless as a signal that anything changed, which is the one thing this codebase relies on logs for.

- **[wrong_in_an_edge_case]** levelscaling.py:54-58 `_apply_current` docstring: "the change is re-applied on every level load anyway"
  - There is no level-load hook in this feature. The only re-application after the once-per-process main menu (core.py:440-441 sets `_main_menu_done` and never clears it) is `core.apply_all`, and that only ever runs because bl2_modern/__init__.py:36-39 wires it as save_options' on_load - which is skipped entirely when `_saved` is empty.
  - bites: If levelless and difficulty both fail to build their save options (save_options missing, levelless.py:56 / difficulty.py:33 fallbacks), `register_save_options` is never called, `apply_all` never runs, and this feature silently loses its only re-application path - while the docstring still tells the next reader it is covered.

- **[wrong_in_an_edge_case]** levelscaling.py:67-68 `except Exception: pass`
  - The on_change path swallows everything with no log at all. The comment says 'the menu and level hooks catch it later', but per the bug above the main-menu hook is already spent by the time a user can touch the slider (core.py:440-441).
  - bites: Move the slider while the object is not loaded and nothing happens, nothing is logged, and the value is not re-applied until the next character load. The user sees a slider that did nothing and has no way to tell.

- **[wrong_in_an_edge_case]** core.py:463-466, which applies to this feature
  - If `_apply_current` ever raises at the main menu, core sets `feature.failed` - and `apply_all` skips any feature with `failed is not None` (core.py:189).
  - bites: One transient main-menu failure permanently removes this feature's only backstop for the rest of the process, with the mod menu still showing the slider as live.
