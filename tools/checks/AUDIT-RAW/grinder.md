# Grinder

Source file: `D:/SteamLibrary/steamapps/common/Borderlands 2/sdk_mods/bl2_modern/features/grinder.py`

**Purpose.** Turns the Sanctuary Golden Chest (and the H key) into a five-option menu that trades several backpack items for one better/new one, marks an item level-less, opens the vanilla chest, or dumps a diagnostic report — charging money for each.

## Claims

### 1. Opening the grinder shows exactly five choices: Perfect / Grind / Level-less / Open normally / Report.

- proven today: **no**
- evidence: (none)
- reachable: bridge_only
- missing capability: (none)

**How to prove it:**

Paste into bl2-mcp/tools/ask.sh. This FakeBox harness is referenced by every later menu check:
```python
import unrealsdk
from bl2_modern.features import grinder as g
captured = []
class FakeBox:
    def __init__(self, **kw): self.kw = kw; captured.append(self)
    def show(self, button=None): pass
pc = unrealsdk.find_all('WillowPlayerController')[-1]
real, g.OptionBox = g.OptionBox, FakeBox
try:
    g._open_menu(pc)
    names = [b.name for b in captured[-1].kw['buttons']]
    assert names == ['Perfect an item', 'Grind for something better',
                     'Make an item level-less', 'Open the chest normally',
                     'Report what the grinder sees'], names
finally:
    g.OptionBox = real
```
OptionBox is a module-level import at grinder.py:40, so replacing `g.OptionBox` makes every dialog path headless-testable.

### 2. Each of the five buttons routes to its own action and no other (the `chosen` dispatch at grinder.py:221-231).

- proven today: **no**
- evidence: (none)
- reachable: bridge_only
- missing capability: (none)

**How to prove it:**

With the FakeBox harness in place, drive each button and record which internal function ran:
```python
fired = []
for name, attr in (('_choose_items','_choose_items'), ('_report','_report'),
                   ('_open_chest_normally','_open_chest_normally')):
    orig = getattr(g, attr)
    setattr(g, attr, (lambda n, o: (lambda *a, **k: (fired.append((n,)+a[1:]), o(*a, **k))[1]))(name, orig))
box = captured[-1]
for b in box.kw['buttons']:
    fired.clear(); box.kw['on_select'](box, b)
    print(b.name, '->', fired)
assert fired  # every button must reach exactly one handler
```
Expect `Perfect an item -> _choose_items('perfect')`, `Grind... -> _choose_items('grind')`, `Make an item level-less -> _choose_items('levelless')`, `Open the chest normally -> _open_chest_normally`, `Report... -> _report`. Note grinder.py:230-231 uses a bare `else:` for grind, so any button that fails identity comparison silently grinds.

### 3. `_busy` is cleared on every way out of the menu, so the chest hooks are never permanently locked out.

- proven today: **no**
- evidence: (none)
- reachable: bridge_only
- missing capability: (none)

**How to prove it:**

```python
g._busy = False
g._open_menu(pc); assert g._busy is True
captured[-1].kw['on_cancel'](captured[-1]); assert g._busy is False
g._open_menu(pc)
captured[-1].kw['on_select'](captured[-1], captured[-1].kw['buttons'][2])
assert g._busy is False
```
Also check the raising path: monkeypatch FakeBox.show to raise and assert `g._busy is False` afterwards (grinder.py:246-250).

### 4. The H keybind respects the 'Enable the grinder' switch.

- proven today: **no**
- evidence: (none)
- reachable: bridge_only
- missing capability: (none)

**How to prove it:**

```python
g.enabled.value = False
captured.clear(); g._open_grinder()
assert captured == [], 'H still opens the grinder with the feature switched off'
g.enabled.value = True
```
This FAILS today: `_open_grinder` at grinder.py:1228-1233 calls `_open_menu` with no `enabled.value` check, unlike `_try_take_over` at grinder.py:1069.

### 5. All four chest hooks actually bind at apply time.

- proven today: **partly**
- evidence: grinder.py:1181 logs 'attached to the {name}' per hook, but nothing asserts it; regress.py never touches any hook.
- reachable: bridge_only
- missing capability: (none)

**How to prove it:**

```python
for h in (g.on_used_definition, g.on_used_object,
          g.on_golden_key_prompt, g.on_cannot_afford):
    assert h.get_active_count() == len(h.hook_funcs), h.hook_identifier
```
`get_active_count` is real: mods_base/hook.py:59-72.

### 6. Walking up to the real Golden Chest with zero keys opens the grinder (i.e. `OnUserCouldNotAfford` really fires for that object).

- proven today: **partly**
- evidence: Human observation only, recorded as prose in grinder.py:1195-1199 and BL2-LOOT-POOLS.md:110-115. No file, no assert.
- reachable: needs_map_travel
- missing capability: A way to fire the chest's Use from code — e.g. calling `chest_actor.UsedBy(pc.Pawn)` through the bridge and confirming pyunrealsdk hooks fire on Python-initiated UFunction calls. That is a 5-minute probe nobody has run.

**How to prove it:**

Two halves. The takeover logic is bridge-testable:
```python
captured.clear(); g._skip_once = False; g._busy = False
g.on_cannot_afford(unrealsdk.find_object('InteractiveObjectDefinition',
    'GD_Balance_Treasure.InteractiveObjects.InteractiveObj_TreasureChest_Golden'), None, None, None)
assert len(captured) == 1 and captured[-1].kw['title'] == 'Grinder'
```
The half that needs a body in Sanctuary: stand at the chest, press Use, then `assert 'took over InteractiveObj_TreasureChest_Golden via could not afford' in open(LOG).read()`.

