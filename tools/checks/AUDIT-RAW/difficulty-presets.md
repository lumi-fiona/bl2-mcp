# Difficulty presets

Source file: `D:/SteamLibrary/steamapps/common/Borderlands 2/sdk_mods/bl2_modern/features/difficulty.py`

**Purpose.** Lets a character be put into UVHM rules from level 1 with a choice of two hand-tuned rulesets (BL2's own, or the Pre-Sequel's gentler 'Second Wind') plus a Custom slider set, by moving the character into playthrough 2 and rewriting the tiers on GD_Playthrough3Tuning.Balance.BalanceMod_PT3.

## Claims

### 1. Every preset builds a valid tier list for any tier count the game might report (1,2,3,4,5,6,8) and no two presets are numerically identical.

- proven today: **yes**
- evidence: sdk_mods/bl2_modern/difficulty.py:251-355, run 2026-08-19, exit 0
- reachable: filesystem_only
- missing capability: (none)

**How to prove it:**

cd sdk_mods/bl2_modern && python difficulty.py — asserts the cross-product distinctness (difficulty.py:272-279), the per-count build (difficulty.py:293-300), the stretch invariance (difficulty.py:314-325) and the four refusal cases (difficulty.py:342-353). I ran it today, it printed 'difficulty: all checks passed'.

### 2. `setattr(tier, name, value)` on elements pulled out of `list(obj.BalanceModifiers)` actually writes back into the array.

- proven today: **no**
- evidence: (none)
- reachable: bridge_only
- missing capability: (none)

**How to prove it:**

This is the single most load-bearing unproven claim in the file, and the code itself is inconsistent about it — difficulty.py:203-205 sets attributes on the pulled-out struct and never writes it back, while difficulty.py:246-249 on the same objects says 'Read out, edited, written back - safe whether these are views or copies'. Falsify or confirm in five lines:
```
import unrealsdk
from bl2_modern.difficulty import TARGET
o = unrealsdk.find_object('BalanceModifierDefinition', TARGET)
tiers = list(o.BalanceModifiers)
was = tiers[0].EnemyHealthMultiplier
tiers[0].EnemyHealthMultiplier = 99.0
print('through the copy:', tiers[0].EnemyHealthMultiplier)
print('through the object:', o.BalanceModifiers[0].EnemyHealthMultiplier)
assert o.BalanceModifiers[0].EnemyHealthMultiplier == 99.0, 'list() gives copies - _apply is a silent no-op'
o.BalanceModifiers[0].EnemyHealthMultiplier = was
```

### 3. Zeroing `BaseValueScaleConstant` on the HealthPassiveRegenerationRate effect actually stops enemies healing themselves.

- proven today: **no**
- evidence: (none)
- reachable: bridge_only
- missing capability: (none)

**How to prove it:**

The property write is checkable; the game effect is not, directly. Property half:
```
import unrealsdk
from bl2_modern.difficulty import TARGET
from bl2_modern.features import difficulty as D
o = unrealsdk.find_object('BalanceModifierDefinition', TARGET)
tiers = list(o.BalanceModifiers)
D._set_healing(tiers, False)
vals = [e.BaseModifierValue.BaseValueScaleConstant for t in o.BalanceModifiers for e in t.AttributeEffectsForSpawnedEnemies if 'HealthPassiveRegenerationRate' in str(e.AttributeToModify)]
assert vals and all(v == 0.0 for v in vals), vals
D._set_healing(tiers, True)
vals2 = [...same...]
assert vals2 == [1.0, 1.0, 1.25, 1.0], vals2   # the UCP's own 4-tier values, measured from patch.txt line 2556
```
Behaviour half: spawn an enemy, damage it, hold still and sample `pawn.GetHealth()` over ~10 seconds; assert it does not rise.

### 4. The healing effect still exists to be zeroed after the Community Patch has run.

- proven today: **yes**
- evidence: data/patch.txt line 2556, parsed 2026-08-19; 4 x MinEffectiveLevel, 4 x HealthPassiveRegenerationRate
- reachable: filesystem_only
- missing capability: (none)

**How to prove it:**

Measured offline against data/patch.txt line 2556: the UCP's 4-tier `set BalanceMod_PT3 BalanceModifiers` writes AttributeEffectsForSpawnedEnemies with HealthPassiveRegenerationRate in all four tiers, BaseValueScaleConstant = [1.0, 1.0, 1.25, 1.0]. Confirm live with the `vals2` assert above.

