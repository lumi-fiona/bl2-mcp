# Co-op rules and pause

Source file: `D:/SteamLibrary/steamapps/common/Borderlands 2/sdk_mods/bl2_modern/features/coopfixes.py`

**Purpose.** Flips four WillowGame.ini switches so the host can pause in co-op, bosses do not heal on reset, enemies stop hunting a downed player, and (optionally) one player's death sends both to New-U.

## Claims

### 1. bAdminCanPause=true lands under [Engine.GameInfo] in WillowGame.ini.

- proven today: **partly**
- evidence: Read this session: WillowGame.ini:5 under [Engine.GameInfo] reads `bAdminCanPause=true`; WillowGame.ini.bl2_modern_original:5 reads `false`. No automated check asserts it — regress.py:1-99 covers only grinder and levelless.
- reachable: filesystem_only
- missing capability: (none)

**How to prove it:**

Section-aware scan of WillowGame.ini asserting the [Engine.GameInfo] copy of bAdminCanPause equals 'true' AND that any other section's copy is unchanged (the sample at gamefiles.py:140-144 shows the key genuinely appears twice in these files).

### 2. bBossesRegenHealthOnReset=false and bEnemiesForgetDownedPlayers=true land under [WillowGame.WillowGameInfo].

- proven today: **partly**
- evidence: Read this session: WillowGame.ini:159 `bBossesRegenHealthOnReset=false` and :160 `bEnemiesForgetDownedPlayers=true`; the backup reads `true` and `false` respectively, so the pack made both changes.
- reachable: filesystem_only
- missing capability: (none)

**How to prove it:**

Same scanner against WillowGame.ini with section '[WillowGame.WillowGameInfo]'; assert bBossesRegenHealthOnReset=='false' and bEnemiesForgetDownedPlayers=='true'.

### 3. bResurrectAllPlayersWhenOneDies follows the 'One death sends both players to New-U' option.

- proven today: **partly**
- evidence: Read this session: sdk_mods/settings/bl2_modern.json:32 `"One death sends both players to New-U": true` and WillowGame.ini:158 `bResurrectAllPlayersWhenOneDies=true`. They agree today, but nothing asserts the coupling.
- reachable: filesystem_only
- missing capability: (none)

**How to prove it:**

Runnable offline, ties the two artefacts together:
import json, pathlib
s = json.load(open(r'D:\\SteamLibrary\\steamapps\\common\\Borderlands 2\\sdk_mods\\settings\\bl2_modern.json'))
want = 'true' if s['options']['One death sends both players to New-U'] else 'false'
# scan WillowGame.ini [WillowGame.WillowGameInfo] for bResurrectAllPlayersWhenOneDies
assert found == want, (found, want)

### 4. Turning the option off rewrites the ini immediately, so only the first launch after installing uses the default (coopfixes.py:41-44, 63-71).

- proven today: **no**
- evidence: (none)
- reachable: bridge_only
- missing capability: (none)

**How to prove it:**

Bridge:
import pathlib
from bl2_modern.features import coopfixes as cf
p = pathlib.Path.home()/'Documents/My Games/Borderlands 2/WillowGame/Config/WillowGame.ini'
cf.shared_death.value = False
assert 'bResurrectAllPlayersWhenOneDies=false' in p.read_text(encoding='utf-8', errors='replace')
cf.shared_death.value = True
assert 'bResurrectAllPlayersWhenOneDies=true' in p.read_text(encoding='utf-8', errors='replace')

### 5. These ini keys are live config properties the engine actually reads at startup, not dead strings (coopfixes.py:5-7).

- proven today: **no**
- evidence: (none)
- reachable: bridge_only
- missing capability: (none)

**How to prove it:**

The highest-value unrun check in this file. Bridge, after a launch with the file already flipped:
import unrealsdk
gi = unrealsdk.find_all('WillowGameInfo')[-1]
print(gi.bResurrectAllPlayersWhenOneDies, gi.bEnemiesForgetDownedPlayers, gi.bBossesRegenHealthOnReset)
assert gi.bResurrectAllPlayersWhenOneDies is True
assert gi.bEnemiesForgetDownedPlayers is True
assert gi.bBossesRegenHealthOnReset is False
print(unrealsdk.find_class('GameInfo').ClassDefaultObject.bAdminCanPause)
assert unrealsdk.find_class('GameInfo').ClassDefaultObject.bAdminCanPause is True

