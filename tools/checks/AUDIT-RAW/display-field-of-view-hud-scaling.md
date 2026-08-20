# Display (field of view + HUD scaling)

Source file: `D:/SteamLibrary/steamapps/common/Borderlands 2/sdk_mods/bl2_modern/features/display.py`

**Purpose.** Lets the player set field of view and HUD scale past the pause menu's own limits by writing the numbers straight onto the player controller, re-writing them every time a character spawns.

## Claims

### 1. The chosen FOV number lands on all three of FOVAngle, DesiredFOV and DefaultFOV.

- proven today: **no**
- evidence: (none)
- reachable: bridge_only
- missing capability: (none)

**How to prove it:**

Bridge request:
from bl2_modern.features import display as d
from mods_base import get_pc
pc = get_pc()
d.fov.value = 100
d._apply()
print(pc.FOVAngle, pc.DesiredFOV, pc.DefaultFOV)
assert (pc.FOVAngle, pc.DesiredFOV, pc.DefaultFOV) == (100.0, 100.0, 100.0)

### 2. Writing all three fields is what makes the FOV survive aiming down sights (display.py:15-17: 'Setting only the first is undone the moment you aim down a sight').

- proven today: **no**
- evidence: (none)
- reachable: bridge_only
- missing capability: The zoom function's real name must be resolved with game_function first; if no callable zoom entry point exists, this falls back to needs_input (hold right mouse) which cannot be done without stealing focus.

**How to prove it:**

Resolve the zoom function first with mcp__bl2__game_function on WillowGame.WillowWeapon, then bridge:
d.fov.value = 100; d._apply()
w = pc.Pawn.Weapon
w.OnZoomIn()   # exact name from game_function
w.OnZoomOut()
assert pc.DefaultFOV == 100.0 and pc.FOVAngle == 100.0

### 3. The values are re-applied on every character spawn, because the game resets them (display.py:22, 99).

- proven today: **no**
- evidence: (none)
- reachable: bridge_only
- missing capability: (none)

**How to prove it:**

Bridge:
d.fov.value = 100; d._apply()
pc.DefaultFOV = 70.0; pc.HUDScaleE = 0.5
d.on_character_live(pc, None, None, None)
assert pc.DefaultFOV == 100.0
assert abs(pc.HUDScaleE - d.hud_element_scale.value/100.0) < 1e-6

### 4. The SpawningProcessComplete hook actually fires on a real respawn/level load, not just when called by hand.

- proven today: **no**
- evidence: (none)
- reachable: needs_map_travel
- missing capability: Something must move the character between maps or kill them; the bridge can call pc.ConsoleCommand('open <map>') but the round trip needs a level load to complete.

**How to prove it:**

Bridge, install a counter then travel:
d._hits = 0
_o = d._apply_to
def counted(pc, _o=_o):
    d._hits += 1; return _o(pc)
d._apply_to = counted
# ... fast-travel or die, then a second bridge request:
assert d._hits >= 1

### 5. Leaving FOV at 0 lets the game's own setting stand and changes nothing (display.py:39-40).

- proven today: **no**
- evidence: (none)
- reachable: bridge_only
- missing capability: (none)

**How to prove it:**

Bridge — this assert FAILS today, which is the point:
d.fov.value = 100; d._apply()
d.fov.value = 0; d._apply()
assert pc.DefaultFOV != 100.0, 'setting 0 left the previous 100 on the controller'

### 6. The field of view range offered is 60 to 130 (display.py:11).

- proven today: **no**
- evidence: display.py:33 `fov = SliderOption("Field of view", 0, 0, 130,` — min_value is 0, not 60.
- reachable: filesystem_only
- missing capability: (none)

**How to prove it:**

Pure source read, runnable offline:
from bl2_modern.features import display as d
assert (d.fov.min_value, d.fov.max_value) == (60, 130), (d.fov.min_value, d.fov.max_value)
# fails today: min_value is 0

### 7. The 'HUD size' percentage lands on HUDScaleX and HUDScaleY as a fraction.

- proven today: **no**
- evidence: (none)
- reachable: bridge_only
- missing capability: (none)

**How to prove it:**

Bridge:
d.hud_scale.value = 250; d._apply()
assert (pc.HUDScaleX, pc.HUDScaleY) == (2.5, 2.5)

