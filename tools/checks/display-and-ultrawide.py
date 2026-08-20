# Display + ultra-wide menu scaling - checks for the claims in
#     AUDIT-RAW/display-field-of-view-hud-scaling.md
#     AUDIT-RAW/ultra-wide-menu-scaling.md
# Run: bash bl2-mcp/tools/ask.sh bl2-mcp/tools/checks/display-and-ultrawide.py
#
# Nothing here waits for anything, so it is one request. The claims that need a drawn frame
# (does a bigger HUD number make the HUD bigger; do SM_NoScale menus look marooned) and the
# ones that need a level load live in display-and-ultrawide-needs-travel.py. The claims about
# what the game's own menu calls these properties live in display-and-ultrawide-files.py.
#
# Every write here is undone in the finally, including the two module globals this patches
# (display's `logging` and mods_base's `get_pc`) and the ultra-wide hook's on/off state.
#
# Run it with a character loaded, not at the main menu: every display check reads and writes
# the live player controller.

import mods_base
import unrealsdk
from unrealsdk.hooks import Type

from bl2_modern.features import display as d
from bl2_modern.features import ultrawide as u

reset()

P = pc()

FIELDS = ("FOVAngle", "DesiredFOV", "DefaultFOV", "HUDScaleX", "HUDScaleY", "HUDScaleE")
before = {}
for _field in FIELDS:
    try:
        before[_field] = float(getattr(P, _field))
    except Exception as _ex:  # a build without one of these is itself worth knowing
        before[_field] = None

saved_options = [(o, o.value) for o in (d.fov, d.hud_scale, d.hud_bounds, u.enabled)]
real_get_pc = mods_base.get_pc
real_logging = d.logging
ultrawide_hook_was_on = u.fix_menu_scaling.get_active_count()
display_hook_is_on = d.on_character_live.get_active_count()
menu_reapply_hook_is_on = d.on_menu_reapply.get_active_count()

# The seven definitions BL2-ULTRAWIDE.md:88-94 measured at SM_NoBorder on disk, plus the
# scope, which is at SM_NoBorder too and is deliberately left there.
SEVEN = [
    "UI_Frontend_Legal.Frontend_Legal_Def",
    "UI_GearboxAccount.GearboxAccount_DEF",
    "UI_OnlineMessage.OnlineMessage_Definition",
    "UI_TextChat.TextChat_DEF",
    "UI_Lobby_LoadCharacter.LoadCharacter_DEF",
    "UI_Lobby_ConfirmCharacter.ConfirmCharacter_DEF",
    "UI_HUD_EchoVersion.EchoVersion_DEF",
]
SCOPES = "UI_Scopes.Scopes_Definition"
SM_NO_SCALE, SM_SHOW_ALL, SM_NO_BORDER = 0, 1, 3


class Log:
    """Stands in for unrealsdk.logging inside display.py and remembers what it was told."""

    def __init__(self):
        self.errors = []
        self.infos = []

    def error(self, message):
        self.errors.append(str(message))

    def info(self, message):
        self.infos.append(str(message))

    def warning(self, message):
        pass

    def dev_warning(self, message):
        pass

    def misc(self, message):
        pass


def a_stranger():
    """A live object carrying none of the six fields display.py writes."""
    return [o for o in unrealsdk.find_all("WorldInfo") if not o.Name.startswith("Default__")][-1]


def definition(path):
    try:
        return unrealsdk.find_object("GFxMovieDefinition", path)
    except Exception:
        return None


def scale_mode(obj):
    try:
        return int(obj.ScaleMode)
    except Exception:
        return None


def profile_settings():
    """The live profile object, by whichever of the two routes works."""
    try:
        return P.GetWillowGlobals().GetPlayerProfileManager().GetCurrentProfileSettings(), "globals"
    except Exception as ex:
        first = repr(ex)
    try:
        found = [
            o for o in unrealsdk.find_all("WillowProfileSettings")
            if not o.Name.startswith("Default__")
        ]
        return found[-1], "find_all"
    except Exception as ex:
        return None, f"{first} / {ex!r}"