### 5. `GRI.SetCurrentPlaythrough(pc, 2)` puts the character into UVHM and `GetCurrentPlaythrough()` confirms it.

- proven today: **partly**
- evidence: difficulty.py:277-282 records a single manual observation on an already-UVHM character
- reachable: needs_input
- missing capability: creating a new character requires menu keystrokes (game_launch steal_focus), which steals the user's focus

**How to prove it:**

The docstring (difficulty.py:277-282) says this was measured once on a live character, which is 'a human once saw it work' at best — and it was measured on a character ALREADY in UVHM, per difficulty.py:262-265. Nobody has run it on a playthrough-0 character, which is the only case that matters. Check: on a fresh character, `import unrealsdk; from bl2_modern.features import difficulty as D; pc = unrealsdk.find_all('WillowPlayerController')[-1]; assert pc.GetCurrentPlaythrough() == 0; assert D._switch_to_uvhm(pc) is True; assert pc.GetCurrentPlaythrough() == 2`

### 6. The playthrough switch survives a save/quit/reload — or, if it does not, the hook redoes it on every spawn.

- proven today: **no**
- evidence: (none)
- reachable: needs_input
- missing capability: loading a character needs Enter pressed at the menu (server.py:180-208, steals focus)

**How to prove it:**

Nothing anywhere addresses this and it decides whether 'Normal' is ever recoverable. `pc.GetCurrentPlaythrough()` -> 2, `pc.SaveGame()`, quit to menu, reload the character, `assert pc.GetCurrentPlaythrough() == 2` (persisted) or `== 0` (not persisted, hook redoes it). Then set preset to Normal, reload, and assert whichever answer the docstring is going to claim.

### 7. 'Normal leaves the game completely alone' (difficulty.py:57-59).

- proven today: **no**
- evidence: (none)
- reachable: bridge_only
- missing capability: (none)

**How to prove it:**

False after any other preset has been used in the same session, and one paste proves it:
```
import unrealsdk
from bl2_modern.difficulty import TARGET
from bl2_modern.features import difficulty as D
o = unrealsdk.find_object('BalanceModifierDefinition', TARGET)
before = [(t.MinEffectiveLevel, t.EnemyHealthMultiplier, t.EnemyShieldStrengthMultiplier) for t in o.BalanceModifiers]
D._apply('Second Wind')
D._apply('Normal')
after = [(t.MinEffectiveLevel, t.EnemyHealthMultiplier, t.EnemyShieldStrengthMultiplier) for t in o.BalanceModifiers]
assert after == before, f'Normal did not restore the table: {before} -> {after}'
```
This assert FAILS today: difficulty.py:168-180 restores healing and nothing else.

### 8. A preset that cannot be applied safely is refused before anything is written, so it can never half-apply.

- proven today: **partly**
- evidence: sdk_mods/bl2_modern/difficulty.py:342-353 covers check() in isolation
- reachable: bridge_only
- missing capability: (none)

**How to prove it:**

The four refusal shapes are proven offline (difficulty.py:342-353). But the count check at difficulty.py:198 can no longer fire: `_wanted` is built with `len(tiers)` (difficulty.py:191) and `check` is called with the same `len(tiers)`, so the mismatch that caused the 2026-08-19 silent failure is now impossible by construction, not by the check. Assert the real guard instead: `import copy; snap = [dict((f, getattr(t, f)) for f in SETTABLE) for t in o.BalanceModifiers]; D._apply('NotAMode'); assert [dict(...)] == snap` — an unknown mode must write nothing (difficulty.py:192-194).

### 9. Preset numbers land on the object: after `_apply('UVHM')` the live table reads 4.0 health / 5.0 shields.

- proven today: **no**
- evidence: (none)
- reachable: bridge_only
- missing capability: (none)

**How to prove it:**

```
import unrealsdk
from bl2_modern.difficulty import TARGET
from bl2_modern.features import difficulty as D
D.start_level.value = 1
D._apply('UVHM')
t = list(unrealsdk.find_object('BalanceModifierDefinition', TARGET).BalanceModifiers)
assert [x.MinEffectiveLevel for x in t] == [1, 25, 50, 61][:len(t)], [x.MinEffectiveLevel for x in t]
assert all(round(x.EnemyHealthMultiplier, 3) == 4.0 for x in t)
assert all(round(x.EnemyShieldStrengthMultiplier, 3) == 5.0 for x in t)
assert all(round(x.XPGainedFromCombatMultiplier, 3) == 0.66 for x in t)
```