### 7. Using anything that is NOT the Golden Chest never opens the grinder.

- proven today: **no**
- evidence: (none)
- reachable: bridge_only
- missing capability: (none)

**How to prove it:**

```python
captured.clear(); g._busy = False
for n in ('InteractiveObj_Ammo_Machine', 'InteractiveObj_Vending_Machine',
          'InteractiveObj_TreasureChest_Red', 'Door_Sanctuary', 'ObjectGrade_TreasureChest_Golden'):
    g._try_take_over(pc, 'definition', n, None)
assert captured == [], [c.kw['title'] for c in captured]
```
Note `ObjectGrade_TreasureChest_Golden` is in the list on purpose: grinder.py:1064/1069 use a substring test, so any object whose name merely CONTAINS 'TreasureChest_Golden' takes over.

### 8. The grinder blocks nothing — the chest's own bookkeeping always runs (the fix for the stuck 'CAN'T AFFORD').

- proven today: **partly**
- evidence: grinder.py:1206-1216 documents the fix in prose. No assert anywhere; regress.py never calls a hook.
- reachable: bridge_only
- missing capability: (none)

**How to prove it:**

```python
golden = 'InteractiveObj_TreasureChest_Golden'
for where in ('definition', 'object', 'could not afford'):
    assert g._try_take_over(pc, where, golden, None) is None
assert g.on_cannot_afford(chest_def, None, None, None) is None
assert g.on_golden_key_prompt(pc, None, None, None) is None
```
Every one must be `None`, never `Block`.

### 9. 'Open the chest normally' lets the very next chest use through untouched.

- proven today: **no**
- evidence: (none)
- reachable: bridge_only
- missing capability: (none)

**How to prove it:**

```python
captured.clear(); g._busy = False
g._open_chest_normally(pc); assert g._skip_once is True
golden = 'InteractiveObj_TreasureChest_Golden'
g._try_take_over(pc, 'definition', golden, None)   # hook 1 of the same press
g._try_take_over(pc, 'could not afford', golden, None)  # hook 2 of the SAME press
assert captured == [], 'the second hook of one chest press opened the grinder anyway'
```
This FAILS today: hook 1 consumes `_skip_once` at grinder.py:1071-1073, hook 2 then finds it False and opens the menu.

### 10. The grinder never costs a Golden Key.

- proven today: **no**
- evidence: (none)
- reachable: bridge_only
- missing capability: (none)

**How to prove it:**

```python
keys = lambda: pc.PlayerReplicationInfo.GetGoldenKeyCount()  # confirm the field name with game_object first
b = keys(); g._open_menu(pc)
captured[-1].kw['on_select'](captured[-1], captured[-1].kw['buttons'][1])
assert keys() == b
```
Cheap and completely uncovered today.

### 11. Grind, backpack path: N items in, exactly one out, backpack net -(N-1).

- proven today: **yes**
- evidence: regress.py:26-28 — `g._grind(pc, feed)` then `assert ai - bi == -2` with how_many=3.
- reachable: bridge_only
- missing capability: (none)

**How to prove it:**

Already covered by regress.py:28. Tighten it to name the survivor:
```python
before = {str(i) for i in g._backpack(pc)}
g._grind(pc, feed)
new = [i for i in g._backpack(pc) if str(i) not in before]
assert len(new) == 1, len(new)
```

### 12. Grinding charges exactly `sum(item levels) * cost_per_level`, not merely 'some money'.

- proven today: **partly**
- evidence: regress.py:30 asserts only `am < bm` — any charge at all passes, including a wrong one.
- reachable: bridge_only
- missing capability: (none)

**How to prove it:**

```python
want = g._cost(feed); bm = g._money(pc)
g._grind(pc, feed)
assert bm - g._money(pc) == want, (bm - g._money(pc), want)
```

### 13. What comes out of a grind is the same KIND as what went in (three class mods can never return a shotgun).

- proven today: **no**
- evidence: (none)
- reachable: bridge_only
- missing capability: (none)

**How to prove it:**

```python
before = {str(i) for i in g._backpack(pc)}
g._grind(pc, feed)
out = [i for i in g._backpack(pc) if str(i) not in before][0]
assert g._kind(out) == g._kind(feed[0]), (g._kind(out), g._kind(feed[0]))
```
Run it once per family: weapon, shield, grenade, classmod, relic.

### 14. What comes out of a grind is the same RARITY as what went in — the feature's headline promise, 'throw in three legendaries and get another legendary'.

- proven today: **no**
- evidence: (none)
- reachable: bridge_only
- missing capability: (none)

**How to prove it:**

```python
for (kind, rar) in list(g.POOLS):
    pool = unrealsdk.find_object('ItemPoolDefinition', g.POOLS[(kind, rar)])
    got = [g._rarity(m) for _ in range(6) for m in g._spawn_from_pool(pc, pool, 40)]
    assert got and set(got) == {rar}, (kind, rar, got)
```
This is the exact roll-six-times sweep BL2-LOOT-POOLS.md:1-6 says was done once by hand and never turned into a check. It will FAIL for `('relic', 4)`: BL2-LOOT-POOLS.md:58 records that `Pool_Artifacts_04_VeryRare` produces rarity 3, while grinder.py:766 maps rarity 4 to it.

### 15. The item out is at the level of the highest item in (grinder.py:920 `stage = max(_level(i) for i in items)`).

- proven today: **no**
- evidence: (none)
- reachable: bridge_only
- missing capability: (none)

**How to prove it:**

