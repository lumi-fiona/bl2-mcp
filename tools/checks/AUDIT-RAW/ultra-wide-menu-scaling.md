# Ultra-wide menu scaling

Source file: `D:/SteamLibrary/steamapps/common/Borderlands 2/sdk_mods/bl2_modern/features/ultrawide.py`

**Purpose.** Rewrites every UI movie definition's scale mode from SM_NoBorder to SM_ShowAll as the movie starts, so menus authored on a 1280x720 stage are not blown up and cropped on a very wide screen.

## Claims

### 1. The hook fires at all — GearboxFramework.GFxMovieDefinition:PostMovieStart is a real hook target that gets called for UI movies.

- proven today: **no**
- evidence: (none)
- reachable: bridge_only
- missing capability: (none)

**How to prove it:**

Bridge, count real invocations:
from bl2_modern.features import ultrawide as u
u._hits = 0
_o = u.fix_menu_scaling.__wrapped__
def counted(obj, a, r, f, _o=_o):
    u._hits += 1
    return _o(obj, a, r, f)
u.fix_menu_scaling.__wrapped__ = counted
u.fix_menu_scaling.enable()
# second request, after any menu has opened:
assert u._hits > 0

### 2. Every SM_NoBorder definition ends up at SM_ShowAll — no menu is left cropped.

- proven today: **no**
- evidence: (none)
- reachable: bridge_only
- missing capability: (none)

**How to prove it:**

Bridge census, the single highest-value check for this file:
import unrealsdk, collections
c = collections.Counter(); still = []
for o in unrealsdk.find_all('GFxMovieDefinition'):
    m = int(o.ScaleMode); c[m] += 1
    if m == 3: still.append(str(o))
print(c); print(still)
assert [s for s in still if 'Scopes' not in s] == []

### 3. The seven specific definitions named in BL2-ULTRAWIDE.md:88-94 are the ones fixed.

- proven today: **no**
- evidence: (none)
- reachable: bridge_only
- missing capability: Definitions are only loaded once their package is; run this at the main menu after each has been opened at least once, or the find_object will miss.

**How to prove it:**

import unrealsdk
for n in ['UI_Frontend_Legal.Frontend_Legal_Def','UI_GearboxAccount.GearboxAccount_DEF','UI_OnlineMessage.OnlineMessage_Definition','UI_TextChat.TextChat_DEF','UI_Lobby_LoadCharacter.LoadCharacter_DEF','UI_Lobby_ConfirmCharacter.ConfirmCharacter_DEF','UI_HUD_EchoVersion.EchoVersion_DEF']:
    o = unrealsdk.find_object('GFxMovieDefinition', n)
    print(n, int(o.ScaleMode))
    assert int(o.ScaleMode) == 1, n

### 4. Scopes are deliberately left alone (ultrawide.py:44, 46).

- proven today: **no**
- evidence: (none)
- reachable: bridge_only
- missing capability: (none)

**How to prove it:**

import unrealsdk
o = unrealsdk.find_object('GFxMovieDefinition', 'UI_Scopes.Scopes_Definition')
assert int(o.ScaleMode) == 3, 'the scope got rescaled and will no longer fill the screen'

### 5. The 'Scopes' substring test correctly identifies the scope definition.

- proven today: **partly**
- evidence: sdk_mods/.stubs/unrealsdk/unreal/_uobject.pyi:46-52 — UObject.__repr__ 'Gets this object's full name', and no __str__ is defined, so str(obj) carries the full path; BL2-ULTRAWIDE.md:95 gives the path as `UI_Scopes.Scopes_Definition`, which contains 'Scopes'. Source-derived, never executed.
- reachable: bridge_only
- missing capability: (none)

**How to prove it:**

import unrealsdk
s = str(unrealsdk.find_object('GFxMovieDefinition', 'UI_Scopes.Scopes_Definition'))
print(repr(s)); assert 'Scopes' in s

### 6. The boot / press-start legal screen is fixed — i.e. the mod is loaded and hooked before UI_Frontend_Legal.Frontend_Legal_Def starts.

- proven today: **no**
- evidence: BL2-ULTRAWIDE.md:82 explicitly flags this as the untested case with a named fallback (hook GFxUI.GFxMoviePlayer:Start POST and call SetViewScaleMode(1)). The fallback is not in ultrawide.py.
- reachable: bridge_only
- missing capability: (none)

**How to prove it:**

Bridge, run as early as the bridge can (first main-menu request):
import unrealsdk
o = unrealsdk.find_object('GFxMovieDefinition','UI_Frontend_Legal.Frontend_Legal_Def')
assert int(o.ScaleMode) == 1, 'boot screen ran before the hook was installed'

### 7. PostMovieStart's body is just SetViewScaleMode(ScaleMode) followed by SetAlignment(AlignMode), so rewriting ScaleMode pre-call makes the game apply our value (ultrawide.py:40-42).

- proven today: **partly**
- evidence: BL2-ULTRAWIDE.md:56-61 records a bytecode disassembly done in an earlier session. Not re-verified this session and not covered by any automated check.
- reachable: bridge_only
- missing capability: (none)

**How to prove it:**

mcp__bl2__game_function on 'GearboxFramework.GFxMovieDefinition:PostMovieStart' and confirm the disassembly is those two calls and nothing else.

### 8. The hook runs BEFORE the game applies the value (it is a PRE hook).