### 10. 'Second Wind' produces measurably different play from 'UVHM' — ordinary enemies soft, badasses the threat.

- proven today: **partly**
- evidence: sdk_mods/bl2_modern/difficulty.py:272-279 proves distinctness only
- reachable: needs_human_judgement
- missing capability: someone playing a level-1 Second Wind run and saying whether it feels right

**How to prove it:**

Numerically distinct is proven offline (difficulty.py:272-279). Landing on the object is the same assert as above with 1.5 / 2.5 / 1.5 / 3.5. The play-feel claim — 'badasses are the threat, not every skag' — is human judgement and no automated check reaches it. The numbers themselves are DERIVED from a Pre-Sequel data dump, never measured in a running game (difficulty.py:113-119).

### 11. Enemies stay at your own level everywhere once a preset is active, so the game can be played in any order.

- proven today: **no**
- evidence: (none)
- reachable: needs_input
- missing capability: a loaded character standing among spawned enemies; requires the Enter keypress to load

**How to prove it:**

This is the headline promise and nothing checks it. In a low-level area after switching a level-1 character to UVHM: `import unrealsdk; pc = unrealsdk.find_all('WillowPlayerController')[-1]; lvl = pc.PlayerReplicationInfo.ExpLevel; pawns = [p for p in unrealsdk.find_all('WillowAIPawn') if p.Health > 0]; assert pawns; bad = [(str(p.Name), p.GetExpLevel()) for p in pawns if abs(p.GetExpLevel() - lvl) > 2]; assert not bad, bad`. Confirm the level accessor name first with `game_function('WillowAIPawn', 'GetExpLevel')`.

### 12. Changing the preset mid-run takes effect on enemies that spawn afterwards.

- proven today: **no**
- evidence: (none)
- reachable: bridge_only
- missing capability: (none)

**How to prove it:**

`before = [p.GetMaxHealth() for p in unrealsdk.find_all('WillowAIPawn') if p.Health > 0]` in a spawn-heavy spot, then `D.preset.value = 'UVHM'`, then trigger a fresh spawn (`pc.ConsoleCommand('spawn ...')` or wait), and assert the new pawns' max health is ~4x the old. Note the docstring at difficulty.py:15-16 says 'the next area in practice' but `_on_change` (difficulty.py:426) applies to the table immediately — decide which one is the promise, then test that one.

### 13. The 'Rules start at level' slider actually moves where the rules begin.

- proven today: **partly**
- evidence: sdk_mods/bl2_modern/difficulty.py:302-308
- reachable: bridge_only
- missing capability: (none)

**How to prove it:**

Level list generation is proven offline (difficulty.py:302-308 asserts levels climb, do not repeat, and levels[0] == start). Landing on the object is not: `D.start_level.value = 30; D._apply('UVHM'); assert list(unrealsdk.find_object('BalanceModifierDefinition', TARGET).BalanceModifiers)[0].MinEffectiveLevel == 30`. Also worth asserting the quirk: with start=50 and 3 tiers the levels come out [50, 51, 52], not [50, 61, 72].

### 14. Moving a Custom slider re-applies with the NEW value, not the previous one (difficulty.py:434-443).

- proven today: **no**
- evidence: (none)
- reachable: bridge_only
- missing capability: (none)

**How to prove it:**

The `_store` workaround relies on mods_base' recursion guard, which I confirmed exists (options.py:139-155: `if name == "value" and not hasattr(self, "_on_change_recursion_guard")`). Prove the outcome, not the mechanism:
```
from bl2_modern.features import difficulty as D
import unrealsdk
from bl2_modern.difficulty import TARGET
D.preset.value = 'Custom'
D.custom_health.value = 300
t = list(unrealsdk.find_object('BalanceModifierDefinition', TARGET).BalanceModifiers)
assert round(t[0].EnemyHealthMultiplier, 2) == 3.0, t[0].EnemyHealthMultiplier
```
If the guard ever regresses this reads 2.0 (the previous 200).

### 15. Moving a Custom slider while a non-Custom preset is chosen changes nothing (difficulty.py:449-451).

- proven today: **no**
- evidence: (none)
- reachable: bridge_only
- missing capability: (none)

**How to prove it:**

`D.preset.value = 'UVHM'; D._apply('UVHM'); snap = [t.EnemyHealthMultiplier for t in o.BalanceModifiers]; D.custom_health.value = 500; assert [t.EnemyHealthMultiplier for t in o.BalanceModifiers] == snap`

### 16. The mode picker appears the first time a first-playthrough character spawns, and once per trip to the main menu.