```python
g.loot_on_ground.value = False
want = max(g._level(i) for i in feed)
before = {str(i) for i in g._backpack(pc)}
g._grind(pc, feed)
out = [i for i in g._backpack(pc) if str(i) not in before][0]
assert g._level(out) == want, (g._level(out), want)
```
Then repeat with `loot_on_ground.value = True` — `stage` is computed at grinder.py:920 but never reaches `_drop_loot` (grinder.py:820-847 takes no stage argument), so the ground path's level is whatever the behaviour picks and has never been looked at.

### 16. Grind, ground path: all N inputs are consumed.

- proven today: **yes**
- evidence: regress.py:34-37 — `assert len(g._backpack(pc)) - bi == -3`.
- reachable: bridge_only
- missing capability: (none)

**How to prove it:**

Covered by regress.py:37.

### 17. Grind, ground path: loot appears in the world.

- proven today: **partly**
- evidence: regress.py:38 — `assert pk() > bp_`, a global WillowPickup count. It cannot tell the grinder's drop from a pickup any other actor made in the same frame, and it never checks what dropped.
- reachable: bridge_only
- missing capability: (none)

**How to prove it:**

```python
before = {str(p) for p in unrealsdk.find_all('WillowPickup')}
g._grind(pc, feed)
new = [p for p in unrealsdk.find_all('WillowPickup') if str(p) not in before]
assert len(new) == 1, len(new)
assert g._rarity(new[0].Inventory) == g._rarity(feed[0])
```
Confirm the pickup's inventory field name with `game_object` on one WillowPickup first — `Inventory` is my reading, not a measurement.

### 18. A mixed-rarity feed is refused and NOTHING is taken — no items and no money.

- proven today: **partly**
- evidence: regress.py:45-47 checks the backpack count only. Money is never read on any refusal path.
- reachable: bridge_only
- missing capability: (none)

**How to prove it:**

```python
bi, bm = len(g._backpack(pc)), g._money(pc)
g._grind(pc, mixed)
assert len(g._backpack(pc)) == bi and g._money(pc) == bm
```

### 19. A mixed-KIND feed (a gun and a shield of the same rarity) is refused.

- proven today: **no**
- evidence: regress.py:42-47 mixes rarity only; the `len(kinds) != 1` branch at grinder.py:897 has never run.
- reachable: bridge_only
- missing capability: (none)

**How to prove it:**

```python
mix = [next(i for i in g._backpack(pc) if g._kind(i)=='weapon'),
       next(i for i in g._backpack(pc) if g._kind(i)=='shield'),
       next(i for i in g._backpack(pc) if g._kind(i)=='grenade')]
bi, bm = len(g._backpack(pc)), g._money(pc)
g._grind(pc, mix)
assert len(g._backpack(pc)) == bi and g._money(pc) == bm
```

### 20. Being unable to pay refuses the grind and takes nothing — on BOTH the backpack path and the ground path.

- proven today: **partly**
- evidence: regress.py:50-56 sets money to 0 and checks the backpack count, but `loot_on_ground.value` was set False back at regress.py:39, so only the backpack path is covered.
- reachable: bridge_only
- missing capability: (none)

**How to prove it:**

```python
for ground in (False, True):
    g.loot_on_ground.value = ground
    saved = g._money(pc)
    pc.PlayerReplicationInfo.AddCurrencyOnHand(cur.CURRENCY_Credits, -saved)
    bi, bp = len(g._backpack(pc)), len(list(unrealsdk.find_all('WillowPickup')))
    g._grind(pc, feed)
    assert len(g._backpack(pc)) == bi
    assert len(list(unrealsdk.find_all('WillowPickup'))) == bp, 'broke player still got loot'
    pc.PlayerReplicationInfo.AddCurrencyOnHand(cur.CURRENCY_Credits, saved)
```

### 21. Nothing is ever taken until the output exists — the module's stated rule at grinder.py:27.

- proven today: **partly**
- evidence: regress.py:47 and :56 prove it for the two refusals the harness tests. Two later failure points (charge throwing, handover throwing) are untested and violate it in opposite directions.
- reachable: bridge_only
- missing capability: (none)

**How to prove it:**

Force each failure and check both directions:
```python
# 1. the charge fails after the loot has already been made
g.loot_on_ground.value = True
real, g._charge = g._charge, (lambda p, a: False)
n, bp = len(g._backpack(pc)), len(list(unrealsdk.find_all('WillowPickup')))
g._grind(pc, feed)
assert len(list(unrealsdk.find_all('WillowPickup'))) == bp, 'free loot: spawned, then kept the inputs'
g._charge = real
# 2. the handover fails after the inputs have already been eaten
g.loot_on_ground.value = False
import types
mgr = pc.GetPawnInventoryManager()
n = len(g._backpack(pc)); bm = g._money(pc)
# monkeypatch AddBackpackInventory via g's own call site is easiest: wrap _grind's manager
```
Check 1 FAILS today: grinder.py:948-949 returns after `_drop_loot` has already spawned the pickup, so the player keeps three items and gets a free one.

### 22. Every rarity a real backpack can contain maps to a pool of the right tier, or to nothing at all.

- proven today: **no**
- evidence: regress.py:64-66 looks unmapped-hunting but `_pool_for` (grinder.py:800-806) falls back to the highest LOWER rarity, so almost nothing ever returns None and the assert cannot fail.
- reachable: bridge_only
- missing capability: (none)

**How to prove it:**