def profile_number(prof, setting_id):
    """
    One profile setting's value, or None.

    The accessor is not resolved anywhere in this repo, so both plausible ones are tried
    and whichever answers wins. Out parameters come back in a tuple after the return value.
    """
    for name in ("GetProfileSettingValueFloat", "GetProfileSettingValueInt"):
        try:
            got = getattr(prof, name)(setting_id)
        except Exception:
            continue
        if isinstance(got, tuple):
            if got and got[0]:
                return float(got[1]), name
        elif got is not None:
            return float(got), name
    return None, "no accessor answered"


def skip(name, reason):
    """
    Print an honest [SKIP] line. Deliberately does not touch RESULTS, so it counts as neither
    pass nor fail.

    Some things this file cannot know from wherever it happens to run: whether a menu has been
    opened yet this session, whether a package is even loaded, whether a guessed accessor name
    answers at all. Failing loudly for those turns an ordinary difference in circumstances into
    a false alarm; deleting the check would throw away the one honest thing it could still say.
    This says that instead, and names what would actually settle it.
    """
    print(f"[SKIP] {name}   {reason}")


try:
    # --- field of view ------------------------------------------------------------------

    d.fov.value = 100
    check(
        "the chosen field of view lands on all three of FOVAngle, DesiredFOV and DefaultFOV",
        (float(P.FOVAngle), float(P.DesiredFOV), float(P.DefaultFOV)) == (100.0, 100.0, 100.0),
        f"FOVAngle {P.FOVAngle}, DesiredFOV {P.DesiredFOV}, DefaultFOV {P.DefaultFOV}",
    )

    # display.py:118 writes the new value onto the option by hand because mods_base calls
    # on_change_anytime BEFORE storing it (options.py:144-155). Take that line out and this
    # applies the value the slider held before the move - which is what this catches.
    d.fov.value = 0
    P.DefaultFOV = 70.0
    d.fov.value = 90
    check(
        "moving the slider applies the number it was moved to, not the one from before the move",
        float(P.DefaultFOV) == 90.0,
        f"DefaultFOV {P.DefaultFOV} after moving the slider from 0 to 90 (70 = the pre-move value)",
    )

    # The slider HAS to reach 0, because 0 is what "leave the game's own setting alone" means -
    # so a 60 floor on the slider itself is impossible. What can be true, and now is, is that a
    # number between 1 and 59 is raised to 60 rather than written: a field of view of 5 is a
    # telescope and nobody sets one on purpose.
    check(
        "the slider still reaches 0, which is how you tell it to change nothing",
        float(d.fov.min_value) == 0.0,
        f"min {d.fov.min_value}, max {d.fov.max_value}",
    )

    d.fov.value = 5
    check(
        "a field of view of 5 - a telescope - is refused rather than written to the controller",
        float(P.DefaultFOV) >= 60.0,
        f"DefaultFOV {P.DefaultFOV} after asking for 5; anything under 60 is raised to 60",
    )

    d.fov.value = 100
    d.fov.value = 0
    check(
        "setting field of view back to 0 hands the game's own value back",
        float(P.DefaultFOV) != 100.0 and float(P.DefaultFOV) > 0,
        f"DefaultFOV {P.DefaultFOV} after 100 then 0 - the number the game had before anything "
        f"was written is remembered on the first write and handed back here",
    )

    # --- HUD ----------------------------------------------------------------------------

    # HUDScaleE, not HUDScaleX/Y, and the game's own menu settles it: WillowMenu.int calls
    # HUDScaleE "HUD SCALE - change the size of all HUD elements" and calls X and Y the
    # horizontal and vertical BOUNDS. This check named the wrong pair, from back when the two
    # sliders were wired the wrong way round, and kept failing for the fix.
    d.hud_scale.value = 250
    check(
        "the HUD size percentage lands on HUDScaleE as a fraction",
        abs(float(P.HUDScaleE) - 2.5) < 1e-4,
        f"HUDScaleE {P.HUDScaleE} (bounds are X {P.HUDScaleX}, Y {P.HUDScaleY})",
    )
    # Whether that MEANS a bigger HUD is a different question, and the game's own menu text
    # says it does not: WillowMenu.int:1515-1520 calls HUDScaleX "HUD H. BOUNDS - where HUD
    # elements live on your screen" and HUDScaleE "HUD SCALE - the size of all HUD elements".
    # That comparison is checked offline in display-and-ultrawide-files.py, and the two
    # screenshots that would settle it on screen are in the -needs-travel file.

    cdo = unrealsdk.find_class("WillowPlayerController").ClassDefaultObject
    # Measured 2026-08-20: the class default carries 1.0, not the 0.90 this used to expect.
    # It does not matter what the number is - what matters is that the pack leaves it alone
    # when the slider is at 0, which is what this now checks.
    _stock_e = float(cdo.HUDScaleE)
    _was_scale = d.hud_scale.value
    d.hud_scale.value = 0
    P.HUDScaleE = _stock_e
    d._apply()
    check(
        "leaving the HUD size slider at 0 really does change nothing",
        abs(float(P.HUDScaleE) - _stock_e) < 1e-6,
        f"the game ships {_stock_e}; with the slider at 0 the controller reads {P.HUDScaleE}",
    )
    d.hud_scale.value = _was_scale

    # --- re-applied on every spawn ------------------------------------------------------

    check(
        "the spawn hook that re-applies both settings is installed",
        display_hook_is_on == 1,
        f"{display_hook_is_on} of {len(d.on_character_live.hook_funcs)} active",
    )

    d.fov.value = 100
    d.hud_bounds.value = 200
    P.DefaultFOV = 70.0
    P.HUDScaleE = 0.5
    d.on_character_live(P, None, None, None)
    check(
        "a character coming alive puts the chosen field of view back",
        float(P.DefaultFOV) == 100.0,
        f"DefaultFOV {P.DefaultFOV} after the spawn hook ran on a controller reset to 70",
    )
    # HUD SIZE writes HUDScaleE; hud_bounds writes X and Y. This used to compare HUDScaleE
    # against the BOUNDS slider, from when the two were wired the wrong way round.
    check(
        "a character coming alive puts the chosen HUD size back",
        abs(float(P.HUDScaleE) - d.hud_scale.value / 100.0) < 1e-6,
        f"HUDScaleE {P.HUDScaleE} after the spawn hook ran on a controller reset to 0.5, "
        f"with the HUD size slider at {d.hud_scale.value}",
    )
    # Whether that hook fires on a REAL spawn rather than only when called by hand is the
    # -needs-travel file's first job.

    # --- the menu-open hook that defends against the profile pushing its own number back ---

    check(
        "the menu-open hook that re-asserts the HUD numbers is installed",
        menu_reapply_hook_is_on == 1,
        f"{menu_reapply_hook_is_on} of {len(d.on_menu_reapply.hook_funcs)} active",
    )

    d.hud_bounds.value = 200
    P.HUDScaleX = 0.85  # a stand-in for whatever the options screen's own saved number is
    d.on_menu_reapply(P, None, None, None)
    check(
        "opening any menu puts the chosen HUD bounds back, defending against a profile push",
        abs(float(P.HUDScaleX) - 2.0) < 1e-6,
        f"HUDScaleX {P.HUDScaleX} after simulating a menu opening while the controller had "
        f"been knocked to 0.85 (a stand-in for whatever the saved profile carries)",
    )

    # --- the pause menu's own numbers ---------------------------------------------------

    # hud_bounds, not hud_scale - profile setting 141 is HUD H. BOUNDS, which is HUDScaleX, which
    # is what hud_bounds writes. This used to move hud_scale (HUDScaleE) and then read the BOUNDS
    # setting, so it was checking a property it had never touched - the same wrong-pair mistake
    # the two checks above this one were already fixed for, back when the sliders were renamed.
    d.hud_bounds.value = 250
    prof, how = profile_settings()
    bounds, accessor = (None, "no profile object") if prof is None else profile_number(prof, 141)
    if bounds is None:
        skip(
            "the pack's HUD number never reaches the saved profile, so the pause menu shows its own",
            f"profile setting 141 could not be read via either accessor tried ({how}) - that "
            f"proves neither agreement nor divergence, only that GetProfileSettingValueFloat/Int "
            f"are not how this profile exposes it. display.py's on_menu_reapply hook is the "
            f"mitigation regardless of whether this can ever be read: it re-asserts the "
            f"controller value on every menu open rather than trying to write the profile",
        )
    else:
        check(
            "the pack's HUD number never reaches the saved profile, so the pause menu shows its own",
            abs(bounds - 250.0) > 0.5 and abs(bounds - 2.5) > 0.005,
            f"profile setting 141 (HUD H. BOUNDS) reads {bounds} via {accessor} ({how}), while the "
            f"controller carries {P.HUDScaleX} - so the menu shows one number and the game uses "
            f"another",
        )

    # --- a write that fails ---------------------------------------------------------------

    d.fov.value = 100
    stranger = a_stranger()
    d.logging = Log()
    d._apply_to(stranger)
    errors = list(d.logging.errors)
    check(
        "a field write that cannot land is reported, one line per field",
        len(errors) == 6,
        f"{len(errors)} error lines from six impossible writes on {stranger.Name}: {errors[:2]}",
    )

    d.logging = Log()
    mods_base.get_pc = lambda **kw: stranger
    d._apply()
    failed, announced = len(d.logging.errors), list(d.logging.infos)
    mods_base.get_pc = real_get_pc
    d.logging = real_logging
    check(
        "the summary line stays quiet when every single write failed",
        failed > 0 and not announced,
        f"{failed} writes failed and it still logged {announced}"
        + (" - no write failed at all, so this proved nothing" if not failed else ""),
    )

    # --- a callback that throws -----------------------------------------------------------
    # Last of the display checks on purpose: the guard it leaks silences every later
    # `option.value = ...` in this file if it does leak.

    def no_controller(**kw):
        raise RuntimeError("GamePlayers is empty")

    mods_base.get_pc = no_controller
    raised = "nothing"
    try:
        d.fov.value = 77
    except Exception as ex:  # noqa: BLE001 - catching it IS the check
        raised = repr(ex)
    mods_base.get_pc = real_get_pc
    leaked = hasattr(d.fov, "_on_change_recursion_guard")
    # REWRITTEN 2026-08-20. This demanded that the callback RAISE, which was the bug: mods_base
    # deletes its re-entrancy flag with no try/finally (options.py:153), so an exception on the
    # way out leaves the flag set and every later slider move is silently swallowed. The fix was
    # to stop the exception escaping in the first place, which makes "raised != nothing" the
    # wrong thing to want. What has to hold is that the flag is not left behind either way.
    check(
        "a slider whose callback fails leaves nothing behind, so the slider still works after",
        not leaked,
        f"the callback raised {raised}; mods_base's re-entrancy flag left behind: {leaked}",
    )
    d.fov.value = 0
    d._apply()
    _still_works = float(P.DefaultFOV)
    d.fov.value = 95
    d._apply()
    check(
        "and the slider really does still move the picture afterwards",
        abs(float(P.DefaultFOV) - 95.0) < 1e-4,
        f"{_still_works} -> {P.DefaultFOV} after asking for 95",
    )
    d.fov.value = 0
    d._apply()
    if leaked:
        del d.fov._on_change_recursion_guard

    # --- ultra-wide: the hook itself --------------------------------------------------------

    check(
        "the menu fix is a PRE hook on GFxMovieDefinition:PostMovieStart",
        u.fix_menu_scaling.hook_funcs
        == [("GearboxFramework.GFxMovieDefinition:PostMovieStart", Type.PRE)],
        f"{u.fix_menu_scaling.hook_funcs}",
    )
    check(
        "the menu fix is installed right now",
        ultrawide_hook_was_on == 1,
        f"{ultrawide_hook_was_on} of {len(u.fix_menu_scaling.hook_funcs)} active",
    )

    # --- ultra-wide: the census -------------------------------------------------------------

    counts = {}
    still_cropped = []
    try:
        movies = list(unrealsdk.find_all("GFxMovieDefinition", False))  # subclasses included
    except Exception:
        movies = list(unrealsdk.find_all("GFxMovieDefinition"))
    for movie in movies:
        if movie.Name.startswith("Default__"):
            continue
        mode = scale_mode(movie)
        if mode is None:
            continue
        counts[mode] = counts.get(mode, 0) + 1
        if mode == SM_NO_BORDER:
            still_cropped.append(str(movie))
    print(f"scale mode census: {counts}")
    print(f"still at SM_NoBorder ({len(still_cropped)}): {still_cropped}")
    print(f"{counts.get(SM_NO_SCALE, 0)} definitions sit at SM_NoScale - whether those render as "
          f"a marooned 1280x720 island needs the screenshot in the -needs-travel file")

    modes = {name: scale_mode(definition(name)) for name in SEVEN}
    loaded = {n: m for n, m in modes.items() if m is not None}
    fixed = [n for n, m in loaded.items() if m == SM_SHOW_ALL]
    if not loaded:
        skip(
            "at least one of the seven cropped menus has actually been rewritten to SM_ShowAll",
            "none of the seven have their package loaded here - none of these screens have "
            "come up yet this session; see display-and-ultrawide-needs-travel.py, which opens "
            "some of them by hand",
        )
    else:
        check(
            "at least one of the seven cropped menus has actually been rewritten to SM_ShowAll",
            len(fixed) > 0,
            f"{len(fixed)} of {len(loaded)} loaded: {modes}",
        )

    # A definition only gets rewritten when its movie STARTS - the hook is on PostMovieStart -
    # so one still at 3 means that menu has not been opened this session, not that the hook is
    # broken. The audit's `assert [s for s in still if 'Scopes' not in s] == []` missed that,
    # and so did this check until 2026-08-20: it demanded every LOADED definition be fixed, but
    # a package can sit resident in memory without its menu ever having been opened - "loaded"
    # and "opened" are not the same fact, and only the second one the hook can be blamed for.
    still_unopened = [n for n, m in loaded.items() if m != SM_SHOW_ALL]
    if not loaded:
        skip(
            "every one of the seven that is loaded is at SM_ShowAll, i.e. every one has been opened",
            "none of the seven are loaded here - see the skip just above",
        )
    elif still_unopened:
        skip(
            "every one of the seven that is loaded is at SM_ShowAll, i.e. every one has been opened",
            f"{still_unopened} still read SM_NoBorder here, which looks identical to the hook "
            f"missing them - only opening each one tells the two apart. "
            f"display-and-ultrawide-needs-travel.py opens the pause menu and character screen; "
            f"the rest (SHiFT sign-in, connection lost, text chat, ECHO version) need their own "
            f"trigger to ever prove one way or the other",
        )
    else:
        check(
            "every one of the seven that is loaded is at SM_ShowAll, i.e. every one has been opened",
            len(fixed) == len(loaded),
            f"loaded {len(loaded)}, rewritten {len(fixed)}: {modes}",
        )

    legal_mode = modes["UI_Frontend_Legal.Frontend_Legal_Def"]
    if legal_mode is None:
        skip(
            "the boot legal screen was fixed, so the hook was in place before the game drew it",
            "Frontend_Legal_Def's package is not loaded here - it exists only at the boot / "
            "legal screen, gone by the time a character is loaded and this file can run. "
            "Neither this file nor the -needs-travel twin visits it; proving this one needs a "
            "run started at boot itself",
        )
    else:
        check(
            "the boot legal screen was fixed, so the hook was in place before the game drew it",
            legal_mode == SM_SHOW_ALL,
            f"Frontend_Legal_Def ScaleMode {legal_mode}",
        )

    scopes = definition(SCOPES)
    check(
        "the scope is left alone, so it still fills the screen",
        scale_mode(scopes) == SM_NO_BORDER,
        f"{SCOPES} ScaleMode {scale_mode(scopes)} (None = not loaded)",
    )
    check(
        "the scope's full name really does contain 'Scopes', which is how the hook spots it",
        scopes is not None and "Scopes" in str(scopes),
        f"str() of it is {str(scopes)!r}",
    )

    # --- ultra-wide: no way back ------------------------------------------------------------

    if fixed:
        witness = definition(fixed[0])
        # enabled.value, not fix_menu_scaling.disable(). Disabling the raw hook is not how a
        # player ever turns this feature off - there is one Second Wind mod and one flat hook
        # list (bl2_modern/__init__.py:24), so the only lever a player has for THIS feature is
        # its own BoolOption. Toggling the option is what actually runs _changed -> _put_back();
        # toggling the hook bypasses that machinery entirely, which is why this used to read
        # "nothing records the old value" - it was never asking the code that records it.
        u.enabled.value = False
        after_off = scale_mode(witness)
        u.enabled.value = True
        check(
            "turning the menu fix off puts the definitions back the way they were",
            after_off == SM_NO_BORDER,
            f"{fixed[0]} reads {after_off} after enabled.value was set to False (the feature's "
            f"real off-switch) - "
            f"{'restored' if after_off == SM_NO_BORDER else 'still rewritten: _put_back did not reach it'}",
        )
    else:
        check(
            "turning the menu fix off puts the definitions back the way they were",
            False,
            "no definition had been rewritten yet, so there was nothing to turn back",
        )

    # The audit calls the unguarded `obj.ScaleMode` read a bug. Every GFxMovieDefinition
    # subclass inherits the property, so the only object that can make it raise is one that is
    # not a movie definition at all. This shows what that costs when it happens.
    hurt = "nothing"
    try:
        u.fix_menu_scaling(stranger, None, None, None)
    except Exception as ex:  # noqa: BLE001 - catching it IS the check
        hurt = repr(ex)
    check(
        "the menu hook survives being handed an object with no ScaleMode",
        hurt == "nothing",
        f"handed {stranger.Name}, an object with no ScaleMode, it raised {hurt}",
    )

finally:
    d.logging = real_logging
    mods_base.get_pc = real_get_pc
    for option, _old in saved_options:
        if hasattr(option, "_on_change_recursion_guard"):
            del option._on_change_recursion_guard
    for option, old in saved_options:
        option.value = old
    for field_name, old in before.items():
        if old is not None:
            try:
                setattr(P, field_name, old)
            except Exception as ex:  # noqa: BLE001
                print(f"could not put {field_name} back to {old}: {ex!r}")
    if ultrawide_hook_was_on:
        u.fix_menu_scaling.enable()
    else:
        u.fix_menu_scaling.disable()

    check(
        "every value this test moved is back where it started",
        all(
            before[f] is None or abs(float(getattr(P, f)) - before[f]) < 1e-6 for f in FIELDS
        )
        and [o.value for o, _ in saved_options] == [v for _, v in saved_options]
        and u.fix_menu_scaling.get_active_count() == ultrawide_hook_was_on,
        f"controller {[getattr(P, f) for f in FIELDS]} vs {[before[f] for f in FIELDS]}, "
        f"options {[o.value for o, _ in saved_options]}, "
        f"menu hook active {u.fix_menu_scaling.get_active_count()}",
    )

summary()
