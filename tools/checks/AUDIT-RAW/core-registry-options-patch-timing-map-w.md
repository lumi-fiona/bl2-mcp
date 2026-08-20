# Core (registry, options, patch timing, map watcher)

Source file: `D:/SteamLibrary/steamapps/common/Borderlands 2/sdk_mods/bl2_modern/core.py`

**Purpose.** Loads each feature in isolation so one bad file cannot take the pack down, runs the bundled text patches at the main menu, and re-applies hotfixes on every level load and map arrival.

## Claims

### 1. A feature that raises on import is recorded as failed and every other feature still loads.

- proven today: **partly**
- evidence: Structural: core.py:109-115 wraps each importlib.import_module in 'except Exception' and appends Feature(failed=...). Never exercised — unrealsdk.log:26 and :83 both show 15 of 15, i.e. the failure branch has no observed run.
- reachable: filesystem_only
- missing capability: (none)

**How to prove it:**

Add 'raise RuntimeError("probe")' to the top of features/ultrawide.py, relaunch, and assert the log contains 'Second Wind 0.17.0 - 14 of 15 loaded - FAILED: ultrawide' AND still contains 'Second Wind: Community Patch applied'.

### 2. A failed feature's hooks, options, keybinds, network functions and save options are all excluded.

- proven today: **no**
- evidence: (none)
- reachable: bridge_only
- missing capability: (none)

**How to prove it:**

With ultrawide forced to raise: assert len(core.all_hooks()) == 3 + sum(len(f.hooks) for f in core.all_features() if f.failed is None), and assert no option whose identifier belongs to ultrawide appears in core.all_options().

### 3. A feature that raises inside apply() is marked failed and stops affecting the game.

- proven today: **no**
- evidence: (none)
- reachable: bridge_only
- missing capability: (none)

**How to prove it:**

Bridge: pick a hooked writes_game_data feature, force its apply to raise, re-run core.on_main_menu's body, then assert the feature's hook no longer fires. Expected to FAIL — see bug.

### 4. The bundled patches run exactly once, at the main menu, after Gearbox's servers have been talked to.

- proven today: **partly**
- evidence: unrealsdk.log:67-68 shows both patch lines at 11:29:47.11x, once each, 4m16s after process start — consistent with the docstring at core.py:443-448. Observed once, no assert.
- reachable: filesystem_only
- missing capability: (none)

**How to prove it:**

assert the log contains exactly one line matching 'Community Patch applied' per process start, and that its timestamp is later than the first 'FrontendGFxMovie' related line.

### 5. The number of commands actually run is logged, so a silently-doing-nothing patch is visible.

- proven today: **yes**
- evidence: unrealsdk.log:67 'Community Patch applied, 4511 commands run, 0 failed, 2149 of them repeating on each level load, 479 held for particular maps, 3983 lines ignored' — core.py:296-300 produced it.
- reachable: filesystem_only
- missing capability: (none)

**How to prove it:**

assert re.search(r'Community Patch applied, (\d+) commands run', log).group(1) != '0'

### 6. Map-specific commands run when their map loads, and the map-name mismatch that cost 479 commands is now visible.

- proven today: **partly**
- evidence: BL2-WAKE-UP.md quotes '12 commands for sanctuaryair_p applied' from an earlier session, which is a human reading a log once. The only such line in the current log is core.py:378 'the game calls this map [menumap, menumap, menumap], and the patch has nothing for it' — i.e. the diagnostic fired for the main menu and can never fire again this session.
- reachable: needs_map_travel
- missing capability: walking a character through a fast-travel station; the bridge can read _map_done and _by_level but cannot drive travel without either a keypress or a scripted ConsoleCommand teleport

**How to prove it:**

Load a character, travel between two maps that both appear in _by_level, and assert the log gains one 'commands for <map> applied' line per arrival with a non-zero count. Also assert core._by_level has 483 keys (479 + 4, from the two 'held for particular maps' figures).

### 7. Options from a feature with four or more settings get their own page instead of flooding the main list.