```python
assert g._pool_for('grenade', 502) is None, g._pool_for('grenade', 502)
assert g._pool_for('weapon', 502) is None
assert g._pool_for('weapon', 7) is None or 'Legendary' in g._pool_for('weapon', 7)
assert g._pool_for('weapon', 8) is None or 'Legendary' in g._pool_for('weapon', 8)
```
All four FAIL today. 502 falls back to the legendary pool; weapon rarity 7 and 8 (which BL2-LOOT-POOLS.md:35 records as legendary) fall back to `Pool_Weapons_All_05_VeryRare_Alien`, an E-tech downgrade.

### 23. Skins and heads are never offered by either recipe.

- proven today: **no**
- evidence: regress.py:60-61 is vacuous: it selects items where `_kind(i)=='skin'` and then asserts `_kind(s) in NOT_GRINDABLE`, which is true by definition of the filter and also true when the backpack has zero skins.
- reachable: bridge_only
- missing capability: (none)

**How to prove it:**

```python
inv = pc.GetPawnInventoryManager()
skin = next(i for i in g._backpack(pc) if g._kind(i) == 'skin')
for _ in range(3): inv.ClientAddItemToBackpack(skin.DefinitionData, 1, 0, False, 0, 0)
for recipe in ('perfect', 'grind'):
    captured.clear(); g._choose_items(pc, recipe)
    labels = [b.name for b in captured[-1].kw['buttons']] if captured else []
    assert g._label(skin) not in ' | '.join(labels), (recipe, labels)
```
The `perfect` half FAILS today: grinder.py:442-446 groups by `_definition_name` with no `NOT_GRINDABLE` check, unlike the grind branch at grinder.py:448-452.

### 24. Grinding spends duplicates rather than the item you have owned longest (grinder.py:487 'Newest first').

- proven today: **no**
- evidence: (none)
- reachable: bridge_only
- missing capability: (none)

**How to prove it:**

```python
inv = pc.GetPawnInventoryManager()
src = next(i for i in g._backpack(pc) if g._kind(i) == 'weapon')
inv.ClientAddWeaponToBackpack(src.DefinitionData, 0, False, 0, 0)
assert str(g._backpack(pc)[-1]) != str(src), 'backpack is newest-first'
```
If that assert holds, the Backpack array is append-order (oldest first) and `chosen = found[:wanted]` at grinder.py:489 eats the OLDEST copies — the opposite of the comment.

### 25. 'Perfect an item' only ever groups genuine copies of the same item.

- proven today: **no**
- evidence: (none)
- reachable: bridge_only
- missing capability: (none)

**How to prove it:**

```python
names = {}
for i in g._backpack(pc):
    if g._kind(i) == 'weapon':
        names.setdefault(g._definition_name(i), []).append(g._label(i))
for k, v in names.items():
    assert len(set(v)) == 1, (k, set(v))
```
This FAILS: grinder.py:147 reads `WeaponTypeDefinition`, which is the weapon TYPE. The evidence is already on disk — data/grinder-findings.txt:24 and :75 record `_definition_name` returning `WT_Tediore_Shotgun` and `WT_Jakobs_Shotgun`, shared by every gun of that manufacturer and class.

### 26. Perfecting refuses at 'items per grind' = 1 and takes nothing.

- proven today: **partly**
- evidence: regress.py:69-72 sets how_many=1, calls `_choose_items(pc,'perfect')`, asserts the backpack count is unchanged. That assert would also pass if the function silently did nothing for the wrong reason, since `_choose_items` never modifies the backpack on any path.
- reachable: bridge_only
- missing capability: (none)

**How to prove it:**

```python
g.how_many.value = 1; captured.clear()
g._choose_items(pc, 'perfect')
assert captured == [], 'a menu was built for an impossible recipe'
assert 'at least 2' in open(FINDINGS, encoding='utf-8').read().splitlines()[-1]
```

### 27. Perfecting eats N-1 items, keeps one, and charges — the whole `_perfect` function.

- proven today: **no**
- evidence: `_perfect` appears nowhere outside grinder.py (grepped the whole repo). regress.py never calls it. The only trace of it ever running is data/grinder-findings.txt:64, one human session.
- reachable: bridge_only
- missing capability: (none)

**How to prove it:**

```python
real, g.OptionBox = g.OptionBox, FakeBox   # MUST be in place: _perfect ends in _offer_element
inv = pc.GetPawnInventoryManager()
src = next(i for i in g._backpack(pc) if g._kind(i) == 'weapon')
for _ in range(3): inv.ClientAddWeaponToBackpack(src.DefinitionData, 0, False, 0, 0)
copies = g._backpack(pc)[-3:]
uid = int(copies[0].DefinitionData.UniqueId)
bi, bm = len(g._backpack(pc)), g._money(pc)
g._perfect(pc, copies)
assert len(g._backpack(pc)) == bi - 2, len(g._backpack(pc)) - bi
assert bm - g._money(pc) == g._cost(copies)
assert any(int(i.DefinitionData.UniqueId) == uid for i in g._backpack(pc))
```

### 28. Perfecting when nothing is better takes nothing and charges nothing (grinder.py:555-557).

- proven today: **no**
- evidence: (none)
- reachable: bridge_only
- missing capability: (none)

**How to prove it:**

Three exact clones have identical parts, so `_take_best_parts` must return 0:
```python
bi, bm = len(g._backpack(pc)), g._money(pc)
g._perfect(pc, copies)   # three ClientAddWeaponToBackpack clones of one gun
assert len(g._backpack(pc)) == bi and g._money(pc) == bm
```
This is the refusal path with the largest blast radius and it has never been run.

### 29. A part the grinder calls 'better' is actually better.

- proven today: **no**
- evidence: (none)
- reachable: bridge_only
- missing capability: (none)

