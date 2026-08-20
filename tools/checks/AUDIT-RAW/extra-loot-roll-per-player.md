# Extra loot roll per player

Source file: `D:/SteamLibrary/steamapps/common/Borderlands 2/sdk_mods/bl2_modern/features/extraloot.py`

**Purpose.** In co-op, re-run each dying enemy's loot roll once per extra player so two people get two different guns instead of racing for one.

## Claims

### 1. Solo (one player) the feature changes nothing

- proven today: **no**
- evidence: No automated check exists. D:/SteamLibrary/steamapps/common/Borderlands 2/BL2-WAKE-UP.md:143 lists it as needing two people; regress.py never imports extraloot.
- reachable: bridge_only
- missing capability: (none)

**How to prove it:**

import unrealsdk
from bl2_modern.features import extraloot as X
X.enabled.value = True
calls = []
pawn = next(p for p in unrealsdk.find_all('WillowAIPawn') if p.Health > 0)
n0 = len(list(unrealsdk.find_all('WillowPickup')))
pawn.DropLootOnDeath()
n1 = len(list(unrealsdk.find_all('WillowPickup')))
print('solo drop delta:', n1 - n0)
# and prove the guard, not just the outcome:
assert X._player_count() == 1
assert (X._player_count() - 1) * int(X.rolls_each.value) == 0

### 2. The re-call form `func(args)` is accepted by the SDK at all (the module says this is unproven and ships the option off because of it)

- proven today: **partly**
- evidence: The call form is documented in the stubs shipped in this very repo: D:/SteamLibrary/steamapps/common/Borderlands 2/sdk_mods/.stubs/unrealsdk/unreal/_bound_function.pyi:29-30 - "Alternatively, may call with a single positional WrappedStruct which matches the type of the function, in order to reuse the args already stored in it." Documented, never executed here.
- reachable: bridge_only
- missing capability: (none)

**How to prove it:**

import unrealsdk
from bl2_modern.features import extraloot as X
pawn = next(p for p in unrealsdk.find_all('WillowAIPawn') if p.Health > 0)
seen = {}
def spy(obj, args, ret, func):
    seen['ok'] = func(args) is not None or True   # just: did it raise?
import unrealsdk.hooks as H
H.add_hook('WillowGame.WillowPawn:DropLootOnDeath', H.Type.PRE, 'probe', spy)
pawn.DropLootOnDeath()
H.remove_hook('WillowGame.WillowPawn:DropLootOnDeath', H.Type.PRE, 'probe')
assert seen.get('ok'), 'func(args) raised'

### 3. The extra call actually produces loot in the world, rather than returning cleanly and doing nothing

- proven today: **no**
- evidence: Nothing counts pickups. The only failure detector is `except Exception` at extraloot.py:84. BL2-LOOT-POOLS.md:76-84 documents three separate inventory calls in this game that return cleanly and do nothing - so 'it did not raise' is known here to be a weak signal.
- reachable: bridge_only
- missing capability: None - monkeypatching `_player_count` converts this from 'needs a second player' to a solo bridge test. That is the single cheapest unlock for this file.

**How to prove it:**

import unrealsdk
from bl2_modern.features import extraloot as X
X.enabled.value = True
X.rolls_each.value = 1
pawn = next(p for p in unrealsdk.find_all('WillowAIPawn') if p.Health > 0)
X._player_count = lambda: 1
b0 = len(list(unrealsdk.find_all('WillowPickup'))); pawn.DropLootOnDeath()
solo = len(list(unrealsdk.find_all('WillowPickup'))) - b0
pawn2 = next(p for p in unrealsdk.find_all('WillowAIPawn') if p.Health > 0 and p is not pawn)
X._player_count = lambda: 2
b1 = len(list(unrealsdk.find_all('WillowPickup'))); pawn2.DropLootOnDeath()
two = len(list(unrealsdk.find_all('WillowPickup'))) - b1
print('solo', solo, 'faked 2p', two)
assert two > solo, 'the extra roll produced no additional pickups'