- proven today: **no**
- evidence: (none)
- reachable: bridge_only
- missing capability: (none)

**How to prove it:**

Bridge: 'from bl2_modern import core; from mods_base import NestedOption; big = [f.name for f in core.all_features() if f.failed is None and len(f.options) >= core.GROUP_AT]; nested = [o.identifier for o in core.all_options() if isinstance(o, NestedOption)]; assert set(big) == set(nested)'

### 8. Keybinds, network functions and save options reach build_mod even though they live in feature files.

- proven today: **partly**
- evidence: Structural: __init__.py:24 passes all_keybinds(), :29 add_network_functions(mod, all_network_functions()), :39 register_save_options(...). The grinder keybind is documented working in BL2-WAKE-UP.md ('press H anywhere'), which is a human observation.
- reachable: bridge_only
- missing capability: (none)

**How to prove it:**

Bridge: 'from bl2_modern import mod; from networking.decorators import NetworkFunction; assert any(isinstance(n, NetworkFunction) and n.__wrapped__.__name__ == "announce" for n in mod.network_functions); assert any(k.identifier for k in mod.keybinds)' plus 'from save_options.registration import registered_save_options; assert registered_save_options'

### 9. The version reported to players, to the mods menu and to the handshake is one number from one source.

- proven today: **partly**
- evidence: core.py:34-54 reads pyproject.toml, which says version = "0.17.0"; unrealsdk.log:26 and :83 both print 'Second Wind 0.17.0'. Nothing asserts the mods-menu string matches.
- reachable: bridge_only
- missing capability: (none)

**How to prove it:**

Bridge: 'import tomllib, pathlib; from bl2_modern import core, mod; d = tomllib.loads(pathlib.Path(core.__file__).with_name("pyproject.toml").read_text()); assert core.__version__ == str(mod.version) == d["project"]["version"]'

### 10. 'One bad line cannot stop the rest' when running patch commands (core.py:303-317).

- proven today: **partly**
- evidence: unrealsdk.log:67-68 show '0 failed' for both patch files, so the failure branch has never run.
- reachable: bridge_only
- missing capability: (none)

**How to prove it:**

Bridge: 'from bl2_modern import core; ran, failed = core._run(["set Nonexistent.Class SomeProp 1", "this is not a command", "set WillowGame.WillowGameInfo bAdminCanPause true"]); assert ran + failed == 3 and ran >= 1'

## Suspected bugs

- **[wrong_in_an_edge_case]** core.py:464-466 'except Exception: feature.failed = traceback.format_exc(limit=3).strip(); logging.error(...)'
  - Marking a feature failed at apply time is cosmetic. Its hooks were handed to build_mod at import (__init__.py:24 -> core.all_hooks(), core.py:129-131) and nothing disables them afterwards; all_options/all_keybinds/all_network_functions were likewise already consumed.
  - bites: A feature reported as FAILED keeps running its PlayerTick / SpawningProcessComplete hooks for the whole session, so the log says one thing and the game does another. And the status line the player actually sees first (__init__.py:20) was printed minutes before any apply ran, so it can never contain an apply-time failure at all — confirmed in the log, where line 26 (11:25:39) and line 83 (11:29:47) both say '15 of 15' from two different code paths.

- **[breaks_the_feature]** core.py:366-381, the _logged_map_name one-shot inside _current_map
  - Only the FIRST map the watcher ever sees is reported. Observed today, unrealsdk.log:84: 'Second Wind: the game calls this map [menumap, menumap, menumap], and the patch has nothing for it' — the one and only diagnostic this session was about the main menu.
  - bites: The docstring at :351-353 says the name is logged 'so a mismatch is visible instead of silently costing 370 commands'. Because the menu map is always first and never matches, the log always burns its single report on menumap, and every real map afterwards is exactly as silent as the bug this was written to expose. Log once per distinct map name instead of once per process — a set instead of a bool.