### 6. bAdminCanPause=true actually makes pause work in co-op — the headline promise.

- proven today: **no**
- evidence: (none)
- reachable: needs_second_player
- missing capability: A second connected player, plus a keypress to open the pause menu.

**How to prove it:**

With two players connected: host presses Escape, then bridge on both machines read `unrealsdk.find_all('WorldInfo')[-1].Pauser` and assert it is non-None on both. BL2-PACK-SCOPE.md:264 names a second thing to watch in the same session: whether a long pause trips ConnectionTimeout=30.0 and drops the second player.

### 7. Bosses no longer regenerate health when the fight resets.

- proven today: **no**
- evidence: (none)
- reachable: needs_map_travel
- missing capability: Requires being in a boss map with the boss spawned and damaged.

**How to prove it:**

Travel to a boss arena, bridge: record `boss.GetHealth()`, walk out of the trigger radius and back (or call the reset function found via game_function), then assert the health is unchanged rather than back at max.

### 8. Enemies forget a downed player rather than continuing to hunt them.

- proven today: **no**
- evidence: (none)
- reachable: needs_input
- missing capability: Getting into Fight For Your Life reliably needs either damage the bridge can inflict (function name unresolved) or a real enemy encounter.

**How to prove it:**

Bridge, force FFYL and read the AI target:
pc.Pawn.SetHealth(1)   # then take damage, or call the FFYL entry fn found with game_function
for e in unrealsdk.find_all('WillowAIPawn')[-10:]:
    print(str(e), e.Controller.Target if e.Controller else None)
# assert none of them still target pc.Pawn

### 9. bEnemiesCannotDoCloseAttacksOnDownedPlayers already ships true, so the release notes must not claim that half (coopfixes.py:8-10).

- proven today: **partly**
- evidence: Read this session: WillowGame.ini:161 reads `bEnemiesCannotDoCloseAttacksOnDownedPlayers=true`, and the diff against WillowGame.ini.bl2_modern_original shows only lines 5, 158, 159, 160 and 189 changed — line 161 is untouched, confirming it shipped true.
- reachable: filesystem_only
- missing capability: (none)

**How to prove it:**

Scan WillowGame.ini [WillowGame.WillowGameInfo] and assert bEnemiesCannotDoCloseAttacksOnDownedPlayers=='true' in BOTH the live file and the .bl2_modern_original backup — the backup is what proves the pack did not set it.

### 10. 'coopfixes: every setting already as wanted' (coopfixes.py:60) means the settings are as wanted.

- proven today: **no**
- evidence: (none)
- reachable: filesystem_only
- missing capability: (none)

**How to prove it:**

Offline, demonstrates it is false — a wrong section produces the same message:
from bl2_modern.gamefiles import apply_ini_edits
_, changed = apply_ini_edits(['[WillowGame.WillowGameInfo]\r\n','bBossesRegenHealthOnReset=true\r\n'],
                             '[WillowGame.WillowGameinfo]', {'bBossesRegenHealthOnReset':'false'})
assert changed == {}   # passes, yet nothing was written and the value is still 'true'

### 11. The feature is re-applied by the core whenever game data is re-applied.

- proven today: **no**
- evidence: (none)
- reachable: filesystem_only
- missing capability: (none)

**How to prove it:**

Offline / bridge:
from bl2_modern.core import all_features
f = [x for x in all_features() if x.name == 'Co-op rules and pause'][0]
assert f.apply is not None, 'core.apply_all() can never re-run this feature'
assert f.writes_game_data, 'the main-menu pass skips this feature'
# both fail today

### 12. The four writes do not disturb the rest of WillowGame.ini, including the other section's copy of bAdminCanPause.

- proven today: **partly**
- evidence: Diffed this session: the only differences are lines 5, 158, 159, 160 (coopfixes) and 189 (configtweaks). Line counts match. gamefiles.py:123-125 also raises if the line count would change, and gamefiles.py:150-153 self-checks the section scoping offline via `python gamefiles.py`.
- reachable: filesystem_only
- missing capability: (none)