**How to prove it:**

```python
seen = {}
for p in unrealsdk.find_all('WeaponPartDefinition'):
    seen[str(p.Name)] = g._part_rank(p)
ranked = {k: v for k, v in seen.items() if v >= 0}
print(len(ranked), 'of', len(seen), 'weapon parts rank at all')
for k, v in list(ranked.items())[:40]: print(v, k)
assert all('Grade' in k or 'Upgrade' in k for k in ranked), \
    [k for k in ranked if 'Grade' not in k and 'Upgrade' not in k]
```
The assert should FAIL and name the parts the trailing-digit fallback (grinder.py:725-729) mistakes for grades — BL2 accessory parts are variant-numbered (`..._1`, `..._2`), which is not a quality scale. Then repeat over `unrealsdk.find_all('ArtifactPartDefinition')`, where the `AttributeSlotUpgrades` path (grinder.py:714-721) is the measured one.

### 30. A part swapped onto the keeper actually changes the gun the player carries, not just the struct on it.

- proven today: **no**
- evidence: (none)
- reachable: bridge_only
- missing capability: (none)

**How to prove it:**

This is the falsifying probe for the trap levelless.py:11-14 already measured ('the weapon object caches what it was built with'):
```python
uid = int(keeper.DefinitionData.UniqueId)
before = keeper.InstantHitDamage
g._perfect(pc, copies)      # with a genuinely better donor part
kept = next(i for i in g._backpack(pc) if int(i.DefinitionData.UniqueId) == uid)
inv.ClientAddWeaponToBackpack(kept.DefinitionData, 0, False, 0, 0)
fresh = g._backpack(pc)[-1]
assert kept.InstantHitDamage == fresh.InstantHitDamage, \
    f'in-place edit never took: edited={kept.InstantHitDamage} rebuilt={fresh.InstantHitDamage}'
```
If `fresh` differs from `kept`, `_take_best_parts` is writing data the weapon object ignores and every 'N parts improved' message is a lie.

### 31. A perfected item survives a save/quit/reload with its new parts (the sanity check does not delete it).

- proven today: **no**
- evidence: BL2-DESIGN-grinder.md:102-104 lists this as an untested risk; nothing has changed.
- reachable: needs_input
- missing capability: The character-select screen needs one ENTER. bl2-mcp/tools/load.sh already does it via PowerShell SendKeys, but that steals the foreground window, so it can only run when nobody is at the machine.

**How to prove it:**

Perfect an item, record `uid` and every `*PartDefinition` on it to a file, then `game_quit`, `game_launch`, `game_load_character`, and re-read:
```python
kept = next(i for i in g._backpack(pc) if int(i.DefinitionData.UniqueId) == uid)
assert {s: str(getattr(kept.DefinitionData, s)) for s in slots} == saved_slots
```
Run it twice: once with SanitySaver loaded and once with it out of sdk_mods, so the answer names which mod is holding it up.

### 32. Only elements this particular gun could legally carry are offered — a gun that cannot be slagged is never offered slag.

- proven today: **no**
- evidence: (none)
- reachable: bridge_only
- missing capability: (none)

**How to prove it:**

```python
bad = {}
for i in g._backpack(pc):
    if g._kind(i) != 'weapon': continue
    ch = g._element_parts(i)
    off = {k: str(v.Name) for k, v in ch.items() if '_Elemental_' not in str(v.Name)}
    if off: bad[g._label(i)] = off
assert not bad, bad
```
This is the check for grinder.py:624-633: it accepts EVERY `WeaponPartDefinition` sharing the current element part's `Outer` and takes the text after the last underscore as the element name. Nothing filters on `_Elemental_`, so if any weapon family keeps barrels or grips in the same package they get offered as elements and written into `ElementalPartDefinition`.

### 33. The chosen element lands on the item and the gun really becomes that element.

- proven today: **partly**
- evidence: data/grinder-findings.txt:65 'Lucid Provacateur is now fire' is the mod's own success message, printed by grinder.py:592 without reading anything back. A human may have seen the item card; nothing recorded it.
- reachable: bridge_only
- missing capability: (none)

**How to prove it:**

```python
ch = g._element_parts(item)
target = ch.get('Corrosive') or list(ch.values())[0]
assert g._set_element(item, target)
assert str(item.DefinitionData.ElementalPartDefinition.Name) == str(target.Name)   # the write landed
inv.ClientAddWeaponToBackpack(item.DefinitionData, 0, False, 0, 0)
fresh = g._backpack(pc)[-1]
assert g._label(fresh) == g._label(item), (g._label(fresh), g._label(item))
```
The last assert is the real one: a gun whose element genuinely changed gets a new title/prefix. If the rebuilt copy is named differently from the edited original, the edit never reached the weapon.

### 34. The element offer appears only for guns, and only when there is a real choice.

- proven today: **no**
- evidence: (none)
- reachable: bridge_only
- missing capability: (none)

**How to prove it:**

```python
for i in g._backpack(pc):
    captured.clear(); g._offer_element(i)
    if g._kind(i) != 'weapon':
        assert captured == [], (g._kind(i), g._label(i))
    elif captured:
        assert len(captured[-1].kw['buttons']) >= 2
```

### 35. Making an item level-less charges only when the mark actually succeeds.

- proven today: **no**
- evidence: regress.py:76-92 tests `levelless.mark` and `levelless._forget` DIRECTLY. The grinder's own cost/charge/toggle path at grinder.py:384-401 has never been executed by anything.
- reachable: bridge_only
- missing capability: (none)

**How to prove it:**

