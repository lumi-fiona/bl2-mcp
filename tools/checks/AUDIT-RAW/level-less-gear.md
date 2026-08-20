# Level-less gear

Source file: `D:/SteamLibrary/steamapps/common/Borderlands 2/sdk_mods/bl2_modern/features/levelless.py`

**Purpose.** Mark a gun once and it is silently rebuilt at your current level every time you level up, so you never have to re-farm it.

## Claims

### 1. mark(item) actually records the item's UniqueId in the persisted list (the thing that makes it follow you later)

- proven today: **no**
- evidence: regress.py:91-92 only asserts `uid not in L._ids()` AFTER `_forget(uid)`, which passes trivially even if `_remember` never added it. Nothing asserts the id is present after mark.
- reachable: bridge_only
- missing capability: (none)

**How to prove it:**

import unrealsdk; from bl2_modern.features import levelless as L
pc = unrealsdk.find_all('WillowPlayerController')[-1]
gun = list(pc.GetPawnInventoryManager().Backpack)[0]
uid = int(gun.DefinitionData.UniqueId)
L._forget(uid)
assert uid not in L._ids()
assert L.mark(gun) is True
assert uid in L._ids(), f'mark did not remember {uid}: {L._ids()}'
assert L.marked.value == sorted(L._ids())

### 2. After marking, the item's GameStage equals the player's ExpLevel

- proven today: **yes**
- evidence: D:/SteamLibrary/steamapps/common/Borderlands 2/bl2-mcp/tools/regress.py:87 — `same[0].GameStage == lvl`
- reachable: bridge_only
- missing capability: (none)

**How to prove it:**

Already covered: regress.py:78-87 seeds a weapon at `lvl-10`, calls `L.mark(gun)`, asserts `same[0].GameStage == lvl`.

### 3. The rebuild rescales real damage, not just the displayed level number

- proven today: **yes**
- evidence: D:/SteamLibrary/steamapps/common/Borderlands 2/bl2-mcp/tools/regress.py:88 — `same[0].InstantHitDamage > was_dmg`
- reachable: bridge_only
- missing capability: (none)

**How to prove it:**

