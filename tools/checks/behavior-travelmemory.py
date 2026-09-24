# Remember where you have been - behavior checks for features/travelmemory.py
# Run: bash bl2-mcp/tools/ask.sh bl2-mcp/tools/checks/behavior-travelmemory.py
#
# EVERYTHING HERE RUNS AGAINST THE REAL RUNNING GAME AND THE REAL TRAVEL MENU. There is no fake
# player controller and no fake station, deliberately: the whole bug this feature exists for was
# that a plausible-looking list read back correctly while the actual menu offered one place. A
# check that reads the same list back would have passed on the broken day too.
#
# The travel menu is read WITHOUT opening any menu, by building a copy of the menu's own movie
# object and asking it to fill its location list - FastTravelStationGFxMovie.BuildLocationData.
# Nothing appears on screen and nothing pauses.
#
# THE ONE DESTRUCTIVE THING THIS FILE DOES, and why it is safe: it calls the register function
# with bFromLoad=False once, on purpose, to prove that flag really is the load-bearing one. That
# call WIPES the registrations. The very next thing the file does is call restore() to put them
# back, and the final check confirms the menu holds at least what it held at the start.
reset()

import unrealsdk

from bl2_modern import core
from bl2_modern.features import travelmemory as TM


def menu_offers():
    """Exactly what the fast travel menu would list, without opening it."""
    p = pc()
    movie = unrealsdk.construct_object("FastTravelStationGFxMovie", p)
    movie.WPCOwner = p
    movie.BuildLocationData()
    return [d.Name for d in movie.LocationStationDefinitions if d]


# The hub stations of each add-on. The game offers these from the start through a different
# path (BuildDLCMapLocations), so they are not evidence of anything this feature did.
DLC_HUBS = {
    "SanctuaryIntro", "Docks", "Underground", "IrisCrater", "OasisTown",
    "Hunger", "Xmas", "PumpkinPatch", "EasterTravel", "Vday", "TestingZone",
}


def main_game(offered):
    return [n for n in offered if n not in DLC_HUBS]


p = pc()
was = TM.enabled.value

try:
    # --- how the feature is wired in ---------------------------------------------------------

    feature = next((f for f in core.all_features() if f.name == "Remember where you have been"), None)
    check(
        "the feature loaded",
        feature is not None and feature.failed is None,
        feature.failed if feature else "no feature by that name",
    )
    check(
        "its switch is carried to the menu",
        feature is not None and any(o is TM.enabled for o in feature.options),
        f"feature.options has {len(feature.options) if feature else 0} entries",
    )
    check(
        "it listens for map arrivals",
        feature is not None and feature.on_arrival is TM.on_arrival,
        getattr(feature, "on_arrival", None),
    )

    # --- the flag that wipes instead of adding -----------------------------------------------

    check(
        "the register call is made with the flag that ADDS, never the one that does nothing",
        TM.FROM_LOAD is True,
        f"FROM_LOAD is {TM.FROM_LOAD!r} - False adds nothing, and was once seen to empty the menu",
    )

    # --- it actually puts places back ---------------------------------------------------------

    TM.enabled.value = True
    restored = TM.restore()
    baseline = menu_offers()
    saved_names = [str(n) for n in p.ActivatedTeleportersList]
    check(
        "it re-registers the places the save lists",
        restored > 0,
        f"re-registered {restored} of {len(saved_names)} names in the save",
    )
    check(
        "and every one of them is a place the save already listed - it invents nowhere",
        all(n in saved_names for n in main_game(baseline)),
        f"menu has {main_game(baseline)}, save lists {len(saved_names)} names",
    )
    check(
        "the travel menu now offers more than one main-game place",
        len(main_game(baseline)) > 1,
        f"offers {len(main_game(baseline))}: {main_game(baseline)}",
    )

    # --- running it twice must not duplicate anything -----------------------------------------

    TM.restore()
    twice = menu_offers()
    check(
        "running it again changes nothing and duplicates nothing",
        sorted(twice) == sorted(baseline) and len(twice) == len(set(twice)),
        f"{len(baseline)} entries before, {len(twice)} after, {len(set(twice))} of them distinct",
    )

    # --- the switch off means it does nothing --------------------------------------------------

    TM.enabled.value = False
    check(
        "with the switch off it registers nothing at all",
        TM.restore() == 0,
        "restore() returned a non-zero count with the switch off",
    )
    TM.enabled.value = True

    # --- the other flag adds nothing, so the feature must never use it --------------------------
    #
    # This used to assert that the wrong flag WIPES the menu, because that was seen once during
    # the investigation. It did not reproduce, so the check now asserts only what does: with the
    # wrong flag the call adds nothing at all. The one-off collapse is written up in the feature
    # file as unexplained rather than pretended into a rule.

    unregistered = next(
        (n for n in TM._stations() if n not in baseline and n not in DLC_HUBS),
        None,
    )
    if unregistered is None:
        print("[SKIP] proving the other flag adds nothing   every station is already registered")
    else:
        p.RegisterStationForPlayer(
            TM._stations()[unregistered], None, p.PlayerReplicationInfo, False, False,
        )
        after_wrong_flag = menu_offers()
        check(
            "with the other flag the call adds nothing, which is why the feature never uses it",
            unregistered not in after_wrong_flag,
            f"{unregistered} appeared in the menu after a call that should do nothing",
        )
        TM.restore()
        repaired = menu_offers()
        check(
            "and the feature still holds everything it held before that call",
            set(main_game(baseline)).issubset(set(main_game(repaired))),
            f"lost {sorted(set(main_game(baseline)) - set(main_game(repaired)))}",
        )

    # --- a name in the save with no such station must be skipped, not raise ---------------------

    real_list = list(p.ActivatedTeleportersList)
    p.ActivatedTeleportersList = [*real_list, "ThisStationDoesNotExist"]
    try:
        survived = TM.restore()
        raised = None
    except Exception as ex:
        survived, raised = -1, repr(ex)
    finally:
        p.ActivatedTeleportersList = real_list
    check(
        "a name in the save that is not a real station is skipped quietly",
        raised is None and survived > 0,
        raised or f"restore() returned {survived}",
    )
    check(
        "and the save list is back exactly as it was",
        list(p.ActivatedTeleportersList) == real_list,
        f"{len(list(p.ActivatedTeleportersList))} names, expected {len(real_list)}",
    )

finally:
    TM.enabled.value = was
    TM.restore()
    check(
        "the switch is back where it started and the menu is intact",
        TM.enabled.value == was and len(main_game(menu_offers())) >= 1,
        f"switch={TM.enabled.value!r}, menu={main_game(menu_offers())}",
    )

summary()