```python
from bl2_modern.features import levelless as L
real_mark, L.mark = L.mark, (lambda item: False)
captured.clear(); g._choose_items(pc, 'levelless')
box = captured[-1]; b = box.kw['buttons'][0]
bm = g._money(pc)
box.kw['on_select'](box, b)
assert g._money(pc) == bm, 'charged for a level-less mark that failed'
L.mark = real_mark
```
FAILS today: grinder.py:396-399 charges, then calls `mark`, and never refunds.

### 36. Picking a starred item again turns level-less off, free, and takes nothing.

- proven today: **no**
- evidence: regress.py:91-92 calls `L._forget(uid)` directly; the grinder's toggle branch at grinder.py:391-393 is untouched.
- reachable: bridge_only
- missing capability: (none)

**How to prove it:**

```python
captured.clear(); g._choose_items(pc, 'levelless')
box = captured[-1]
starred = next(b for b in box.kw['buttons'] if b.name.startswith('* '))
bm, bi = g._money(pc), len(g._backpack(pc))
box.kw['on_select'](box, starred)
assert g._money(pc) == bm and len(g._backpack(pc)) == bi
assert not L.is_marked(item)
```

### 37. 'Report what the grinder sees' writes a report and takes nothing.

- proven today: **no**
- evidence: Not only is there no automated check — the artefact proves no HUMAN has ever run it either. grep of data/grinder-findings.txt (81 lines) for 'grinder report' returns nothing, and grinder.py:295 makes '=== grinder report ===' the unconditional first line of every successful run.
- reachable: bridge_only
- missing capability: (none)

**How to prove it:**

```python
from pathlib import Path
p = Path(g.__file__).parent.parent / 'data' / 'grinder-findings.txt'
bi, bm = len(g._backpack(pc)), g._money(pc)
before = p.stat().st_size
g._report(pc)
text = p.read_text(encoding='utf-8')
assert '=== grinder report ===' in text
assert '--- the game\'s own spawn function ---' in text
assert p.stat().st_size > before
assert len(g._backpack(pc)) == bi and g._money(pc) == bm
```

### 38. Dropping loot does not permanently change how the rest of the game drops loot.

- proven today: **no**
- evidence: (none)
- reachable: bridge_only
- missing capability: (none)

**How to prove it:**

```python
cdo = unrealsdk.find_object('Behavior_SpawnLootAroundPoint',
                            'WillowGame.Default__Behavior_SpawnLootAroundPoint')
bp, br = [str(x) for x in cdo.ItemPools], cdo.CircularScatterRadius
g._drop_loot(pc, pool, pc.Pawn)
assert [str(x) for x in cdo.ItemPools] == bp, 'grinder left its pool on the game default'
assert cdo.CircularScatterRadius == br
```
FAILS by construction: grinder.py:838-840 assigns straight onto the class default object and never restores it.

### 39. Turning the Second Wind mod off in the mod menu stops the grinder taking over the chest.

- proven today: **no**
- evidence: (none)
- reachable: bridge_only
- missing capability: (none)

**How to prove it:**

```python
from bl2_modern.core import all_hooks
ids = {h.hook_identifier for h in all_hooks()}
for h in (g.on_used_definition, g.on_used_object,
          g.on_golden_key_prompt, g.on_cannot_afford):
    assert h.hook_identifier in ids, h.hook_identifier
```
FAILS today: grinder.py:1236-1244 registers `Feature(... keybinds=[...], apply=_attach ...)` with no `hooks=` list, so `core.all_hooks()` (core.py:129-131) never sees them and `build_mod` cannot disable them.

### 40. An item the grinder produced reaches the second player in co-op (the single fact BL2-DESIGN-grinder.md:89 says shaped the whole design).

- proven today: **no**
- evidence: BL2-DESIGN-grinder.md:105-106 and BL2-WAKE-UP.md:143 both list it as needing two people.
- reachable: needs_second_player
- missing capability: A second running client with the bridge feature enabled, plus a way to run one request against each. bl2-mcp/tools/ask.sh is hard-wired to one install path (ask.sh line 3).

**How to prove it:**

Host grinds on machine A with `loot_on_ground.value = True`; on machine B run through the bridge:
```python
names = sorted(str(p) for p in unrealsdk.find_all('WillowPickup'))
print(names)
```
and assert the pickup A created is in B's list. Then repeat with `loot_on_ground.value = False` — the `AddBackpackInventory` path is host-local and is the one likeliest to fail.

## Suspected bugs

- **[breaks_the_feature]** grinder.py:147 `for slot in ("WeaponTypeDefinition", "ItemDefinition"):`
  - `_definition_name` returns the weapon TYPE, not the gun. `WeaponTypeDefinition` is shared by every gun of one manufacturer and class — the proof is already on disk in data/grinder-findings.txt:24 and :75, where it printed `WT_Tediore_Shotgun` and `WT_Jakobs_Shotgun`. `_perfect`'s guard `names = {_definition_name(i)}; if len(names) != 1` (grinder.py:531-533) therefore accepts three completely different Tediore shotguns as 'copies of the SAME item'.
  - bites: The menu says 'Exspansive Shredifier x3' but the group may be a legendary plus two whites of the same type, and `_take_best_parts` will then splice parts across unrelated guns — including onto a legendary. It also makes the whole 'three Shams become the best Sham' promise (grinder.py:522) false for every weapon.

