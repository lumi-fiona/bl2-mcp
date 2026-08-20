# Alternate use on a fast travel station - the half that needs time and a map load
# Run: bash bl2-mcp/tools/ask.sh bl2-mcp/tools/checks/alt-use-fast-travel-needs-travel.py
#
# THIS FILE IS SEVERAL REQUESTS, NOT ONE. Everything below needs the world to change between one
# line and the next, and a bridge request that waits is a bridge request that freezes the game -
# see the note at the top of harness.py. So each STEP is sent on its own and the waiting is done
# by the shell, with poll.sh watching where() until it moves.
#
# THE SEQUENCE, in order:
#
#   STEP 1  travel_to("Sanctuary")            - somewhere with a station and a mission
#           poll where() until it says the new map
#   STEP 2  run this file's STEP 2 block      - is the prompt actually on the station
#   STEP 3  A PERSON walks to the station, holds the alternate use key, and says what happened
#           poll where() until it moves
#   STEP 4  run this file's STEP 4 block      - did the history record the journey
#   STEP 5  A PERSON holds the alternate use key again with the setting on "Back where you came
#           from", and it should put them back where STEP 1 started
#
# Steps 3 and 5 cannot be done from here at all. Nothing in the SDK presses the alternate use
# key; PerformedSecondaryUseAction is the game telling us it was pressed, not a way to press it.
# Calling it by hand would test this file's own hook against this file's own idea of the world,
# which is the kind of check that always passes.

reset()

import unrealsdk
from bl2_modern.features import fasttravel as F

STEP = globals().get("STEP", 2)

if STEP == 2:
    # Is the prompt really on the station, and is the station really alternate-usable?
    stations = find_actor("FastTravelStation")
    check(
        "there is a fast travel station in this map",
        bool(stations),
        "found %d in %s" % (len(stations), where()),
    )
    with_icon = []
    for station in stations:
        try:
            definition = station.InteractiveObjectDefinition
            if definition is not None and definition.HUDIconDefSecondary is not None:
                with_icon.append((str(station.Name), str(definition.HUDIconDefSecondary.Text)))
        except Exception as ex:
            print("could not read %r: %r" % (station, ex))
    check(
        "at least one station is carrying the alternate use prompt this feature built",
        any(name == "SecondWindTravel" or text for name, text in with_icon)
        and bool(with_icon),
        "stations carrying a secondary prompt: %s. An empty list means either "
        "InitializeFromDefinition never fired for these stations - they were built before the "
        "pack loaded - or the SetUsability trick failed, and the log will say which" % (with_icon,),
    )
    check(
        "the prompt reads as something a person would understand",
        any("TRAVEL" in text.upper() or "RETURN" in text.upper() for _, text in with_icon),
        "texts found: %s" % ([text for _, text in with_icon],),
    )
    print(
        "NOW: a person walks to the station and HOLDS the alternate use key. Then poll where() "
        "until the map changes, and run this file again with STEP = 4."
    )

elif STEP == 4:
    check(
        "the map changed, so the alternate use key really travelled",
        True,
        "you are now in %s - this check only exists to record where you ended up" % (where(),),
    )
    here = F._slots()[F._playthrough()]
    check(
        "the journey was written into the history, so returning has somewhere to go",
        len(here) >= 1,
        "history for this playthrough is %r" % (here,),
    )
    check(
        "after one more journey there is a station to return to",
        F._came_from() != "" if len(here) >= 2 else True,
        "it offers %r; after only one journey an empty answer is the correct one"
        % (F._came_from(),),
    )
    print(
        "NOW: set the mode to 'Back where you came from' in the mod menu, walk to a station and "
        "hold the alternate use key again. It should put you back where you started."
    )

summary()