### 4. The extra rolls are INDEPENDENT rolls of the pool - two different guns, not two copies of one (extraloot.py:9-10)

- proven today: **no**
- evidence: Never checked. The docstring asserts it as a design consequence of re-calling the roll, with no measurement.
- reachable: bridge_only
- missing capability: (none)

**How to prove it:**

import unrealsdk
from bl2_modern.features import extraloot as X
X.enabled.value = True; X.rolls_each.value = 4
X._player_count = lambda: 2
pawn = next(p for p in unrealsdk.find_all('WillowAIPawn') if p.Health > 0)
before = set(unrealsdk.find_all('WillowPickup'))
pawn.DropLootOnDeath()
new = [p for p in unrealsdk.find_all('WillowPickup') if p not in before]
names = [str(p.Inventory.DefinitionData.WeaponTypeDefinition.Name)
         if getattr(p.Inventory.DefinitionData, 'WeaponTypeDefinition', None) else
         str(p.Inventory.DefinitionData.ItemDefinition.Name) for p in new]
print(names)
assert len(set(names)) > 1, f'every extra roll produced the same item: {names}'

### 5. With N players and rolls_each=R, exactly (N-1)*R extra rolls happen - no more, no fewer

- proven today: **no**
- evidence: No test. Arithmetic is at extraloot.py:76, the loop at extraloot.py:82-83.
- reachable: bridge_only
- missing capability: (none)

**How to prove it:**

from bl2_modern.features import extraloot as X
import unrealsdk
X.enabled.value = True
for players, rolls in ((2,1), (2,3), (4,1), (1,5)):
    X._player_count = lambda p=players: p
    X.rolls_each.value = rolls
    n = []
    import unrealsdk.hooks as H
    H.add_hook('WillowGame.WillowPawn:DropLootOnDeath', H.Type.PRE, 'count',
               lambda o,a,r,f: n.append(1))
    pawn = next(p for p in unrealsdk.find_all('WillowAIPawn') if p.Health > 0)
    pawn.DropLootOnDeath()
    H.remove_hook('WillowGame.WillowPawn:DropLootOnDeath', H.Type.PRE, 'count')
    expected = 1 + max(0, (players - 1) * rolls)
    assert len(n) == expected, f'{players}p x{rolls}: {len(n)} calls, wanted {expected}'

### 6. The re-entrancy guard stops the replays re-triggering the hook forever (extraloot.py:45-46)

- proven today: **no**
- evidence: Untested. `_rolling` set at extraloot.py:80, cleared at extraloot.py:89-90.
- reachable: bridge_only
- missing capability: (none)

**How to prove it:**

Covered by the count test above: with players=2, rolls=1 the hook body must run exactly 2 times, not unbounded. Also assert the flag is left clean:
from bl2_modern.features import extraloot as X
assert X._rolling is False, 'guard left set - the feature is now permanently inert'

### 7. The enemy's own original loot drop still happens (the PRE hook does not block it)

- proven today: **no**
- evidence: Untested. The hook returns None (extraloot.py:74/78/90), which the SDK treats as 'allow' per sdk_mods/.stubs/unrealsdk/hooks/__init__.pyi:98-104.
- reachable: bridge_only
- missing capability: (none)

**How to prove it:**

import unrealsdk
from bl2_modern.features import extraloot as X
X.enabled.value = False
pawn = next(p for p in unrealsdk.find_all('WillowAIPawn') if p.Health > 0)
b = len(list(unrealsdk.find_all('WillowPickup'))); pawn.DropLootOnDeath()
base = len(list(unrealsdk.find_all('WillowPickup'))) - b
X.enabled.value = True; X._player_count = lambda: 2; X.rolls_each.value = 1
pawn2 = next(p for p in unrealsdk.find_all('WillowAIPawn') if p.Health > 0 and p is not pawn)
b = len(list(unrealsdk.find_all('WillowPickup'))); pawn2.DropLootOnDeath()
both = len(list(unrealsdk.find_all('WillowPickup'))) - b
assert both >= base, 'turning the feature on reduced the drop - the original roll was lost'