- **[breaks_the_feature]** grinder.py:725-729 `digits = re.search(r"(\d+)$", str(part.Name))` / `return int(digits.group(1)) if digits else -1`
  - For weapon parts, `AttributeSlotUpgrades` does not exist, so ranking falls to a trailing number in the part's name. BL2 weapon accessories are variant-numbered, not grade-numbered (`SG_Accessory_Bayonet_1` / `_2`), so the fallback reads variant identity as quality.
  - bites: `_take_best_parts` swaps parts on the strength of a meaningless suffix and then reports 'N parts improved' — data/grinder-findings.txt:64 is exactly that message on a gun. The player is told the gun got better with no evidence it did, and the resulting part combination is one the game never rolls, which is what the sanity check deletes.

- **[breaks_the_feature]** grinder.py:659-691, `_take_best_parts`, and grinder.py:640-642 `data = item.DefinitionData; data.ElementalPartDefinition = part; item.DefinitionData = data`
  - Both perfecting and element choice write `DefinitionData` back onto an existing item and stop there. The sibling feature in the same repo measured that this does not work: levelless.py:11-14 — 'the weapon object caches what it was built with, so its damage does not move. Measured: setting a level 49 sniper's GameStage to 51 left its damage at exactly 1442.66' — and levelless.py:144-147 therefore rebuilds via `ClientAddWeaponToBackpack`. The grinder never rebuilds.
  - bites: If the cache applies to part and element fields too, every 'perfected' gun and every element change is cosmetic-at-best until the save is reloaded, while the mod charges money, eats N-1 items and reports success. Two features in one pack disagree about the same mechanism and only one of them measured it.

- **[breaks_the_feature]** grinder.py:800-806 `lower = [r for (k, r) in POOLS if k == kind and r < rarity]; return POOLS.get((kind, max(lower))) if lower else None`
  - `_pool_for` silently falls back to the highest lower rarity. BL2-LOOT-POOLS.md:37 records rarity 502 and 506 on mission items and unique grenades and says 'Ignore them' — the code does the opposite: `_pool_for('grenade', 502)` returns `Pool_GrenadeMods_06_Legendary`. In the other direction, weapon rarity 7 and 8 (legendary, per BL2-LOOT-POOLS.md:35) are absent from POOLS and fall back to `Pool_Weapons_All_05_VeryRare_Alien`.
  - bites: Three junk mission items become a legendary — an unlimited legendary printer, and mission items may also refuse to be removed, in which case grinder.py:950-951 charges and eats nothing while still handing over the reward. And a legendary weapon reporting 7 or 8 grinds DOWN into an E-tech, breaking the 'same rarity out' promise in the other direction.

- **[breaks_the_feature]** grinder.py:1069-1073, `if not enabled.value or _busy or GOLDEN_CHEST not in name: return None` / `if _skip_once: _skip_once = False`
  - `_skip_once` is a single global consumed by the first chest hook that fires. `_attach` (grinder.py:1170-1175) enables four hooks, at least two of which can fire for one chest interaction. Hook one consumes the flag and returns; hook two finds it False and opens the grinder.
  - bites: 'Open the chest normally' — the entry BL2-DESIGN-grinder.md:62 calls 'the important one', the reason Golden Keys stay useful — fails exactly whenever more than one hook is live. It is also unfalsifiable from the record: `_open_chest_normally` (grinder.py:990-994) uses `show_hud_message` rather than `_note`, so it writes nothing to data/grinder-findings.txt and there is no trace of anyone ever having used it.

- **[wrong_in_an_edge_case]** grinder.py:838-840 `behaviour = unrealsdk.find_object(..., "WillowGame.Default__Behavior_SpawnLootAroundPoint"); behaviour.ItemPools = [pool]; behaviour.CircularScatterRadius = 180`
  - `_drop_loot` mutates the class DEFAULT object and never restores it. Every grind overwrites the game-wide template for loot bursts.
  - bites: Any `Behavior_SpawnLootAroundPoint` created after the first grind that does not override `ItemPools` inherits the grinder's pool, and every one of them inherits a 180 scatter radius. It is a shared value written by one feature and read by the whole game, it persists for the session, and nothing in regress.py would ever see it.

- **[wrong_in_an_edge_case]** grinder.py:948-949 `if not _charge(pc, _cost(items)): return`
  - On the ground path, `_drop_loot` has already spawned the pickup (grinder.py:934-940) before this line. If `_charge` returns False — which it does whenever `_enum('ECurrencyType')` returns None or `AddCurrencyOnHand` throws (grinder.py:121-128) — the function returns with the loot in the world and the inputs still in the backpack.
  - bites: The mirror of the failure the whole module was built to avoid: instead of eating three legendaries for nothing, it hands out a free item for nothing. The same `_charge` failure on the backpack path leaks the spawned item object entirely.

- **[wrong_in_an_edge_case]** grinder.py:396-399 `if not _charge(pc, _cost([item])): return` then `if levelless.mark(item):`
  - The level-less path charges BEFORE the output exists, the exact inversion of the rule stated at grinder.py:27 and enforced everywhere else in the file. `levelless.mark` returns False when the item has no readable `UniqueId` (levelless.py:98-102), and there is no refund.
  - bites: The player pays and gets nothing, silently — `mark` failing only writes to the log, and grinder.py:399 simply skips its success message. Money loss is the least of it: it is the one place the module's own headline rule is broken.

- **[wrong_in_an_edge_case]** grinder.py:554-561 `moved = _take_best_parts(keeper, donors)` ... `if not _charge(pc, _cost(items)): return`
  - `_perfect` mutates and writes back the keeper (grinder.py:685-690) before charging. A failed charge returns having already improved the item and without consuming the donors.
  - bites: Free perfecting whenever the charge throws — and unlike the grind path, this one leaves the player strictly better off with the inputs intact, so nobody would ever report it.