- proven today: **no**
- evidence: (none)
- reachable: needs_screenshot
- missing capability: seeing whether the dialog box actually drew

**How to prove it:**

Whether it renders needs a screen. Whether the code path is entered does not: `from bl2_modern.features import difficulty as D; D._asked = False; D.ask_on_new.value = True; import unrealsdk; pc = unrealsdk.find_all('WillowPlayerController')[-1]; print('playthrough', pc.GetCurrentPlaythrough()); D._ask(pc); assert D._asked is True` — and check the log for 'could not show the mode picker'. The 'once per trip to the menu' half: `D.on_main_menu(None, None, None, None); assert D._asked is False`.

### 17. Picking 'Normal' in the picker leaves the game exactly as it is.

- proven today: **no**
- evidence: (none)
- reachable: bridge_only
- missing capability: (none)

**How to prove it:**

```
from bl2_modern.features import difficulty as D
from ui_utils import OptionBoxButton
D.preset.value = 'UVHM'          # simulate the no-save_options fallback path
D._ask(pc)                        # builds the box; grab the handler instead of clicking
# call the handler directly the way OptionBox would:
leave = OptionBoxButton('Normal', '')
# ...the real check: after choosing Leave, preset must read Normal
assert D.preset.value == 'Normal', D.preset.value
```
This FAILS today — `chosen` (difficulty.py:364-367) only logs when the Leave button is picked; it never assigns `preset.value`.

### 18. The preset is remembered per character, so two characters can play different difficulties.

- proven today: **no**
- evidence: (none)
- reachable: needs_input
- missing capability: two character loads, each needing an Enter keypress at the menu

**How to prove it:**

Requires two saves. `from bl2_modern.features import difficulty as D; assert D.PER_CHARACTER is True` proves only that save_options imported. Real check: on character A set preset='UVHM', `pc.SaveGame()`, quit to menu, load character B, `assert D.preset.value == 'Normal'`, load A again, `assert D.preset.value == 'UVHM'`. Note save_options/hooks.py:125-132 resets every save option to its constructor default on LoadGame, so the machine-wide value in sdk_mods/settings/bl2_modern.json ('Difficulty preset': 'Normal') is effectively dead once a character loads — worth asserting so nobody later 'fixes' the settings file.

### 19. The tier count is read off the running game rather than assumed, so a 3-tier vanilla game and a 4-tier patched game both work.

- proven today: **partly**
- evidence: sdk_mods/bl2_modern/difficulty.py:293-300
- reachable: bridge_only
- missing capability: (none)

**How to prove it:**

Offline: difficulty.py:293-300 builds every preset for 1,2,3,4,5,6,8 tiers. Live, both halves: with the Community Patch on, `assert len(list(unrealsdk.find_object('BalanceModifierDefinition', TARGET).BalanceModifiers)) == 4` then `D._apply('UVHM')` and assert no 'was NOT applied' line in the log; with `cp.enabled.value = False` and a relaunch, assert the count is 3 and the same apply succeeds.

### 20. The Community Patch's write to this same property happens BEFORE the difficulty feature's, so last write wins in the right order.

- proven today: **yes**
- evidence: measured 2026-08-19 by parsing data/patch.txt: 3 commands target GD_Playthrough3Tuning.Balance.BalanceMod_PT3, all outside hotfix elements
- reachable: filesystem_only
- missing capability: (none)

**How to prove it:**

Measured offline today and it holds two ways: (1) ordering — core.py:455 runs `run_bundled_patch()` before the `writes_game_data` loop at core.py:457-466, and communitypatch registers at features/__init__.py:24 while difficulty registers at :29; (2) no re-clobbering — the ONLY patch commands touching GD_Playthrough3Tuning.Balance.BalanceMod_PT3 BalanceModifiers are at patch.txt line 2556 (section 'Features', default on) and line 9847 (section 'Revert UVHM scaling back to pre-Lilith DLC', default off), and NEITHER is inside a <hotfix>, so neither re-runs on level load. Re-assert offline after any patch update: `assert all(level is None for level in levels_of_commands_targeting('BalanceMod_PT3','BalanceModifiers'))`.

### 21. Custom sliders produce sane multipliers across their whole declared range (0 to 600).

- proven today: **no**
- evidence: (none)
- reachable: filesystem_only
- missing capability: (none)

**How to prove it:**