- proven today: **partly**
- evidence: mods_base/hook.py:167 — `hook_type: Type = Type.PRE` is the default, and ultrawide.py:30 passes no second argument. Source-verified this session; the assert has never been run.
- reachable: filesystem_only
- missing capability: (none)

**How to prove it:**

from bl2_modern.features import ultrawide as u
from unrealsdk.hooks import Type
assert u.fix_menu_scaling.hook_funcs == [('GearboxFramework.GFxMovieDefinition:PostMovieStart', Type.PRE)]

### 9. On a 16:9 screen SM_ShowAll and SM_NoBorder produce identical output, so a co-op partner on a normal monitor sees no difference (ultrawide.py:10-12).

- proven today: **no**
- evidence: (none)
- reachable: needs_screenshot
- missing capability: No way to capture or compare a rendered frame; Scaleform computes the viewport transform internally and does not expose it as a readable property.

**How to prove it:**

Launch windowed at 1920x1080, screenshot the character-select screen with the feature enabled and with fix_menu_scaling.disable() called before the menu opens, and compare the two images pixel-for-pixel.

### 10. One hook covers every menu in the game including any added by add-ons (ultrawide.py:43).

- proven today: **no**
- evidence: (none)
- reachable: needs_map_travel
- missing capability: Needs the DLC packages loaded, which requires travelling to those maps.

**How to prove it:**

Same census as the SM_NoBorder claim, but run after loading each DLC map and opening each vendor/menu; assert the counter of ScaleMode==3 definitions stays at exactly the Scopes entry.

### 11. Menus that never set ScaleMode and sit on the class default of 0 (SM_NoScale) render correctly and need no fix.

- proven today: **no**
- evidence: (none)
- reachable: needs_screenshot
- missing capability: The count is bridge-readable, but whether 0 means 'literal 1:1' or 'unset, use Scaleform's default' can only be settled by looking at a frame.

**How to prove it:**

Bridge census first — `print(c[0], 'definitions at SM_NoScale')` from the counter above — then a screenshot of the pause menu and inventory to see whether they render as a marooned 1280x720 island. BL2-ULTRAWIDE.md:111 names the exact remedy if so: add `if obj.ScaleMode == 0` to the same hook.

### 12. The feature writes no game data (ultrawide.py:54, writes_game_data=False).

- proven today: **no**
- evidence: (none)
- reachable: bridge_only
- missing capability: (none)

**How to prove it:**

True of disk, false of memory. Bridge:
u.fix_menu_scaling.disable()
o = unrealsdk.find_object('GFxMovieDefinition','UI_TextChat.TextChat_DEF')
assert int(o.ScaleMode) == 3, 'disabling the feature did not put the definition back'
# fails today: the mutation is permanent for the process

## Suspected bugs

- **[wrong_in_an_edge_case]** ultrawide.py:46-47
  - `if obj.ScaleMode == SM_NO_BORDER and "Scopes" not in str(obj):` / `obj.ScaleMode = SM_SHOW_ALL` — the write is permanent on the package object and there is no record of the previous value.
  - bites: Disabling the mod in the mod menu removes the hook but leaves every definition already rewritten at SM_ShowAll for the rest of the process. There is no way to A/B the feature, and no way to back it out if it turns out to be the cause of a menu problem, short of restarting the game. That directly undermines the debugging note in features/__init__.py:12-20 about menu breakage being the pack's known danger area.

- **[wrong_in_an_edge_case]** ultrawide.py:46
  - Only ScaleMode == 3 is rewritten. The unresolved question recorded at BL2-ULTRAWIDE.md:111 — 'most menus never set ScaleMode at all, so they sit on the class default of 0 = SM_NoScale ... If 0 is applied literally, those menus render 1:1 - a small 1280x720 island lost in the middle of your screen' — is still open and unhandled.
  - bites: If SM_NoScale is applied literally, the pause menu and inventory are marooned islands on a 5120x1440 screen and this feature does not touch them. The doc's own stop condition ('You'll know in three seconds on first launch') has no evidence anywhere in the repo that it was ever checked, and the census that would answer it is a three-line bridge request nobody has run.

- **[cosmetic]** ultrawide.py:46
  - `obj.ScaleMode` is read with no guard. UObject.__getattr__ (sdk_mods/.stubs/unrealsdk/unreal/_uobject.pyi:35-45) raises when the field is absent.
  - bites: Any GFxMovieDefinition subclass without a ScaleMode property, or a null obj, makes the hook raise on every single movie start for the rest of the session. Every other feature in this pack wraps its object writes (display.py:78, configtweaks.py:133, core.py:311); this one does not. BL2-PACK-PLAN-PHASE1.md:209 anticipated exactly this failure ('Errors in pyunrealsdk.log naming ScaleMode mean the property is not on that object') but no guard was added.

- **[cosmetic]** ultrawide.py:4-5
  - 'Seven of them are set to the scale mode SM_NoBorder.' The source table at BL2-ULTRAWIDE.md:88-95 lists seven definitions that get fixed PLUS `UI_Scopes.Scopes_Definition` marked 'excluded', which is only excluded because it is also SM_NoBorder.
  - bites: Off by one against the pack's own measured data. Harmless in itself, but the count is the thing a future reader would use to sanity-check the census assert, so a census returning eight SM_NoBorder definitions would look like a discrepancy when it is correct.