- **[wrong_in_an_edge_case]** core.py:304 'pc = get_pc()' — outside the per-command try at :308-317
  - get_pc is mods_base's get_pc_willow (mods_base/__init__.py:160-163), which does ENGINE._get_field(GamePlayers)[0]._get_field(Actor) — it can return None or raise IndexError when no local player exists yet.
  - bites: The docstring one line above promises 'Run each command on its own, so one bad line cannot stop the rest'. If get_pc misbehaves, zero commands run and the whole batch dies as one — and on the on_character_live path (:342) that call has no try around it at all, so the exception escapes into the spawn hook. With 4511 + 32 commands riding on it, the difference between 'one line failed' and 'all of them failed' is the difference between a log line and a silent no-op patch.

- **[wrong_in_an_edge_case]** core.py:180-193 apply_all versus core.py:457-466 on_main_menu
  - The two apply paths disagree about what apply means. on_main_menu runs feature.apply() only for writes_game_data features; apply_all runs it for EVERY feature with an apply, and apply_all is wired as the save_options on_load callback (__init__.py:39), which fires on WillowPlayerController:LoadPlayerSaveGame POST (save_options/hooks.py:163-177) — i.e. on every character load.
  - bites: Nobody has counted how many times any given apply() runs. It is the mechanism that makes bridge._ready fire mid-session and eat live requests, and it is invisible in today's log only because no character was loaded in that session (features/bridge.py@148 appears exactly once, at 11:29:47.148). The check is one line: load a character and grep for a second 'bridge.py@148' line.

- **[wrong_in_an_edge_case]** core.py:320-343 on_character_live, running _run(_repeat_on_level_load) synchronously
  - 2152 ConsoleCommand calls (2149 from the Community Patch + 3 from Extras, per unrealsdk.log:67-68) are executed on the frame SpawningProcessComplete fires — every level load, not just the first.
  - bites: That is the frame the player is staring at coming out of a loading screen, and it is also the frame handshake.announce_on_spawn and extras.on_character_live and display.on_character_live all run on. Nobody has timed it. The measurement is cheap: wrap _run with time.perf_counter through the bridge and print the milliseconds on the next level load.

- **[cosmetic]** core.py:196-203 status_line, called from __init__.py:20 and again from core.py:468
  - The same sentence is logged twice per launch with two different meanings — import failures at 11:25:39.276, import-plus-apply failures at 11:29:47.148 (unrealsdk.log:26 and :83).
  - bites: Two identical-looking lines four minutes apart, where only the second one can ever mention an apply failure. Anyone grepping for 'Second Wind .* loaded' gets two hits and no way to tell which is authoritative. Naming them differently ('imported' vs 'ready') costs nothing.

- **[cosmetic]** core.py:391-432 on_tick and features/bridge.py:111-138 on_tick, both on WillowGame.WillowPlayerController:PlayerTick, each with its own '% 30' counter
  - Hook identifiers are distinct (mods_base/hook.py:246 builds them from module + qualname, so 'bl2_modern.core:on_tick' and 'bl2_modern.features.bridge:on_tick' coexist correctly) — but each keeps a private counter and both assume PlayerTick fires once per frame.
  - bites: If more than one WillowPlayerController ticks locally (split-screen, or a host ticking remote controllers), both counters advance N times per frame and the '% 30' budget silently becomes 'every 30/N-th'. Nobody has measured how many controllers tick. The probe is one request: count PlayerTick activations per second and compare against the map watcher's own _tick_count delta.

- **[wrong_in_an_edge_case]** __init__.py:34-44 / save_options, observed in unrealsdk.log at 11:29:39.930
  - 'save_options.sdkmod\\save_options\\hooks.py@152 WARN| Save data found for unregistered mod bl2_modern_uvhm, skipping.' — the mod id under which per-character settings were previously stored no longer exists, so that data in Lumi's saves is orphaned.
  - bites: Per-character settings (difficulty preset, level-less marks) are keyed by mod id. Renaming the mod silently abandons every character's saved choices with one WARN line, which is precisely the 'remembered per character' promise BL2-WAKE-UP.md makes for level-less gear. Worth a migration or at minimum a visible note; right now it is one line in a log nobody reads.
