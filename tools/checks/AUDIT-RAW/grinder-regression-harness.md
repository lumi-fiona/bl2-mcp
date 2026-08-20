# Grinder regression harness

Source file: `D:/SteamLibrary/steamapps/common/Borderlands 2/bl2-mcp/tools/regress.py`

**Purpose.** The single script that is supposed to prove the grinder and level-less gear work, run through the developer bridge against a live character; it prints 14 PASS/FAIL lines.

## Claims

### 1. It covers 'everything the grinder claims to do' (regress.py:1).

- proven today: **no**
- evidence: (none)
- reachable: filesystem_only
- missing capability: (none)

**How to prove it:**

Grep the harness for the grinder's own entry points:
```bash
grep -c 'g\._perfect\|g\._open_menu\|g\._report\|g\._open_chest_normally\|g\._choose_one_to_free\|g\._offer_element\|g\._take_best_parts\|g\._part_rank\|g\._try_take_over\|g\._drop_loot' regress.py
```
Expect 0. I grepped the whole repo: `_perfect`, `_offer_element`, `_take_best_parts`, `_part_rank`, `_open_menu`, `_report`, `_open_chest_normally`, `_choose_one_to_free`, `_try_take_over` and `_drop_loot` appear nowhere outside grinder.py. Of the five menu paths, only 'grind' is exercised, and only below the menu — `_choose_items(pc,'grind')` itself never runs; regress.py:24 builds `feed` by hand.

### 2. 'skins excluded' proves skins are never offered.

- proven today: **no**
- evidence: regress.py:60-61 — the assert is vacuous, see the bug below.
- reachable: bridge_only
- missing capability: (none)

**How to prove it:**

```python
results.append(('skins excluded', all(g._kind(s) in g.NOT_GRINDABLE for s in [])))
assert results[-1][1] is True   # a PASS with an empty backpack
```
Then replace it with the real check in the grinder feature entry above (drive `_choose_items` through a fake OptionBox and assert no skin label appears).

### 3. 'every kind maps to a pool' catches unmapped rarities.

- proven today: **no**
- evidence: regress.py:64-66 filters on `g._pool_for(k, r) is None`, but `_pool_for` (grinder.py:800-806) falls back to the highest lower rarity, so it returns None only for rarities below every mapped one.
- reachable: bridge_only
- missing capability: (none)

**How to prove it:**

```python
assert g._pool_for('grenade', 502) is None
```
The harness passes today while `_pool_for('grenade', 502)` returns the legendary grenade pool.

### 4. The refusal tests prove 'nothing was taken'.

- proven today: **partly**
- evidence: regress.py:47 and regress.py:56 compare backpack COUNT only. Neither reads money, and neither reads the world pickup count.
- reachable: bridge_only
- missing capability: (none)

**How to prove it:**

Add to both refusal cases: `assert g._money(pc) == bm` and `assert pk() == bp_`. A refusal that silently charged, or that dropped loot on the floor before refusing, passes today.

### 5. The harness leaves the character and the mod settings as it found them.

- proven today: **no**
- evidence: (none)
- reachable: bridge_only
- missing capability: (none)

**How to prove it:**

```python
before = (g.how_many.value, g.cost_per_level.value, g.loot_on_ground.value, g._money(pc), len(g._backpack(pc)))
exec(open('regress.py').read())
assert (g.how_many.value, g.cost_per_level.value, g.loot_on_ground.value) == before[:3]
```
FAILS: regress.py:8-9 and :39 assign to the user's live mods_base options and never restore them; regress.py:7 and :57 add 2,000,000 credits; every `seed()` call leaves items in the backpack. Recovery depends entirely on the external save restore (bl2-mcp/tools/restore-saves.sh), which is outside the script.

### 6. A FAIL is reported rather than lost.

- proven today: **no**
- evidence: (none)
- reachable: bridge_only
- missing capability: (none)

**How to prove it:**

Inject a raise into any step and run it:
```python
g._grind = lambda *a: (_ for _ in ()).throw(RuntimeError('boom'))
```
The script has no try/except around any case, so the first exception aborts before regress.py:96-99 prints anything — 14 checks become zero output, and the bridge reply is a traceback rather than a scoreboard. Wrap each block: `for name, fn in cases: try: fn() except Exception as ex: results.append((name, False))`.

### 7. It runs against the player's real controller.

- proven today: **no**
- evidence: regress.py:4 `pc = unrealsdk.find_all("WillowPlayerController")[-1]` — a positional guess, where the mod itself uses `get_pc()` everywhere (grinder.py:1100, :1125, :1215, :1230).
- reachable: bridge_only
- missing capability: (none)

