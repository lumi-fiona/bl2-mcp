# Display + ultra-wide - the claims that need time to pass, a menu to be opened, or a map to
# load. Same file, run four times; it works out which phase it is in from what it left behind.
#
# THE OPERATOR RUNS EXACTLY THIS, from the Borderlands 2 folder:
#
#   bash bl2-mcp/tools/ask.sh bl2-mcp/tools/harness.py                          # once a session
#   bash bl2-mcp/tools/ask.sh bl2-mcp/tools/checks/display-and-ultrawide-needs-travel.py
#       phase 1: instruments both hooks, sets HUD size to 50%, photographs the screen
#   sleep 5                                                                     # the shot lands
#   bash bl2-mcp/tools/ask.sh bl2-mcp/tools/checks/display-and-ultrawide-needs-travel.py
#       phase 2: sets HUD size to 250%, photographs the screen again
#   sleep 5
#   >>> NOW, BY HAND: press Escape to open the pause menu, open the character screen,
#   >>> close both again. That is what makes the menu hook fire.
#   bash bl2-mcp/tools/ask.sh bl2-mcp/tools/checks/display-and-ultrawide-needs-travel.py
#       phase 3: checks the menu hook fired, then starts a fast travel and returns at once
#   sleep 90                                                                    # the map loads
#   ASK_TIMEOUT=90 bash bl2-mcp/tools/ask.sh bl2-mcp/tools/checks/display-and-ultrawide-needs-travel.py
#       phase 4: checks the spawn hook fired and the settings survived, then puts everything back
#
# IF YOU STOP EARLY, RUN PHASE 4 ANYWAY. Until it runs, field of view is left at 100, HUD size
# at 250%, and two counters are wrapped around the feature's own functions. Any later run of
# this file just restores again, so running it twice at the end is harmless.
#
# The two screenshots are the only honest way to settle "does raising HUD size make the HUD
# bigger". They land in Steam/userdata/<id>/760/remote/49520/screenshots/ - a person, or a
# later image read, has to compare them. The game's own menu text says the answer is no:
# WillowMenu.int:1515 calls HUDScaleX "HUD H. BOUNDS", not a size.

import unrealsdk

from bl2_modern.features import display as d
from bl2_modern.features import ultrawide as u

FIELDS = ("FOVAngle", "DesiredFOV", "DefaultFOV", "HUDScaleX", "HUDScaleY", "HUDScaleE")
SM_SHOW_ALL, SM_NO_BORDER = 1, 3

if not hasattr(d, "_check_state"):
    d._check_state = {"phase": 0, "spawns": 0, "movies": 0, "seen": set(), "travelled": False}
state = d._check_state
state["phase"] += 1
phase = state["phase"]

reset()
P = pc()
print(f"--- phase {phase}, map {where()} ---")


def census():
    counts = {}
    cropped = []
    try:
        movies = list(unrealsdk.find_all("GFxMovieDefinition", False))  # subclasses included
    except Exception:
        movies = list(unrealsdk.find_all("GFxMovieDefinition"))
    for movie in movies:
        if movie.Name.startswith("Default__"):
            continue
        try:
            mode = int(movie.ScaleMode)
        except Exception:
            continue
        counts[mode] = counts.get(mode, 0) + 1
        if mode == SM_NO_BORDER:
            cropped.append(str(movie))
    return counts, cropped


if phase == 1:
    state["options"] = [(o, o.value) for o in (d.fov, d.hud_scale, d.hud_element_scale)]
    state["fields"] = {}
    for name in FIELDS:
        try:
            state["fields"][name] = float(getattr(P, name))
        except Exception as ex:
            state["fields"][name] = None
            print(f"cannot read {name}: {ex!r}")

    d.fov.value = 100
    d.hud_element_scale.value = 200
    d.hud_scale.value = 50

    state["real_apply_to"] = d._apply_to
    state["real_wrapped"] = u.fix_menu_scaling.__wrapped__
    state["hook_was_on"] = u.fix_menu_scaling.get_active_count()

    def counted_apply_to(target, _real=state["real_apply_to"]):
        d._check_state["spawns"] += 1
        return _real(target)

    def counted_movie(obj, args, ret, func, _real=state["real_wrapped"]):
        d._check_state["movies"] += 1
        try:
            d._check_state["seen"].add(str(obj))
        except Exception:
            pass
        return _real(obj, args, ret, func)

    d._apply_to = counted_apply_to
    u.fix_menu_scaling.__wrapped__ = counted_movie
    u.fix_menu_scaling.enable()

    state["spawns"] = 0
    state["movies"] = 0
    P.DefaultFOV = 70.0
    P.HUDScaleE = 0.5

    check(
        "the counters are installed and the menu hook is still active",
        d._apply_to is counted_apply_to and u.fix_menu_scaling.get_active_count() == 1,
        f"menu hook active {u.fix_menu_scaling.get_active_count()}, was "
        f"{state['hook_was_on']} before",
    )
    print(f"HUD size now {d.hud_scale.value}% (HUDScaleX {P.HUDScaleX}) - photographing it")
    print(screenshot())
    print("next: sleep 5, then run this file again for phase 2")