### 8. Raising 'HUD size' makes the heads-up display BIGGER (display.py:51-52; BL2-WAKE-UP.md:75 'the answer to a microscopic HUD on a big monitor').

- proven today: **no**
- evidence: (none)
- reachable: needs_screenshot
- missing capability: No way to read back a rendered frame; Scaleform lays the HUD out internally and the resulting element sizes are not exposed as properties.

**How to prove it:**

Two halves. Value half, bridge: assert pc.HUDScaleX == 2.5 after setting 250. Semantic half needs a frame: set hud_scale to 50 and to 250 and compare screenshots of the ammo counter's pixel size. Per BL2-ULTRAWIDE.md:27-29 HUDScaleX/Y are 'HUD H./V. BOUNDS - where HUD elements live on your screen', not size, so the expected result is the HUD spreading toward the screen edges rather than growing.

### 9. 90 is the game's own value for HUDScaleE (display.py:63-64), so the default is a no-op.

- proven today: **no**
- evidence: (none)
- reachable: bridge_only
- missing capability: (none)

**How to prove it:**

Bridge, read the stock value before the mod has written anything:
import unrealsdk
cdo = unrealsdk.find_class('WillowPlayerController').ClassDefaultObject
print('stock HUDScaleE:', cdo.HUDScaleE)
assert abs(cdo.HUDScaleE - 0.90) < 1e-6, 'default 90 is not the stock value; the pack shrinks the HUD out of the box'

### 10. Writing these onto the controller does not fight the game's own pause-menu sliders or the saved profile (BL2-ULTRAWIDE.md:27-29 records HUDScaleX/Y/E as profile settings 141/142/120).

- proven today: **no**
- evidence: (none)
- reachable: bridge_only
- missing capability: The profile-settings accessor chain must be resolved with game_find/game_function before the snippet is exact.

**How to prove it:**

Bridge — resolve the profile accessor with mcp__bl2__game_function first, then:
d.hud_scale.value = 200; d._apply()
prof = pc.GetWillowGlobals().GetPlayerProfileManager().GetCurrentProfileSettings()
# assert the profile still holds the OLD number -> the pause menu will show a stale value
# and any profile save writes it back over ours
print(prof)

### 11. The change applies to the local player only and does not touch a co-op partner's controller.

- proven today: **no**
- evidence: (none)
- reachable: needs_second_player
- missing capability: A second connected player.

**How to prove it:**

With two players connected, bridge on the host:
import unrealsdk
for c in unrealsdk.find_all('WillowPlayerController'):
    print(str(c), c.DefaultFOV, c.HUDScaleE)
# assert only the local controller carries the modded numbers

### 12. Moving a slider applies the NEW value, not the value from before the move (display.py:116-118).

- proven today: **partly**
- evidence: Source-verified this session at mods_base/options.py:144-155 — on_change_anytime is called before `super().__setattr__(name, value)`, so the manual `option.value = new_value` at display.py:118 is genuinely required and is correctly protected from recursion by the guard at options.py:141. Never executed at runtime.
- reachable: bridge_only
- missing capability: (none)

**How to prove it:**

Bridge, exercising the real __setattr__ path rather than calling _apply directly:
d.fov.value = 0
d.fov.value = 90
assert pc.DefaultFOV == 90.0, 'the callback applied the pre-move value'

### 13. A failed field write is reported rather than silently swallowed (display.py:78-79, 88-89).

- proven today: **no**
- evidence: (none)
- reachable: bridge_only
- missing capability: (none)

**How to prove it:**

Bridge, aim _apply_to at an object with none of the fields, then read the log:
import unrealsdk
d.fov.value = 100
d._apply_to(unrealsdk.find_all('WorldInfo')[-1])
# then filesystem: grep pyunrealsdk.log for exactly 3 'display: cannot set' lines
# and separately assert _apply() still prints its success line even when every write failed

## Suspected bugs