- **[wrong_in_an_edge_case]** grinder.py:442-446, the `if recipe == "perfect": key = _definition_name(item)` branch of `_choose_items`
  - The perfect branch never checks `NOT_GRINDABLE`, while the grind branch three lines below (grinder.py:448-452) does. Skins and heads with three copies are offered under 'Perfect an item'.
  - bites: It directly contradicts BL2-WAKE-UP.md:44 ('skins and heads are never offered'), and the check that is supposed to catch it — regress.py:60-61 — is vacuous, so the claim reads as proven while the code that would prove it has never run.

- **[wrong_in_an_edge_case]** grinder.py:766 `("relic", 4): "GD_Itempools.ArtifactPools.Pool_Artifacts_04_VeryRare"`
  - The pack's own measured document contradicts this table entry. BL2-LOOT-POOLS.md:58: '`Pool_Artifacts_04_VeryRare` produces rarity 3 rather than 4.'
  - bites: Grinding three very-rare relics returns a rare relic — a silent downgrade of exactly the family the perfect recipe was demonstrated on. The measurement exists; only the table was never updated to match it.

- **[wrong_in_an_edge_case]** grinder.py:624-631 `for part in unrealsdk.find_all("WeaponPartDefinition"): if part.Outer is not package: continue; element = str(part.Name).rsplit("_", 1)[-1]`
  - Two problems on adjacent lines. (a) There is no `_Elemental_` name filter — any part sharing the current element part's `Outer` becomes an 'element', named by whatever follows its last underscore. (b) `is not` is identity on the Python wrapper, while grinder.py:676 uses `==` for the same kind of comparison; if pyunrealsdk does not intern UObject wrappers, `is` never matches and the element menu silently never appears.
  - bites: (a) writes a non-elemental part into `ElementalPartDefinition`, producing an item combination the game never rolls — the sanity-check deletion case BL2-DESIGN-grinder.md:102 warns about. (b) would be a silent no-feature. The file uses both comparison styles for object identity and has measured neither.

- **[wrong_in_an_edge_case]** grinder.py:1228-1233 `def _open_grinder(): pc = get_pc(); if pc is None: return; _open_menu(pc)`
  - The keybind checks neither `enabled.value` nor `_busy`, while every hook path checks both (grinder.py:1069).
  - bites: Switching 'Enable the grinder' off leaves H fully functional, contradicting the option's own description at grinder.py:53-59. And holding H stacks OptionBox instances: each `_open_menu` builds a fresh box whose `show()` only hides ITSELF (ui_utils/option_box.py:110-111), so earlier dialogs are never `Close()`d, and two menus opened at the same money value collide on the hook identifier `f"{hash(title):x}:{hash(message):x}"` (ui_utils/option_box.py:342).

- **[wrong_in_an_edge_case]** grinder.py:1236-1244 `register(Feature(name="Grinder", keybinds=[_open_grinder], writes_game_data=True, apply=_attach, options=[...]))`
  - No `hooks=` argument. The four chest hooks are enabled by hand in `_attach` and are invisible to `core.all_hooks()` (core.py:129-131) and therefore to `build_mod`.
  - bites: Disabling Second Wind in the mod menu disables the H keybind (which IS registered) but leaves all four chest hooks live forever. Every other feature in the pack passes its hooks to `Feature` — levelless.py:242-249 and bridge.py:151-159 both do — so this is an inconsistency, not a design choice.

- **[wrong_in_an_edge_case]** grinder.py:487-489 `# Newest first, so grinding spends the duplicates rather than a favourite.` / `chosen = found[:wanted]`
  - The comment asserts an ordering nobody measured. `found` is built by iterating `_backpack(pc)` (grinder.py:442), i.e. `pc.GetPawnInventoryManager().Backpack` in array order, which for an append-only inventory array is OLDEST first.
  - bites: If the array is append-order, `found[:wanted]` feeds the grinder the copies the player has carried longest — the favourite the comment says it protects — and the newest duplicates survive. Exactly backwards, and one line of bridge Python settles it.

- **[wrong_in_an_edge_case]** grinder.py:961-971, the `for new_item in made:` handover loop
  - Inputs are destroyed at grinder.py:950-951, and only then is the output handed over. If `AddBackpackInventory` throws for every item, `given` is empty and grinder.py:970-971 prints nothing at all beyond the per-item error.
  - bites: 'Nothing is taken until the output exists' (grinder.py:27) is true of the SPAWN but not of the HANDOVER. The item object exists and never reaches the player, who has already paid and lost N items. It is the same shape as the `Destroy()` bug the module was rewritten to fix, one step further down the function.

- **[cosmetic]** grinder.py:1182 `_note("watching for the chest - use it and this box will say which hook caught it")` at the end of `_attach`
  - `_attach` runs at every main menu AND on every `apply_all()` (core.py:180-193, called on save-options load), and `_note` writes to data/grinder-findings.txt and shows a HUD message each time.
  - bites: 51 of the 81 lines in data/grinder-findings.txt are this one sentence. The file is the pack's designated durable record — grinder.py:1022-1030 explains it exists because the log truncates — and it has been diluted to the point where the real evidence (lines 21-78) is buried.

- **[cosmetic]** grinder.py:678-683 `if _part_rank(theirs) > _part_rank(mine): ... moved += 1`
  - `moved` counts swaps, not slots. Two donors each beating the previous value in the same slot count twice.
  - bites: 'perfected X - N parts improved' (grinder.py:564) over-reports whenever N > 2, so the one number the human-run perfect test produced (data/grinder-findings.txt:64, '3 parts improved') does not mean three slots changed.