elif phase == 2:
    d.hud_scale.value = 250
    print(f"HUD size now {d.hud_scale.value}% (HUDScaleX {P.HUDScaleX}) - photographing it")
    print(screenshot())
    check(
        "the second HUD photograph was taken with HUD size actually at 250%",
        abs(float(P.HUDScaleX) - 2.5) < 1e-6,
        "second shot is at HUDScaleX 2.5, first was at 0.5; a person must open the two files "
        "in Steam's screenshot folder and say whether the HUD got BIGGER (the slider's promise) "
        "or merely spread out toward the screen edges (what HUD H. BOUNDS actually means)",
    )
    print(f"menu hook has fired {state['movies']} times so far")
    print("next: sleep 5, OPEN AND CLOSE THE PAUSE MENU AND CHARACTER SCREEN, then phase 3")
    print("while they are open, LOOK at them: BL2-ULTRAWIDE.md:111 says a pause menu that is a "
          "small marooned island in the middle of the screen means the definitions sitting at "
          "SM_NoScale need the same fix, and nothing in the code answers that question")

elif phase == 3:
    check(
        "opening a menu makes GFxMovieDefinition:PostMovieStart fire, so the hook is real",
        state["movies"] > 0,
        f"{state['movies']} movie starts seen since phase 1: {sorted(state['seen'])[:8]}",
    )
    counts, cropped = census()
    print(f"scale mode census after opening menus: {counts}")
    print(f"still at SM_NoBorder: {cropped}")

    state["spawns_before_travel"] = state["spawns"]
    P.DefaultFOV = 70.0
    P.HUDScaleE = 0.5

    here = where()
    stem = here.split("_")[0].lower()
    names = sorted(stations())
    elsewhere = [n for n in names if stem not in n.lower()]
    target = next((n for n in elsewhere if "sanctuary" in n.lower()), elsewhere[0] if elsewhere else None)
    if target is None:
        print(f"no station away from {here}. Travel by hand, then run phase 4. Stations: {names}")
    else:
        state["travelled"] = True
        print(f"field of view and HUD text size knocked back to 70 / 0.5, now travelling to "
              f"{target} - this returns immediately, the load takes seconds")
        travel_to(target)
    print("next: sleep 90, then ASK_TIMEOUT=90 and run this file again for phase 4")

else:
    if phase == 4:
        moved = state["spawns"] - state.get("spawns_before_travel", 0)
        check(
            "a real level load fires the spawn hook that re-applies both settings",
            moved > 0,
            f"_apply_to ran {moved} times since the travel started ({state['spawns']} in all)",
        )
        check(
            "the field of view survived the level load without anyone touching a slider",
            abs(float(P.DefaultFOV) - 100.0) < 1e-6,
            f"DefaultFOV {P.DefaultFOV}, knocked to 70 just before travelling, map now {where()}",
        )
        check(
            "the HUD text size survived the level load",
            abs(float(P.HUDScaleE) - 2.0) < 1e-6,
            f"HUDScaleE {P.HUDScaleE}, knocked to 0.5 just before travelling",
        )
        counts, cropped = census()
        print(f"scale mode census after the load: {counts}")
        print(f"still at SM_NoBorder: {cropped}")
        print(f"menu hook has fired {state['movies']} times in all")

    # --- put everything back -------------------------------------------------------------
    if "real_apply_to" in state:
        d._apply_to = state["real_apply_to"]
    if "real_wrapped" in state:
        u.fix_menu_scaling.__wrapped__ = state["real_wrapped"]
        if state.get("hook_was_on"):
            u.fix_menu_scaling.enable()
        else:
            u.fix_menu_scaling.disable()
    for option, _old in state.get("options", []):
        if hasattr(option, "_on_change_recursion_guard"):
            del option._on_change_recursion_guard
    for option, old in state.get("options", []):
        option.value = old
    for name, old in state.get("fields", {}).items():
        if old is not None:
            try:
                setattr(P, name, old)
            except Exception as ex:
                print(f"could not put {name} back to {old}: {ex!r}")

    check(
        "everything this test moved is back where it started",
        d._apply_to is state.get("real_apply_to", d._apply_to)
        and u.fix_menu_scaling.__wrapped__ is state.get("real_wrapped", u.fix_menu_scaling.__wrapped__)
        and all(
            state.get("fields", {}).get(f) is None
            or abs(float(getattr(P, f)) - state["fields"][f]) < 1e-6
            for f in FIELDS
        ),
        f"controller {[getattr(P, f) for f in FIELDS]} vs "
        f"{[state.get('fields', {}).get(f) for f in FIELDS]}, options "
        f"{[o.value for o, _ in state.get('options', [])]}, menu hook active "
        f"{u.fix_menu_scaling.get_active_count()}",
    )
    del d._check_state
    print("state cleared - the next run of this file starts again at phase 1")

summary()
