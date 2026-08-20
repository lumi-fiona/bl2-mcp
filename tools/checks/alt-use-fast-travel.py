# Alternate use on a fast travel station - checks for features/fasttravel.py
# Run: bash bl2-mcp/tools/ask.sh bl2-mcp/tools/checks/alt-use-fast-travel.py
#
# NOTHING HERE TRAVELS ANYWHERE. Every path that would teleport goes through a stand-in player
# controller that writes down where it was asked to go and stays put. The remembered station
# list is saved and put back in the finally, so the character's own history is not disturbed.
#
# Actually pressing the key on a real station is the one thing this cannot do - see
# alt-use-fast-travel-needs-travel.py for that sequence.
reset()

import unrealsdk
from bl2_modern.features import fasttravel as F

p = pc()

was_remembered = None
try:
    was_remembered = [list(entry) for entry in (F.remembered.value or [])]
except Exception as ex:
    print("could not read the remembered stations: %r" % (ex,))

was_enabled = F.enabled.value
was_mode = F.mode.value
was_guest = F.on_guest.value
real_get_pc = F.get_pc
armed_before = F._armed_at

# The real world, borrowed so the stand-in controller can still answer "what map is this" and
# "what time is it" truthfully. Without it the map test and the arming clock would be fiction.
real_world = None
try:
    real_world = p.WorldInfo if p is not None else None
except Exception as ex:
    print("could not borrow the world: %r" % (ex,))


class _FakePC(object):
    """A controller that remembers where it was told to go, and does not go."""

    def __init__(self, world_info=None, playthrough=0, role=3):
        self.sent = []
        self.Role = role
        self.WorldInfo = world_info if world_info is not None else real_world

    def ServerTeleportPlayerToStation(self, definition):
        self.sent.append(definition)

    def GetCurrentPlaythrough(self):
        return 0


class _Movie(object):
    def __init__(self, definition):
        self.CurrentWaypointStationDef = definition


class _Args(object):
    def __init__(self, **kw):
        for key, value in kw.items():
            setattr(self, key, value)