`check()` (difficulty.py:224-248) validates field names and tier levels but never validates magnitudes, so 0 is accepted. Offline: `from bl2_modern.difficulty import custom, check; t = custom(1, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 4); check(t, 4)` succeeds today. Decide whether a 0x health multiplier is legal; if not, add `assert all(v > 0 for k, v in tier.items() if k != 'MinEffectiveLevel')` to check() and to the __main__ block.

## Suspected bugs

- **[breaks_the_feature]** difficulty.py:415-417 — `# Order matters: be in the playthrough first, then write the numbers it reads.` / `_switch_to_uvhm(obj)` / `_apply(preset.value)`
  - The return value of `_switch_to_uvhm` is discarded on the hook path, while the picker path four lines of reasoning earlier does check it: difficulty.py:366-367 `if _switch_to_uvhm(pc): _apply(button.name)`.
  - bites: `_switch_to_uvhm` returns False for three real reasons — `pc.WorldInfo.GRI` unavailable, `SetCurrentPlaythrough` raising, or the readback disagreeing (difficulty.py:289-310). In every one of those cases the hook still writes the preset to a table the game is not consulting, producing exactly the silent failure the function's own comment at difficulty.py:304-305 says it exists to prevent: 'the preset would be written to an object the game is not consulting, and everything would look like it worked'. On top of that, `_apply` then logs 'difficulty: applied UVHM - 4 tiers ...' which reads as success.

- **[breaks_the_feature]** difficulty.py:168-180 — the Normal branch of `_apply`: `if _healing_original: live = _tiers(quiet=True); if live is not None: _set_healing(live, enabled=True)` / `logging.info(f"difficulty: {chosen}, changing nothing")`
  - Switching back to Normal restores enemy self-healing and nothing else. The twelve multipliers written by the previous preset (difficulty.py:203-205) are never snapshotted and never restored — there is no `_tiers_original` to match `_healing_original`.
  - bites: The code's own comment three lines up states the rule it then breaks: 'switching away from a mode that silenced it back to Normal has to give the game back exactly what it shipped with, or "leaves the game completely alone" is a lie for the rest of the session'. Health at 4.0x and shields at 5.0x are a far bigger lie than the healing rate. Combined with the fact that the character is left in playthrough 2 (nothing ever calls SetCurrentPlaythrough(pc, 0)), selecting Normal after any other preset changes essentially nothing back.

- **[breaks_the_feature]** difficulty.py:203-205 (`for tier, values in zip(tiers, wanted, strict=True): for name, value in values.items(): setattr(tier, name, value)`) versus difficulty.py:246-249 (`effect.BaseModifierValue = modifier` / `effects[i] = effect` / `# Read out, edited, written back - safe whether these are views or copies.`)
  - Two write paths in the same function chain, operating on structs pulled out of the same `list(obj.BalanceModifiers)`, disagree about whether those structs are views or copies. `_set_highest`-style write-back is done in one and omitted in the other.
  - bites: If pyunrealsdk hands back copies, `_apply` is a total silent no-op and only the healing toggle works — which would be indistinguishable from working, because `_describe(_tiers() or tiers)` at difficulty.py:211 falls back to the same in-memory `tiers` list it just mutated when the re-read returns something falsy, and the success log prints the values it wanted rather than the values the object holds. One assert settles it (see the claim above); until then the feature's core mechanism is a coin flip nobody has called.

- **[wrong_in_an_edge_case]** difficulty.py:232-237 — `for index, tier in enumerate(tiers): try: effects = tier.AttributeEffectsForSpawnedEnemies  except Exception as ex: logging.error(f"difficulty: cannot reach tier {index}'s effects: {ex!r}"); return`
  - `return`, not `continue`. One unreadable tier abandons every tier after it.
  - bites: If tier 0 is the one that fails, no tier gets its healing changed at all, yet `_apply` carries straight on to difficulty.py:210-213 and logs 'enemies heal themselves: False'. The Second Wind preset's headline promise ('nothing heals itself', difficulty.py:60-61) would be false with a success line in the log.

- **[wrong_in_an_edge_case]** difficulty.py:364-367 — `def chosen(_box, button): if button is leave: logging.info("difficulty: mode picker - staying on Normal"); return`
  - Choosing the button labelled 'Leave the game exactly as it is.' (difficulty.py:350) never assigns `preset.value = NORMAL`.
  - bites: With save_options present this is masked, because save_options/hooks.py:125-132 already reset the option to its constructor default on LoadGame. But difficulty.py:32-38 deliberately supports running WITHOUT save_options (`PER_CHARACTER = False`, one setting for everyone). On that documented fallback path the spinner still holds the last character's choice, so picking 'Normal' leaves it on UVHM, `_asked` is now True so the picker never returns, and the very next level load runs difficulty.py:415-417 and converts the character to playthrough 2 with 4x health. The one-line fix is `preset.value = NORMAL` before the return.