**How to prove it:**

diff the live WillowGame.ini against WillowGame.ini.bl2_modern_original and assert the changed line numbers are exactly {5, 158, 159, 160} plus configtweaks' {189}, and that the line count is unchanged.

## Suspected bugs

- **[breaks_the_feature]** coopfixes.py:63-71
  - `def _on_change(_option, new_value): edit_ini(INI, WILLOW_GAME_INFO, {...})` — no try/except. edit_ini raises FileNotFoundError when the ini is missing (gamefiles.py:114-116) and RuntimeError on a line-count mismatch (gamefiles.py:123-125). This callback is installed at line 77 as on_change_anytime and is therefore invoked from inside mods_base's ValueOption.__setattr__ at options.py:144-145.
  - bites: Three compounding failures from one raise. (1) options.py:155 `super().__setattr__(name, value)` is never reached, so the option silently keeps its old value while the menu shows the new one. (2) options.py:142-153 sets `self._on_change_recursion_guard = True` and deletes it at line 153 with no try/finally, so the guard leaks and every later on_change for that option is silently skipped for the rest of the session — the toggle becomes permanently inert with no error. (3) During settings load, mods_base/settings.py:36-42 calls `option._from_json(value)` with no try/except, so the raise aborts the whole mod's settings load; 'One death sends both players to New-U' is the third option in the list (sdk_mods/settings/bl2_modern.json:32), so Difficulty presets, Game feel, Level scaling percent, Field of view, HUD size, HUD text size, Extra loot, Grinder and Developer bridge would all silently revert to defaults, and the keybind and enabled flag would never load.

- **[wrong_in_an_edge_case]** coopfixes.py:79 and 81-86
  - `_apply()` is called at module import, and the Feature is registered as `Feature(name="Co-op rules and pause", options=[shared_death])` — no `apply=` argument and `writes_game_data` left at its default False (core.py:63-64).
  - bites: Two consequences. The import-time run happens before saved settings load, so it always writes the class default (`True`) for bResurrectAllPlayersWhenOneDies regardless of what the owner chose; correctness then depends entirely on `_on_change` firing later during settings load, which only happens if the identifier is present in the json (settings.py:37-38). And because `apply` is None, neither core.py:457-466 (main menu) nor core.py:188-193 (`apply_all`, on character load) can ever re-run it — the pack's whole 'the core owns the timing' design at core.py:4-14 is bypassed for this one feature. A user who turns the option off sees the file get written twice per launch, wrong then right, and the log at line 70 announces a change they did not make on every single launch.

- **[cosmetic]** coopfixes.py:39 and 45
  - `changed |= edit_ini(INI, GAME_INFO, {...})` then `changed |= edit_ini(INI, WILLOW_GAME_INFO, {...})` — the dicts returned by edit_ini are keyed by bare key name (gamefiles.py:96 `changed[key] = (old, new)`), with no section qualifier.
  - bites: These files genuinely carry the same key in two sections — gamefiles.py's own self-check sample at lines 139-146 puts `bAdminCanPause` under both [Engine.GameInfo] and [WillowGame.WillowGameInfo] precisely because that is what the real file looks like. Today the two calls happen to touch disjoint keys, so nothing is lost. The moment anyone adds a key that exists in both sections, the second union silently discards the first section's report and the count at line 58 undercounts, while both edits actually happened. Latent, and the exact class of bug the section-scoping design at gamefiles.py:23-25 was built to avoid.

- **[wrong_in_an_edge_case]** coopfixes.py:55-60
  - `if changed: ... else: logging.info("coopfixes: every setting already as wanted")` — the else branch is reached whenever every edit_ini call returned an empty dict.
  - bites: Identical to the configtweaks case: gamefiles.py:88-89 skips keys it cannot find and gamefiles.py:121-122 returns {} for that, so a renamed key, a mistyped section constant (WILLOW_GAME_INFO at line 21) or a game patch dropping a setting all report 'every setting already as wanted'. Given the module docstring at lines 5-7 stresses that in-session testing proves nothing, this log line is the only feedback the feature ever gives, and it cannot tell success from total failure.