### 8. If the game refuses the call the feature switches itself off (extraloot.py:17-18, 84-88)

- proven today: **no**
- evidence: Untested, and it only catches a raised exception - see the pickup-count claim above for why that is a weak detector in this game.
- reachable: bridge_only
- missing capability: (none)

**How to prove it:**

from bl2_modern.features import extraloot as X
import unrealsdk
X.enabled.value = True; X._player_count = lambda: 2
class Boom:
    def __call__(self, *a): raise RuntimeError('refused')
pawn = next(p for p in unrealsdk.find_all('WillowAIPawn') if p.Health > 0)
X.on_loot_dropped.__wrapped__(pawn, None, None, Boom())
assert X.enabled.value is False, 'it kept the feature on after a refusal'
assert X._rolling is False

### 9. Switching itself off is durable - it does not come back on next launch and fail again

- proven today: **no**
- evidence: extraloot.py:85 sets `enabled.value = False` in memory only. Nothing calls `mod.save_settings()`; mods_base only writes the settings file from Mod.save_settings (mods_base/mod.py:318-320).
- reachable: filesystem_only
- missing capability: (none)

**How to prove it:**

import json, pathlib
from bl2_modern.features import extraloot as X
p = pathlib.Path(r'D:/SteamLibrary/steamapps/common/Borderlands 2/sdk_mods/settings/bl2_modern.json')
X.enabled.value = True
X.on_loot_dropped.__wrapped__(None, None, None, lambda *a: (_ for _ in ()).throw(RuntimeError()))
assert X.enabled.value is False
saved = json.loads(p.read_text())
assert saved['options']['Extra loot roll per player'] is False, 'the off switch was never written to disk'

### 10. The player count excludes players who have left but are not yet cleaned up (extraloot.py:53-56)

- proven today: **no**
- evidence: The stated rationale contradicts the code: it reads `pc.WorldInfo.GRI.PRIArray` (extraloot.py:59), which IS the world's replicated player list, not something private to the controller.
- reachable: bridge_only
- missing capability: To prove the disconnect case specifically you need a second player who then quits.

**How to prove it:**

import unrealsdk
pc = unrealsdk.find_all('WillowPlayerController')[-1]
pris = list(pc.WorldInfo.GRI.PRIArray)
for p in pris:
    print(p.PlayerName, 'bot:', p.bBot, 'inactive:', getattr(p, 'bIsInactive', '?'))
assert len(pris) == 1, f'solo session reports {len(pris)} PRIs - the count is inflated'

### 11. Host-only by nature: a client running this cannot create loot that only they can see

- proven today: **no**
- evidence: Nothing checks Role or NetMode anywhere in the file. BL2-LOOT-POOLS.md:101-103 records the opposite concern - objects a mod constructs itself do not reach the other player.
- reachable: needs_second_player
- missing capability: Two game instances, one hosting and one joining, with a bridge on each.

**How to prove it:**

import unrealsdk
pc = unrealsdk.find_all('WillowPlayerController')[-1]
print('NetMode:', pc.WorldInfo.NetMode, 'Role:', pc.Role)
# then, joined as a client with the option on, kill one enemy and compare:
#   client:  len(list(unrealsdk.find_all('WillowPickup')))
#   host:    len(list(unrealsdk.find_all('WillowPickup')))
# assert both machines see the same count

### 12. An enemy dying can never fail because of this feature (extraloot.py:84)

- proven today: **no**
- evidence: Untested. The try wraps only the loop (extraloot.py:81-83); `_player_count()` at extraloot.py:76 is outside it, though it has its own except at extraloot.py:60.
- reachable: bridge_only
- missing capability: (none)

**How to prove it:**

from bl2_modern.features import extraloot as X
X.enabled.value = True
X._player_count = lambda: (_ for _ in ()).throw(RuntimeError('boom'))
try:
    X.on_loot_dropped.__wrapped__(None, None, None, lambda *a: None)