**How to prove it:**

```python
from mods_base import get_pc
assert unrealsdk.find_all('WillowPlayerController')[-1] == get_pc()
```
If `find_all` includes the class default object or a stale controller, every downstream number in the harness is measured against the wrong player.

### 8. The mixed-rarity case really is mixed.

- proven today: **no**
- evidence: regress.py:42-44 takes the first two weapons of ANY rarity and appends one rarity-9 weapon.
- reachable: bridge_only
- missing capability: (none)

**How to prove it:**

```python
assert len({g._rarity(i) for i in mixed}) > 1, [g._rarity(i) for i in mixed]
```
If the first two happen to be rarity 9 too, the 'refusal' case becomes a successful grind and the assert at regress.py:47 fails for a reason that has nothing to do with what it is named after.

## Suspected bugs

- **[breaks_the_feature]** regress.py:60-61 `skins = [i for i in g._backpack(pc) if g._kind(i) == "skin"]` / `results.append(("skins excluded", all(g._kind(s) in g.NOT_GRINDABLE for s in skins)))`
  - The assert is a tautology. The list comprehension selects items where `_kind(i) == 'skin'`, then asserts `_kind(s) in NOT_GRINDABLE` — and `NOT_GRINDABLE` contains 'skin' (grinder.py:771). It also passes vacuously when the backpack holds no skins at all.
  - bites: It is the sole evidence behind BL2-WAKE-UP.md:44 'skins and heads are never offered', and that statement is FALSE for the perfect recipe (grinder.py:442-446 has no NOT_GRINDABLE check). A test that cannot fail is worse than no test: it converted an unchecked claim into a reported PASS.

- **[wrong_in_an_edge_case]** regress.py:8-9 `g.how_many.value = 3` / `g.cost_per_level.value = 100`, and regress.py:39 `g.loot_on_ground.value = False`
  - The harness writes to live mods_base options and never restores them. `loot_on_ground` is left False at the end (the user's default is True, grinder.py:81-90), and `cost_per_level` is left at 100 regardless of what the player chose.
  - bites: mods_base persists option values to the settings file, so a diagnostic run silently rewrites the player's configuration. Every subsequent chest grind then drops into the backpack instead of onto the floor, and the human reads it as a regression in the mod.

- **[wrong_in_an_edge_case]** regress.py:24, :34, :53 `feed = [i for i in g._backpack(pc) if g._kind(i) == "weapon" and g._rarity(i) == 3][:3]`
  - `seed()` adds three items, but `feed` is taken from the FRONT of the whole backpack, so on an append-order inventory it selects the player's pre-existing rarity-3 weapons and grinds those, not the seeded ones.
  - bites: The harness destroys real gear it never created. It survives only because bl2-mcp/tools/restore-saves.sh puts the save back afterwards — so the safety lives entirely outside the script, and anyone running regress.py directly through ask.sh loses items.

- **[wrong_in_an_edge_case]** regress.py:38 `results.append(("grind to ground: loot appeared in the world", pk() > bp_))`
  - `pk()` (regress.py:18-19) counts every WillowPickup in the world. It cannot distinguish the grinder's drop from any other pickup that appeared in the same window, and it does not check what dropped.
  - bites: It is the same racy count `_grind` itself uses to decide whether to consume the player's items (grinder.py:935-940). Test and implementation share one weak signal, so the test can never catch the case where that signal is wrong — a stray pickup makes both the mod and its test agree that a grind succeeded when nothing spawned.

- **[wrong_in_an_edge_case]** regress.py:96-99, the whole print block, with no try/except anywhere above it
  - Any exception in any of the 14 cases aborts the script before a single result line is printed.
  - bites: The bridge returns a traceback instead of a scoreboard, so a partial run looks identical to a broken bridge. It also means '14 of 14 passing' (BL2-WAKE-UP.md:3) is only ever reported when nothing threw — there is no such thing as a 13/14 run.

- **[wrong_in_an_edge_case]** regress.py:78-94, the level-less block
  - It calls `L.mark` and `L._forget` directly, bypassing the grinder menu path (`_choose_one_to_free`, grinder.py:361-408) that is the only way a player reaches them.
  - bites: The five level-less PASS lines are attributed to the grinder in BL2-WAKE-UP.md:85-95, but they prove the levelless module, not the grinder's cost/charge/toggle wrapper — which contains the charge-before-output bug at grinder.py:396-399 and has never been executed.