Already covered by regress.py:83,88 (`was_dmg = gun.InstantHitDamage`; assert the rebuilt copy's InstantHitDamage is strictly greater).

### 4. Exactly one copy survives the rebuild - no duplicated gun

- proven today: **yes**
- evidence: D:/SteamLibrary/steamapps/common/Borderlands 2/bl2-mcp/tools/regress.py:89 — `len(same) == 1`
- reachable: bridge_only
- missing capability: (none)

**How to prove it:**

Already covered by regress.py:86,89.

### 5. Backpack item count is unchanged - the old copy really is removed

- proven today: **yes**
- evidence: D:/SteamLibrary/steamapps/common/Borderlands 2/bl2-mcp/tools/regress.py:90 — `len(g._backpack(pc)) == n_before`
- reachable: bridge_only
- missing capability: (none)

**How to prove it:**

Already covered by regress.py:84,90.

### 6. UniqueId survives the rebuild, so the marked gun stays 'the same gun'

- proven today: **yes**
- evidence: D:/SteamLibrary/steamapps/common/Borderlands 2/bl2-mcp/tools/regress.py:86 — the rebuilt copy is found by looking up the pre-mark uid, and 87-90 then pass on it.
- reachable: bridge_only
- missing capability: (none)

**How to prove it:**

Already covered by regress.py:82,86.

### 7. UniqueId is unique per item, so marking one gun cannot silently mark another

- proven today: **no**
- evidence: Nothing checks for collisions. `is_marked` (levelless.py:89-93) and `relevel_all` (levelless.py:186) match on this int alone.
- reachable: bridge_only
- missing capability: (none)

**How to prove it:**

import unrealsdk, collections
pc = unrealsdk.find_all('WillowPlayerController')[-1]
ids = [int(i.DefinitionData.UniqueId) for i in pc.GetPawnInventoryManager().Backpack]
dupes = [u for u, n in collections.Counter(ids).items() if n > 1]
print('zero-ids:', ids.count(0), 'dupes:', dupes)
assert 0 not in ids, 'items with UniqueId 0 exist - marking one marks all of them'
assert not dupes, f'colliding UniqueIds: {dupes}'

### 8. _forget removes the id, so a marked gun can be un-marked

- proven today: **yes**
- evidence: D:/SteamLibrary/steamapps/common/Borderlands 2/bl2-mcp/tools/regress.py:91-92
- reachable: bridge_only
- missing capability: (none)

**How to prove it:**

Already covered by regress.py:91-92.

### 9. When you LEVEL UP mid-play, marked gear is brought up with you (the on_tick path)

- proven today: **no**
- evidence: regress.py never touches ExpLevel and never calls `on_tick` or `relevel_all`. The only path it exercises is `mark()` -> `_relevel_one` (regress.py:85).
- reachable: bridge_only
- missing capability: (none)

**How to prove it:**

import unrealsdk; from bl2_modern.features import levelless as L
pc = unrealsdk.find_all('WillowPlayerController')[-1]
inv = pc.GetPawnInventoryManager()
gun = list(inv.Backpack)[0]
uid = int(gun.DefinitionData.UniqueId)
L.mark(gun)
lvl = int(pc.PlayerReplicationInfo.ExpLevel)
pc.PlayerReplicationInfo.ExpLevel = lvl + 1
L._ticks = 59            # next tick is the 60th, so the throttle lets it through
for _ in range(2):
    L.on_tick.__wrapped__(pc, None, None, None)
now = [i for i in inv.Backpack if int(i.DefinitionData.UniqueId) == uid]
assert now and int(now[0].GameStage) == lvl + 1, f'stayed at {now[0].GameStage if now else "gone"}'
pc.PlayerReplicationInfo.ExpLevel = lvl

### 10. The tick hook does the work once per level-up, not once per frame

- proven today: **no**
- evidence: No test. Guarded only by `_last_level` (levelless.py:218-220) and the `_ticks % 60` throttle (levelless.py:214).
- reachable: bridge_only
- missing capability: (none)

**How to prove it:**

import unrealsdk; from bl2_modern.features import levelless as L
pc = unrealsdk.find_all('WillowPlayerController')[-1]
calls = []
real = L.relevel_all
L.relevel_all = lambda p: (calls.append(1), real(p))[1]
L._last_level = 0
for _ in range(600):
    L.on_tick.__wrapped__(pc, None, None, None)
L.relevel_all = real
assert len(calls) == 1, f'relevel_all ran {len(calls)} times over 600 ticks at one level'

### 11. Marked gear catches up on load / after a map change (the SpawningProcessComplete path)

- proven today: **no**
- evidence: Nothing calls `on_character_live` (levelless.py:227-239). regress.py has no load step.
- reachable: bridge_only
- missing capability: (none)

**How to prove it:**

import unrealsdk; from bl2_modern.features import levelless as L
pc = unrealsdk.find_all('WillowPlayerController')[-1]
inv = pc.GetPawnInventoryManager()
gun = list(inv.Backpack)[0]
uid = int(gun.DefinitionData.UniqueId)
L.mark(gun)
item = [i for i in inv.Backpack if int(i.DefinitionData.UniqueId) == uid][0]
item.DefinitionData.GameStage = 5          # pretend it fell behind
L._last_level = 0
L.on_character_live.__wrapped__(pc, None, None, None)
now = [i for i in inv.Backpack if int(i.DefinitionData.UniqueId) == uid][0]
assert int(now.GameStage) == int(pc.PlayerReplicationInfo.ExpLevel)

### 12. The marked list is stored in that character's save file, not once for the machine

- proven today: **partly**
- evidence: Human-observed once: D:/SteamLibrary/steamapps/common/Borderlands 2/BL2-WAKE-UP.md:92-93 ("proven by marking a gun, saving, restarting, reloading and finding it still marked"). No automated check. The mechanism is real (save_options/hooks.py:99-119 writes registered_save_options into the save's UnloadableDlcLockoutList) but the mod's own wiring is not asserted anywhere.
- reachable: bridge_only
- missing capability: (none)

**How to prove it:**

import json
from save_options.registration import registered_save_options, registered_mods, load_callbacks
from bl2_modern.features import levelless as L
assert 'bl2_modern' in registered_save_options, registered_save_options.keys()
assert registered_save_options['bl2_modern'].get('Level-less items') is L.marked
assert 'bl2_modern' in load_callbacks
L.marked.value = [12345]
pc = __import__('unrealsdk').find_all('WillowPlayerController')[-1]
pc.SaveGame()
# then, with no restart, read it back out of the file the game just wrote
from save_options.options import can_save
print('can_save:', can_save())

### 13. Loading character B does not show character A's marked list

- proven today: **no**
- evidence: Nothing tests two characters. The reset path exists (save_options/hooks.py:125-132 sets every save option to default on LoadGame) but is untested against this option.
- reachable: bridge_only
- missing capability: (none)

**How to prove it:**

from bl2_modern.features import levelless as L
from save_options.options import set_option_to_default
L.marked.value = [111, 222]
set_option_to_default(L.marked)          # what the LoadGame hook does
assert L.marked.value == [], f'leaked between characters: {L.marked.value}'
assert L.marked.default_value == []      # and the default was not aliased/mutated

### 14. On load, the save file's list is populated BEFORE on_character_live tries to relevel from it

- proven today: **no**
- evidence: Two independent hooks with no ordering guarantee: save_options populates on `WillowSaveGameManager:EndLoadGame` POST (save_options/hooks.py:135-160) while levelless reads it on `WillowPlayerController:SpawningProcessComplete` (levelless.py:227). Nothing establishes which fires first.
- reachable: needs_input
- missing capability: Loading a character needs a keypress through game_load_character (bl2-mcp/server.py:180-208), which steals focus.

**How to prove it:**

Add a witness and load a character with a non-empty list:
from bl2_modern.features import levelless as L
import save_options.hooks as SH
order = []
_real = L.on_character_live.__wrapped__
L.on_character_live.__wrapped__ = lambda *a: (order.append(('spawn', list(L.marked.value))), _real(*a))[1]
# ... load the character ...
print(order)
assert order and order[0][1], 'SpawningProcessComplete saw an empty list - it ran before the save was read'

### 15. If the replacement copy never appears, the original item is untouched ('nothing was removed', levelless.py:157-160)

- proven today: **no**
- evidence: No test forces the add to fail. And the code writes `data.GameStage = level` / `data.ManufacturerGradeIndex = level` (levelless.py:131-132) BEFORE attempting the add, so 'untouched' is only true if DefinitionData is a copy - which the module's own docstring (levelless.py:12-14) implies it is not.
- reachable: bridge_only
- missing capability: (none)

**How to prove it:**

# 1. does a DefinitionData write land on the live item?
import unrealsdk
pc = unrealsdk.find_all('WillowPlayerController')[-1]
item = list(pc.GetPawnInventoryManager().Backpack)[0]
before = int(item.DefinitionData.GameStage)
item.DefinitionData.GameStage = before + 7
print('re-read:', int(item.DefinitionData.GameStage))
assert int(item.DefinitionData.GameStage) == before, 'DefinitionData writes mutate the live item'

# 2. force the add to fail and check the original survived intact
from bl2_modern.features import levelless as L
shield = next(i for i in pc.GetPawnInventoryManager().Backpack
              if getattr(i.DefinitionData, 'WeaponTypeDefinition', None) is None)
stage = int(shield.DefinitionData.GameStage)
orig = L._is_weapon
L._is_weapon = lambda _i: True      # wrong add call -> nothing gets added
ok = L._relevel_one(pc, shield, stage + 5)
L._is_weapon = orig
assert ok is False
assert int(shield.DefinitionData.GameStage) == stage, 'original was mutated despite the failed add'

### 16. Non-weapons (shields, grenades, class mods, relics) relevel too, via ClientAddItemToBackpack

- proven today: **no**
- evidence: regress.py:78 seeds only `('weapon', 4)`; the `_is_weapon` False branch at levelless.py:147 is never executed by any test.
- reachable: bridge_only
- missing capability: (none)

**How to prove it:**

import unrealsdk; from bl2_modern.features import levelless as L
from bl2_modern.features import grinder as g
pc = unrealsdk.find_all('WillowPlayerController')[-1]
inv = pc.GetPawnInventoryManager()
lvl = int(pc.PlayerReplicationInfo.ExpLevel)
for kind in ('shield', 'grenade', 'class mod', 'relic'):
    pool = unrealsdk.find_object('ItemPoolDefinition', g.POOLS[(kind, 3)])
    for m in g._spawn_from_pool(pc, pool, max(1, lvl - 10)):
        inv.AddBackpackInventory(m)
    item = [i for i in inv.Backpack if g._kind(i) == kind][-1]
    uid = int(item.DefinitionData.UniqueId)
    n = len(list(inv.Backpack))
    assert L.mark(item)
    same = [i for i in inv.Backpack if int(i.DefinitionData.UniqueId) == uid]
    assert len(same) == 1 and int(same[0].GameStage) == lvl, f'{kind} did not relevel'
    assert len(list(inv.Backpack)) == n, f'{kind} count changed'

### 17. A marked gun you are actually holding follows your level

- proven today: **no**
- evidence: relevel_all only iterates `pc.GetPawnInventoryManager().Backpack` (levelless.py:179). Equipped weapons live on InventoryChain/ItemChain, not Backpack - see SanitySaver's own enumeration at sdk_mods/SanitySaver/console.py:43-53, which walks ItemChain/InventoryChain separately from Backpack.
- reachable: bridge_only
- missing capability: (none)

**How to prove it:**

import unrealsdk; from bl2_modern.features import levelless as L
pc = unrealsdk.find_all('WillowPlayerController')[-1]
inv = pc.GetPawnInventoryManager()
held = inv.InventoryChain                      # the equipped weapon
uid = int(held.DefinitionData.UniqueId)
L._remember(uid)
lvl = int(pc.PlayerReplicationInfo.ExpLevel)
pc.PlayerReplicationInfo.ExpLevel = lvl + 1
moved = L.relevel_all(pc)
pc.PlayerReplicationInfo.ExpLevel = lvl
assert moved == 1, f'relevel_all moved {moved} items - it never looked at the equipped gun'

### 18. mark() returning True means the item is now level-less AND up to date (the grinder charges money on this return value)

- proven today: **no**
- evidence: mark returns True at levelless.py:107 regardless of what `_relevel_one` returned (levelless.py:106 discards it). grinder.py:396-399 charges first, then treats True as success.
- reachable: bridge_only
- missing capability: (none)

**How to prove it:**

from bl2_modern.features import levelless as L
import unrealsdk
pc = unrealsdk.find_all('WillowPlayerController')[-1]
shield = next(i for i in pc.GetPawnInventoryManager().Backpack
              if getattr(i.DefinitionData, 'WeaponTypeDefinition', None) is None)
orig = L._is_weapon
L._is_weapon = lambda _i: True          # guarantees _relevel_one fails
result = L.mark(shield)
L._is_weapon = orig
assert result is False, 'mark() said True after the rebuild failed - the grinder already took the money'

### 19. Only marked items are touched; unmarked gear in the same backpack is left alone

- proven today: **no**
- evidence: No test. `relevel_all` filters at levelless.py:186 but nothing asserts the negative.
- reachable: bridge_only
- missing capability: (none)

**How to prove it:**

import unrealsdk; from bl2_modern.features import levelless as L
pc = unrealsdk.find_all('WillowPlayerController')[-1]
inv = pc.GetPawnInventoryManager()
before = {int(i.DefinitionData.UniqueId): int(i.DefinitionData.GameStage) for i in inv.Backpack}
keep = list(before)[0]
L.marked.value = [keep]
L._last_level = 0
L.relevel_all(pc)
after = {int(i.DefinitionData.UniqueId): int(i.DefinitionData.GameStage) for i in inv.Backpack}
changed = [u for u in before if u in after and after[u] != before[u]]
assert changed == [keep], f'also moved: {[c for c in changed if c != keep]}'

### 20. If save_options is unavailable, only per-character memory is lost - the feature still works ('losing per-character memory beats losing the feature', levelless.py:56)

- proven today: **no**
- evidence: In the fallback, `marked` is a bare HiddenOption (levelless.py:57) and the Feature is registered with `options=[]` and `save_options=[]` (levelless.py:247), so nothing ever passes it to build_mod. `marked.mod` stays None, and HiddenOption.save() raises RuntimeError when mod is None (mods_base/options.py:285-292). The list becomes process-local and vanishes on quit.
- reachable: bridge_only
- missing capability: (none)

**How to prove it:**

from bl2_modern.features import levelless as L
assert L.PER_CHARACTER, 'fallback path is live'
# and to check the fallback itself is not a silent total loss:
from mods_base import HiddenOption
fake = HiddenOption('Level-less items', [])
try:
    fake.save()
    print('saved somewhere')
except RuntimeError as ex:
    raise AssertionError(f'fallback cannot persist at all: {ex!r}')

### 21. In co-op the feature acts on your own backpack only, never a partner's

- proven today: **no**
- evidence: Both hooks act on whatever controller `obj` they were handed (levelless.py:217 `_player_level(obj)`, levelless.py:222 `relevel_all(obj)`) with no `obj is get_pc()` check, while `_ids()` is the local player's list.
- reachable: needs_second_player
- missing capability: A second player in the session so a non-local WillowPlayerController exists to hand the hook.

**How to prove it:**

import unrealsdk; from bl2_modern.features import levelless as L
from mods_base import get_pc
pcs = list(unrealsdk.find_all('WillowPlayerController'))
print('controllers:', len(pcs), 'local:', get_pc())
# with a second player joined, call the hook body with the REMOTE controller:
other = [p for p in pcs if p is not get_pc()][0]
seen = []
L.relevel_all = lambda p: seen.append(p) or 0
L.on_tick.__wrapped__(other, None, None, None)
assert not seen, 'the hook acted on the other player\'s controller'

## Suspected bugs

- **[breaks_the_feature]** levelless.py:179 `items = list(pc.GetPawnInventoryManager().Backpack)`
  - relevel_all only ever scans the Backpack. An equipped weapon is on InventoryChain/ItemChain (cf. sdk_mods/SanitySaver/console.py:43-51, which walks those chains separately from Backpack), so it is never seen. The grinder can only mark backpack items too (grinder.py:425 -> grinder.py:131-133), so the intended flow is: mark it in the backpack, equip it, and from that moment it silently stops following your level.
  - bites: The headline promise - 'mark a gun and it follows your level for the rest of the run' - fails for exactly the gun you actually use. The one-off proof in BL2-WAKE-UP.md:101 was a mark on a backpack item, which is why nobody noticed.

- **[breaks_the_feature]** levelless.py:131-132 `data.GameStage = level` / `data.ManufacturerGradeIndex = level`, and the comment at levelless.py:157-158 ("The original is untouched, which is the whole point of checking")
  - The level is written into `item.DefinitionData` BEFORE the replacement is built. The module's own measurement (levelless.py:12-14, "setting a level 49 sniper's GameStage to 51 left its damage at exactly 1442.66") says that write lands on the live object. So when the add fails and the code returns at levelless.py:160, the original is NOT untouched - it now claims the new level while keeping the old damage.
  - bites: Worse than cosmetic: the next attempt short-circuits at levelless.py:129 (`if int(data.GameStage) == level: return False`), so the item is permanently stuck reading level 61 with level 43 damage and can never self-repair. Backpack full, or a shield hitting the weapon branch, is enough to trigger it.

- **[wrong_in_an_edge_case]** levelless.py:210-214
  - Wrong order: `if not _ids(): return` runs before `_ticks += 1; if _ticks % 60: return`. `_ids()` reads `marked.value`, which goes through SaveOption.__getattribute__ (save_options/options.py:157-170), which calls `can_save()` -> `get_pc()` + `pc.GetCachedSaveGame()` - a real unreal function call - on every single PlayerTick.
  - bites: At the 264 fps this machine runs (bridge.py:58-60 says so), that is ~264 unreal calls plus 264 set constructions per second, all of them thrown away 59 times out of 60. Swapping the two blocks makes it 4/second with identical behaviour.

- **[cosmetic]** levelless.py:42-58 and the docstring "a hidden one is not among them"
  - Factually wrong: save_options already ships `HiddenSaveOption` - see the extracted package, save_options/options.py:173-199, `class HiddenSaveOption[J: JSON](SaveOption, HiddenOption[J])`. The hand-rolled `_HiddenSaveOption` is the same mixin minus the one thing the shipped class adds: an overridden `save()` that calls `trigger_save()` instead of HiddenOption.save()'s `self.mod.save_settings()`.
  - bites: Sixteen lines of try/except/dataclass gymnastics replace a one-line import, and any future `marked.save()` would write the machine-wide mod settings file instead of the character save - the exact bug the whole per-character design exists to avoid.

- **[wrong_in_an_edge_case]** levelless.py:107 `return True` in mark(), against grinder.py:396-399
  - `mark()` returns True whenever the item had a readable UniqueId, discarding `_relevel_one`'s return value at levelless.py:106. The grinder charges the player at grinder.py:396 and then prints 'will follow your level from now on' on that True.
  - bites: A failed rebuild (full backpack, refused add) still takes the money and still reports success. The error only appears in the log at levelless.py:159, which nobody reads mid-game.

- **[wrong_in_an_edge_case]** levelless.py:89-93 / levelless.py:186 - matching items purely on `int(item.DefinitionData.UniqueId)`
  - Nothing establishes that UniqueId is unique, or non-zero, across a backpack. If any item carries UniqueId 0 (common for freshly constructed items) and gets marked, every other zero-id item matches too.
  - bites: relevel_all would rebuild and replace unrelated gear, and `is_marked` would put a star on items the player never chose. Silent, and it destroys-and-recreates real items.

- **[wrong_in_an_edge_case]** levelless.py:217 `_player_level(obj)` and levelless.py:222 `relevel_all(obj)`
  - Neither hook checks that `obj` is the local player controller. `core.py:392` has the same shape for its own tick hook.
  - bites: In co-op the host can receive PlayerTick/SpawningProcessComplete for a joining player's controller, at which point the local player's marked-id list is applied to a partner's inventory manager at the partner's level.

- **[wrong_in_an_edge_case]** levelless.py:247 `save_options=[marked] if PER_CHARACTER else []` with `options=[]` on both branches
  - On the fallback branch `marked` is never handed to build_mod or to register_save_options, so it has no associated mod and no persistence path at all.
  - bites: The comment at levelless.py:56 promises 'losing per-character memory beats losing the feature'; what actually happens is losing all memory - marks evaporate on quit and `marked.save()` would raise RuntimeError (mods_base/options.py:287-290).