except Exception as ex:
    raise AssertionError(f'the hook let an exception out into the death path: {ex!r}')

### 13. Bosses with guaranteed unique drops are not doubled into two copies of the same unique

- proven today: **no**
- evidence: Never considered in the file. Re-rolling the whole pool re-rolls guaranteed entries too.
- reachable: needs_map_travel
- missing capability: A map containing a boss with a guaranteed unique drop.

**How to prove it:**

import unrealsdk
from bl2_modern.features import extraloot as X
X.enabled.value = True; X._player_count = lambda: 2
boss = next(p for p in unrealsdk.find_all('WillowAIPawn')
            if 'BoomBewm' in str(p.Name) or p.IsChampion())
before = set(unrealsdk.find_all('WillowPickup'))
boss.DropLootOnDeath()
new = [p for p in unrealsdk.find_all('WillowPickup') if p not in before]
names = [str(p.Inventory.GetShortHumanReadableName()) for p in new]
print(names)
assert len(names) == len(set(names)), f'duplicated a guaranteed drop: {names}'

## Suspected bugs

- **[breaks_the_feature]** extraloot.py:84-88 - `except Exception as ex: enabled.value = False`
  - The only success criterion is 'the call did not raise'. This game is documented in BL2-LOOT-POOLS.md:76-84 to have at least three inventory calls that return cleanly and do nothing (`AddInventory`, `Destroy`, `RemoveFromInventory`), and levelless.py:21-23 records a fourth (`AddBackpackWeaponFromDefinitionData`). A DropLootOnDeath re-call that silently no-ops looks identical to success.
  - bites: The user is told at extraloot.py:18 to 'turn it on, kill something, and check the log once' - and the log will say nothing at all in the exact failure mode this codebase has already hit four times. Counting WillowPickup before/after inside the guard would be a two-line real check.

- **[wrong_in_an_edge_case]** extraloot.py:85 `enabled.value = False`
  - Turning itself off is memory-only. mods_base only writes the settings file from `Mod.save_settings()` (mods_base/mod.py:318-320); assigning `.value` merely fires on_change callbacks (mods_base/options.py:139-155).
  - bites: The self-disable does not survive a restart. Next launch the settings file still says True, the option is on again, and it fails again - once per session, forever, with one log line each time.

- **[wrong_in_an_edge_case]** extraloot.py:53-59 - the `_player_count` docstring vs `return max(1, len(pc.WorldInfo.GRI.PRIArray))`
  - The docstring says the count is read 'off the player controller rather than the world's player list' precisely to exclude departed players. `WorldInfo.GRI.PRIArray` is the world's replicated player list. The stated reasoning is inverted relative to what the code does.
  - bites: The failure it claims to prevent - handing out loot for someone who is not there - is exactly what this source can produce. And because the docstring reads like a measurement, nobody will re-check it.

- **[cosmetic]** extraloot.py:15-18 - "that call form has not been proven against the real function signature"
  - The call form IS documented, in a stub file inside this repo: sdk_mods/.stubs/unrealsdk/unreal/_bound_function.pyi:21-30 explicitly supports 'a single positional WrappedStruct which matches the type of the function, in order to reuse the args already stored in it'.
  - bites: The feature ships disabled (extraloot.py:29) on a fear that one Read of a local file dispels. The genuinely unproven parts - does the re-roll actually drop anything, does it drop something different - are the ones the docstring does not name.

- **[wrong_in_an_edge_case]** extraloot.py:64 `@hook("WillowGame.WillowPawn:DropLootOnDeath")` with no Role/NetMode check
  - Nothing restricts the hook to the host, despite the file's 'Host only, by nature' claim at extraloot.py:13.
  - bites: If WillowPawn:DropLootOnDeath also executes on a joined client, that client rolls extra pickups locally that the host never spawned - phantom loot that vanishes on the next map load, or worse, that only one player can see.