- **[breaks_the_feature]** display.py:45-54 and 81-85
  - 'HUD size' is wired to the wrong properties. `hud_scale = SliderOption("HUD size", 100, 50, 250, description=("How big the heads-up display is, as a percentage. ..."))` is mapped at lines 82-83 to `("HUDScaleX", hud_scale), ("HUDScaleY", hud_scale)`. The repo's own measured table at BL2-ULTRAWIDE.md:27-29 says HUDScaleX is 'HUD H. BOUNDS - where HUD elements live on your screen, horizontally' and HUDScaleY is the vertical equivalent; the property that means size is HUDScaleE, 'size of all HUD elements' — which display.py labels 'HUD text size'.
  - bites: Raising 'HUD size' to 250% pushes HUD elements outward toward and past the screen edges rather than enlarging them. On the 5120x1440 monitor this feature exists to serve, BL2-ULTRAWIDE.md:31 says the correct move is the opposite direction — 'Drag HUD H. BOUNDS to its minimum - that pulls the HUD in from the screen edges', and line 35 gives the worked example `PC.HUDScaleX = 0.7`. The two sliders are effectively swapped in meaning: the one named 'HUD text size' is the real HUD size control, and the one named 'HUD size' is a bounds/margin control whose useful range on an ultrawide is below 100, not above it.

- **[wrong_in_an_edge_case]** display.py:56-65 and 84
  - `hud_element_scale = SliderOption("HUD text size", 90, 50, 250, ...)` defaults to 90 and is written unconditionally: `("HUDScaleE", hud_element_scale)` at line 84, with no `if wanted > 0` guard equivalent to the one FOV gets at line 73.
  - bites: HUDScaleE is the real 'size of all HUD elements' lever (BL2-ULTRAWIDE.md:29). With stock settings the pack therefore writes HUDScaleE = 0.90 onto the controller on every single spawn. The claim that '90 is the game's own value' (line 64) is unverified — nothing in the repo records reading the stock HUDScaleE. If stock is 1.0, the pack silently shrinks the entire HUD by 10% out of the box, on every spawn, which is the exact opposite of the feature's stated purpose.

- **[wrong_in_an_edge_case]** display.py:33 vs display.py:11
  - `fov = SliderOption("Field of view", 0, 0, 130,` — the positional args are identifier, value, min_value, max_value, so min_value is 0. The module docstring at line 11 says 'The game's own menu offers 70 to 110; this offers 60 to 130.'
  - bites: Every value from 1 to 59 is selectable and is written straight onto FOVAngle/DesiredFOV/DefaultFOV with no clamp (line 77). An FOV of 5 is a near-unusable telescope view. The 60 floor that the docstring and BL2-WAKE-UP.md:70 both advertise does not exist in the code.

- **[wrong_in_an_edge_case]** display.py:72-73
  - `wanted = int(fov.value)` / `if wanted > 0:` — zero means 'skip the write', not 'restore what was there'.
  - bites: The description at lines 39-40 promises 'Leave at 0 to let the game's own setting stand and change nothing.' That is only true if you never moved the slider. Set FOV to 120, then back to 0, and the controller keeps 120 for the rest of the session — and the spawn hook at line 100 keeps re-confirming it. There is no saved original to restore, so the feature is one-way until the game is restarted.

- **[wrong_in_an_edge_case]** display.py:78-79, 88-89 and 109-112
  - Every setattr failure is caught and logged individually, but `_apply()` then logs `f"display: field of view {...}, HUD at {int(hud_scale.value)}%, HUD text at {int(hud_element_scale.value)}%"` unconditionally — it has no knowledge of whether any write succeeded.
  - bites: If the property names are wrong on some build, or the controller is a type without them, the log reports the intended numbers as though they were applied. Reading the log is then actively misleading: it looks like a working feature. The same anti-silent-failure care taken in configtweaks.py:148-152 was not applied here.

- **[wrong_in_an_edge_case]** display.py:115-119 combined with mods_base/options.py:141-153
  - `_changed` calls `_apply()`, which calls `get_pc()`. mods_base's willow implementation is `return ENGINE._get_field(_GAME_PLAYERS_PROP)[0]._get_field(_ACTOR_PROP)` (mods_base/__init__.py:160-161) — that raises IndexError when GamePlayers is empty, it does not return None. `_apply` does not guard it. The callback runs inside `ValueOption.__setattr__`, which sets `self._on_change_recursion_guard = True` at options.py:142 and deletes it at options.py:153 with no try/finally.
  - bites: Any exception out of `_apply()` leaves `_on_change_recursion_guard` set forever, so that option's on_change callback is silently skipped for the rest of the session — the slider stops doing anything and says nothing. Worse, this path also runs during settings load: SliderOption._from_json (options.py:346-355) assigns self.value, and mods_base/settings.py:36-42 calls `option._from_json(value)` with no try/except, so one raise aborts the whole mod's settings load and every option after 'Field of view' in the list keeps its default.