try:
    # --- the prompt that has to appear on the station ---------------------------------------
    F.mode.value = F.TO_OBJECTIVE
    icon = F._the_icon()
    check(
        "the game's default use icon exists to be copied, so a prompt can be built at all",
        icon is not None,
        "F._the_icon() returned %r; without it the station shows nothing to press"
        % (icon,),
    )
    if icon is not None:
        check(
            "the prompt is attached to the alternate use key rather than the ordinary one",
            str(icon.Action) == "UseSecondary",
            "Action is %r" % (str(icon.Action),),
        )
        check(
            "the prompt says something a player can read",
            str(icon.Text) == "TRAVEL TO OBJECTIVE",
            "Text is %r" % (str(icon.Text),),
        )
        check(
            "asking for the prompt again gives the same object rather than building a second",
            F._the_icon() is icon,
            "a second call returned %r" % (F._the_icon(),),
        )

    # --- where you came from ------------------------------------------------------------------
    F.remembered.value = [[], [], []]
    check(
        "with nowhere remembered, there is nowhere to return to",
        F._came_from() == "",
        "returned %r" % (F._came_from(),),
    )

    F._remember("A_Station")
    check(
        "after one journey there is still nowhere to return to, because the only station "
        "remembered is the one you are standing at",
        F._came_from() == "",
        "after a single arrival it offers %r, which would spend a whole map load putting you "
        "back exactly where you already are" % (F._came_from(),),
    )

    F._remember("B_Station")
    check(
        "after two journeys, returning means going back to the one before this one",
        F._came_from() == "A_Station",
        "offers %r, expected A_Station" % (F._came_from(),),
    )

    F._remember("C_Station")
    check(
        "only the last two are kept, so the list cannot grow forever",
        F._came_from() == "B_Station" and len(F._slots()[F._playthrough()]) == 2,
        "offers %r, list is %r" % (F._came_from(), F._slots()[F._playthrough()]),
    )

    # Playthroughs do not share a history.
    here = F._playthrough()
    other = (here + 1) % 3
    slots = F._slots()
    check(
        "each playthrough keeps its own history",
        slots[other] == [],
        "playthrough %d has %r while playthrough %d has %r"
        % (other, slots[other], here, slots[here]),
    )

    # --- is the station in the map I am standing in? -------------------------------------------
    local = find_actor("FastTravelStation")
    local_def = None
    for station in local:
        try:
            found = station.TravelDefinition or station.GetTravelStationDefinition()
        except Exception:
            found = None
        if found is not None:
            local_def = found
            break

    check(
        "there is a fast travel station in this map to check the map-name test against",
        local_def is not None,
        "found %d FastTravelStation actors here. If this fails, travel somewhere with a "
        "station and run this again" % (len(local),),
    )
    if local_def is not None:
        check(
            "a station in this map is correctly recognised as being in this map",
            F._in_this_map(local_def),
            "station level name %r against map %r - if this fails, the two halves of the "
            "feature that refuse a pointless map reload are both broken"
            % (str(local_def.StationLevelName), where()),
        )
        F.mode.value = F.TO_LAST
        F.remembered.value = [[], [], []]
        F._remember(str(local_def._path_name()))
        F._remember(str(local_def._path_name()))
        check(
            "returning refuses to send you to a station in the map you are already in",
            F._where_to() == "",
            "it offered %r" % (F._where_to(),),
        )

    # --- the lock that stops the fast travel menu throwing you across the world -----------------
    F.mode.value = F.TO_OBJECTIVE
    somewhere = _FakePC()
    F.get_pc = lambda: somewhere

    far_away = None
    for definition in find_actor("FastTravelStationDefinition"):
        try:
            if not F._in_this_map(definition) and not definition.bSendOnly:
                far_away = definition
                break
        except Exception:
            continue
    check(
        "there is a station somewhere else loaded, to be a plausible mission target",
        far_away is not None,
        "checked %d station definitions" % (len(find_actor("FastTravelStationDefinition")),),
    )

    if far_away is not None:
        somewhere.sent = []
        F._armed_at = -1.0
        F.on_waypoint_shown(_Movie(far_away), None, None, None)
        check(
            "opening the fast travel menu yourself never teleports you",
            not somewhere.sent,
            "it sent you to %r without being asked to" % (somewhere.sent,),
        )

        somewhere.sent = []
        F._armed_at = F._now()
        F.on_waypoint_shown(_Movie(far_away), None, None, None)
        check(
            "when this feature did open the menu, the mission's station is travelled to",
            somewhere.sent == [far_away],
            "it sent you to %r" % (somewhere.sent,),
        )

        somewhere.sent = []
        F._armed_at = F._now() - (F.ARMED_FOR + 5.0)
        F.on_waypoint_shown(_Movie(far_away), None, None, None)
        check(
            "an arming that was never used goes stale rather than lying in wait",
            not somewhere.sent,
            "a %s second old arming still fired: %r"
            % (F.ARMED_FOR + 5.0, somewhere.sent),
        )

        somewhere.sent = []
        F._armed_at = F._now()
        F.on_waypoint_shown(_Movie(None), None, None, None)
        check(
            "a mission that marks no station leaves you looking at the map rather than raising",
            not somewhere.sent,
            "sent %r" % (somewhere.sent,),
        )

    if local_def is not None:
        somewhere.sent = []
        F._armed_at = F._now()
        F.on_waypoint_shown(_Movie(local_def), None, None, None)
        check(
            "a mission whose station is in this map does not reload the map you are in",
            not somewhere.sent,
            "sent %r" % (somewhere.sent,),
        )

    # --- what the alternate use key does, and does not, act on ----------------------------------
    class _Usable(object):
        def __init__(self, class_name):
            self.Class = type("C", (), {"Name": class_name})()
            self.used = 0

        def UsedBy(self, pawn):
            self.used += 1

    class _Presser(object):
        def __init__(self, usable, role=3):
            self.Role = role
            self.CurrentUsableObject = usable
            self.CurrentInteractionIcon = [None, type("I", (), {"IconDef": object()})()]
            self.Pawn = None
            self.sent = []

        def ServerTeleportPlayerToStation(self, definition):
            self.sent.append(definition)

    F.enabled.value = True
    F.mode.value = F.TO_OBJECTIVE

    machine = _Usable("WillowVendingMachine")
    presser = _Presser(machine)
    F._armed_at = -1.0
    F.on_alt_used(presser, None, None, None)
    check(
        "the alternate use key on a vending machine is left entirely alone, so Alt Use Vendors "
        "keeps working",
        machine.used == 0 and F._armed_at < 0,
        "the machine was used %d times and the arming is %r" % (machine.used, F._armed_at),
    )

    station = _Usable("FastTravelStation")
    presser = _Presser(station)
    F._armed_at = -1.0
    F.on_alt_used(presser, None, None, None)
    check(
        "the alternate use key on a fast travel station opens it and arms the waypoint read",
        station.used == 1 and F._armed_at >= 0,
        "used %d times, arming %r" % (station.used, F._armed_at),
    )

    F.on_guest.value = False
    guest_station = _Usable("FastTravelStation")
    guest = _Presser(guest_station, role=2)
    F._armed_at = -1.0
    F.on_alt_used(guest, None, None, None)
    check(
        "a guest's alternate use key does nothing, because the mod this copies is host only",
        guest_station.used == 0,
        "it was used %d times on a guest" % (guest_station.used,),
    )

    F.on_guest.value = True
    F._armed_at = -1.0
    F.on_alt_used(guest, None, None, None)
    check(
        "and it does something once the guest is allowed",
        guest_station.used == 1,
        "used %d times with the guest switch on" % (guest_station.used,),
    )
    F.on_guest.value = False

    F.enabled.value = False
    off_station = _Usable("FastTravelStation")
    F._armed_at = -1.0
    F.on_alt_used(_Presser(off_station), None, None, None)
    check(
        "turning the feature off really stops the key doing anything",
        off_station.used == 0,
        "used %d times with the switch off" % (off_station.used,),
    )
    F.enabled.value = True

    # --- the SetUsability trick, which must only ever fire for our own calls ---------------------
    class _Func(object):
        def __init__(self):
            self.func = None
            self.calls = 0

        def __call__(self, *a):
            self.calls += 1

    F._forcing = False
    handler = _Func()
    answer = F.on_set_usability(None, _Args(bUsable=True, UsedType=1, UsedComponent=None), None, handler)
    check(
        "the game's own reasons for locking a station off are left alone",
        answer is None and handler.calls == 0,
        "returned %r after %d calls; Yeti's original redirects every call in the session, "
        "which is the thing this narrows" % (answer, handler.calls),
    )

    # --- arriving somewhere is remembered, however you got there ----------------------------------
    F.remembered.value = [[], [], []]
    if far_away is not None:
        F.on_travelled(None, _Args(StationDefinition=far_away), None, None)
        check(
            "travelling by any means at all is written into the history",
            F._slots()[F._playthrough()] == [str(far_away._path_name())],
            "history is %r" % (F._slots()[F._playthrough()],),
        )

finally:
    F.get_pc = real_get_pc
    F.enabled.value = was_enabled
    F.mode.value = was_mode
    F.on_guest.value = was_guest
    F._armed_at = armed_before
    F._forcing = False
    if was_remembered is not None:
        F.remembered.value = was_remembered
    print("restored: mode %r, history %r" % (F.mode.value, was_remembered))

summary()