- **[wrong_in_an_edge_case]** difficulty.py:373-386 — `box = OptionBox(title=..., message=..., buttons=[leave, *choices], on_select=chosen)` with no `on_cancel` and no `prevent_cancelling`
  - ui_utils/option_box.py:82 defaults `prevent_cancelling = False` and :86 defaults `on_cancel = None`, so Escape closes the box, `_paging_on_cancel` fires with nothing attached, and `_asked` (set True at difficulty.py:348) stays True.
  - bites: One stray Escape on a brand-new character means the mode question is never asked again until the player quits to the main menu, with no log line and no visible trace. Either `prevent_cancelling=True` or an `on_cancel=lambda _b: globals().__setitem__('_asked', False)` closes it.

- **[wrong_in_an_edge_case]** difficulty.py:191 `wanted = _wanted(chosen, len(tiers))` feeding difficulty.py:198 `check(wanted, len(tiers))`, with `custom_levels` at sdk_mods/bl2_modern/difficulty.py:186-198
  - Applying any preset overwrites the game's tier thresholds with `custom_levels(start, count)`. With the Community Patch's 4-tier table (MinEffectiveLevel = [50, 61, 72, 81], measured from patch.txt line 2556) and the default start of 1, the thresholds become [1, 25, 50, 61].
  - bites: The Overpower tiers at 72 and 81 stop existing as distinct bands, and the tier-2 healing scale of 1.25 that the UCP set for OP levels now applies from level 50 instead of 72. sdk_mods/bl2_modern/difficulty.py:167-178 reasons only about whether the PRESET's own upper rows are identical; it never considers that the rows it is overwriting meant something. Harmless for a level-1 run, wrong for an OP8 character.

- **[wrong_in_an_edge_case]** sdk_mods/bl2_modern/difficulty.py:186-198, `custom_levels` — `want = LATER_LEVELS[i - 1] if i - 1 < len(LATER_LEVELS) else levels[-1] + 11` / `levels.append(max(want, levels[-1] + 1))`
  - `custom_levels(50, 3)` returns [50, 51, 52], not [50, 61, 72] — because LATER_LEVELS[0] is 25, which loses to `levels[-1] + 1 = 51`. Visible in the self-test output I ran today: 'refused (levels out of order): ... got [51, 50, 52]' comes from `preset("UVHM", 50)`.
  - bites: A player who sets 'Rules start at level' to 50 to reproduce real UVHM gets tier boundaries one level apart, so UVHM's distinct first-tier damage multiplier (1.1 vs 1.0, sdk_mods/bl2_modern/difficulty.py:106-110) applies for exactly one level instead of eleven. The menu says the setting is 'the level these rules begin applying at' and it silently also collapses the spacing.

- **[cosmetic]** difficulty.py:182-189 — `tiers = _tiers(quiet=quiet)` / `if tiers is None: if quiet: logging.info(f"difficulty: {chosen} selected, and the tuning table is not loaded at the menu - it will be applied when a character loads")`
  - When `quiet` is False and the table is missing, `_apply` returns having logged only `_tiers`' own error and no statement that the preset was not applied. When `quiet` is True the message hard-codes 'at the menu' even though `_on_slider_change` (difficulty.py:451) and `_on_start_change` (difficulty.py:458) both call it with quiet=True while a character is live.
  - bites: Moving a slider in game while the tuning object is genuinely unreachable produces a log line blaming the main menu, sending anyone reading the log to the wrong place. Cosmetic but it is the only diagnostic this path has.

- **[wrong_in_an_edge_case]** difficulty.py:389-417, `on_character_live` — `obj` is whichever WillowPlayerController fired SpawningProcessComplete
  - Six features hook this same function (core.py:320, difficulty.py:389, extras.py:53, display.py:92, handshake.py:56, levelless.py:227). On a host, a joining client's controller also fires it, and difficulty then reads `obj.GetCurrentPlaythrough()` and may call `_switch_to_uvhm(obj)` on the remote controller.
  - bites: In co-op the host's playthrough governs the session. Calling SetCurrentPlaythrough with a client's controller is at best redundant and at worst re-triggers the mode picker on the host when a friend joins (the client's controller could read playthrough 0). Untested and untestable without a second player.
