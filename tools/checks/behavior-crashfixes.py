# Crash fixes - checks for features/crashfixes.py
# Run: bash bl2-mcp/tools/ask.sh bl2-mcp/tools/checks/behavior-crashfixes.py
#
# RAID CRASH PREVENTION touches real, shared WillowPickup actors in the live world, so the parts
# that would actually mark or warn about real ground loot are exercised here with STAND-IN
# pickups - nothing currently on the ground when this runs is touched. The one real-game part is
# confirming the object paths this feature depends on (GD_Globals.General.Globals,
# RarityLevelColors, WillowPickup) actually resolve, which is read-only, plus ONE run of the real
# hook over the real find_all return type - guarded below so it only happens while the real ground
# count is far under the feature's own lowest threshold, i.e. while it can only look and not mark.
#
# Nothing here reassigns unrealsdk.find_all. That attribute is read by the whole live game, and a
# check that aborts halfway through would leave the session holding a stub for the rest of its
# life. The feature owns a _find_all of its own for exactly this, and that is what gets stubbed.
reset()

import unrealsdk
from bl2_modern.features import crashfixes as C

p = pc()

# --- everything we are about to change, so the finally can put it back --------------------

real_find_all = C._find_all
real_is_host = C._is_host
real_lifespan_types = C._lifespan_types
real_show_hud_message = C.show_hud_message

was = {
    "raid": C.raid_crash_prevention.value,
    "shown_short": C._shown_short,
    "shown_long": C._shown_long,
    "short_type": C._short_lifespan_type,
    "long_type": C._long_lifespan_type,
}

check(
    "the inert placeholder switch is gone - nothing in the menu that changes nothing",
    not hasattr(C, "skill_effect_crash_fix"),
    "crashfixes still exposes %r"
    % ([n for n in dir(C) if "skill" in n.lower() or "effect" in n.lower()],),
)

# --- stand-ins ---------------------------------------------------------------------------


class _Pickup(object):
    def __init__(self, mission_item, lifespan_type):
        self.bIsMissionItem = mission_item
        self.LifeSpanType = lifespan_type
        self.LifeSpan = 999.0  # a made-up "still alive" value, not read from any real pickup


class _Angry(object):
    """A pickup that raises the moment anything reads it - one bad pickup must not stop the rest."""

    @property
    def bIsMissionItem(self):
        raise RuntimeError("this pickup has no data")


SHORT_TYPE = "stand-in-short"
LONG_TYPE = "stand-in-long"
OTHER_TYPE = "stand-in-other"

hud_said = []


def _fake_hud(title, text, seconds=4):
    hud_said.append((title, text))


def _use(pickup_list):
    """
    Make the feature's own find_all answer with this exact list - as a GENERATOR.

    iter() is the point of this line, not an accident. The real unrealsdk.find_all returns a
    generator, len() on which raises TypeError, and the first draft of this feature called len()
    on it directly inside the loot-spawn hook - so every single loot drop in the game would have
    thrown out of the hook body. Handing the feature a plain list here is exactly what hid that.
    A fresh iterator per call, because a generator only walks once.
    """
    C._find_all = lambda cls: iter(pickup_list) if cls == "WillowPickup" else real_find_all(cls)


try:
    # --- what the feature rests on, against the real game --------------------------------
    try:
        globals_def = unrealsdk.find_object("GlobalsDefinition", C.GLOBALS_PATH)
        globals_ok = globals_def is not None
    except Exception as ex:
        globals_def = None
        globals_ok = False
        print("could not read %s: %r" % (C.GLOBALS_PATH, ex))

    if not globals_ok:
        print(
            "[SKIP] %s resolves, so Raid Crash Prevention has real thresholds to compare "
            "against - not found in this world; flag for needs_ingame_probes before this switch "
            "ships" % (C.GLOBALS_PATH,)
        )
    else:
        check(
            "GD_Globals.General.Globals resolves and its RarityLevelColors reach index 3",
            globals_def.RarityLevelColors is not None and len(globals_def.RarityLevelColors) > 3,
            "RarityLevelColors has %r entries"
            % (len(globals_def.RarityLevelColors) if globals_def.RarityLevelColors else 0,),
        )
        try:
            short_type, long_type = C._lifespan_types()
            check(
                "the feature's own lookup finds both DropLifeSpanType values from that object",
                short_type is not None and long_type is not None,
                "got %r and %r" % (short_type, long_type),
            )
        except Exception as ex:
            print("[FAIL] _lifespan_types() raised: %r" % (ex,))

    real_count = None
    try:
        real_count = len(list(real_find_all("WillowPickup")))
    except Exception as ex:
        print("could not count find_all('WillowPickup'): %r" % (ex,))
    check(
        "the game answers find_all('WillowPickup') with something the feature can count",
        real_count is not None,
        "find_all raised" if real_count is None else "%r pickups on the ground" % (real_count,),
    )

    # Not a check, because a future SDK returning a list instead is not a failure - but it is the
    # exact shape of the bug this file is here to catch, so it gets said out loud either way.
    try:
        len(real_find_all("WillowPickup"))
        print("note: len() straight on find_all's return works in this build")
    except Exception as ex:
        print(
            "note: len() straight on find_all's return raises %s - which is why the feature "
            "list()s it first, and why the stand-ins below are handed over as generators"
            % (type(ex).__name__,)
        )

    check(
        "_is_host() runs and returns a plain bool without a live world raising through it",
        isinstance(real_is_host(), bool),
        "returned %r" % (real_is_host(),),
    )

    # --- ONE run of the real hook, over the real find_all, with nothing stubbed but the host
    # gate - the only way to prove the hook body survives the type the game actually hands it.
    # Guarded on the real ground count being far under the feature's own lowest threshold, so
    # this run can only look: at that count the feature marks nothing and warns about nothing.
    if real_count is not None and real_count < C.WARN_SHORTLIVED:
        C._is_host = lambda: True
        C.raid_crash_prevention.value = True
        # Both flags parked at True first. The feature only clears them AFTER it has successfully
        # counted, so their state afterwards is the observable proof that the count really
        # happened - "it did not raise" would not be, since the feature catches its own count
        # failures and returns quietly.
        C._shown_short = True
        C._shown_long = True
        try:
            C.on_spawn_items(None, None, None, None)
            real_hook_ex = None
        except Exception as ex:
            real_hook_ex = ex
        C._is_host = real_is_host
        check(
            "the real loot-spawn hook counts the real find_all result and carries on",
            real_hook_ex is None and C._shown_short is False and C._shown_long is False,
            "the hook raised %r - every loot drop in the game would do this" % (real_hook_ex,)
            if real_hook_ex is not None
            else "it never got past counting %r real pickups - flags left at %r/%r"
            % (real_count, C._shown_short, C._shown_long)
            if (C._shown_short or C._shown_long)
            else "counted %r real pickups, well under the %r warning line, so it only looked"
            % (real_count, C.WARN_SHORTLIVED),
        )
    else:
        print(
            "[SKIP] the real hook is exercised over the real find_all result - the ground count "
            "is %r, not safely under the %r warning line" % (real_count, C.WARN_SHORTLIVED)
        )

    # --- the logic itself, with stand-in pickups so nothing real on the ground is touched ---
    C.show_hud_message = _fake_hud
    C._lifespan_types = lambda: (SHORT_TYPE, LONG_TYPE)
    C._is_host = lambda: True
    C.raid_crash_prevention.value = True
    C._shown_short = False
    C._shown_long = False

    # Well under every threshold: nothing warned, nothing marked.
    hud_said[:] = []
    low = [_Pickup(False, SHORT_TYPE) for _ in range(5)]
    _use(low)
    C.on_spawn_items(None, None, None, None)
    check(
        "well under every threshold, nothing is warned and nothing is marked for expiry",
        hud_said == [] and all(x.LifeSpan == 999.0 for x in low),
        "hud said %r, lifespans %r" % (hud_said, [x.LifeSpan for x in low]),
    )

    # Crossing the short warning line: warned once, not twice, and nothing deleted yet.
    hud_said[:] = []
    mid = [_Pickup(False, SHORT_TYPE) for _ in range(C.WARN_SHORTLIVED)]
    _use(mid)
    C.on_spawn_items(None, None, None, None)
    C.on_spawn_items(None, None, None, None)
    check(
        "crossing the short warning line shows the warning exactly once, not once per call",
        len(hud_said) == 1 and hud_said[0][1] == C.WARN_SHORT_TEXT,
        "hud said %r after two calls over the line" % (hud_said,),
    )
    check(
        "nothing is deleted yet at just the warning line, below the deletion line",
        all(x.LifeSpan == 999.0 for x in mid),
        "a sample of lifespans: %r" % ([x.LifeSpan for x in mid[:5]],),
    )

    # Dropping back under the line clears the shown flag, so crossing it again warns again.
    _use(low)
    C.on_spawn_items(None, None, None, None)
    hud_said[:] = []
    _use(mid)
    C.on_spawn_items(None, None, None, None)
    check(
        "dropping back under the line and crossing it again warns a second time",
        len(hud_said) == 1,
        "hud said %r" % (hud_said,),
    )

    # Over the short deletion line: ordinary short-lived pickups marked, a mission item and a
    # differently-typed pickup among them left alone.
    high = (
        [_Pickup(False, SHORT_TYPE) for _ in range(C.DELETE_SHORTLIVED - 2)]
        + [_Pickup(True, SHORT_TYPE), _Pickup(False, OTHER_TYPE)]
    )
    _use(high)
    C.on_spawn_items(None, None, None, None)
    check(
        "over the short deletion line, ordinary short-lived pickups are marked to expire",
        all(
            x.LifeSpan == 1
            for x in high
            if not x.bIsMissionItem and x.LifeSpanType == SHORT_TYPE
        ),
        "a sample: %r" % ([x.LifeSpan for x in high if x.LifeSpanType == SHORT_TYPE][:5],),
    )
    check(
        "a mission item over the same line is never touched",
        [x for x in high if x.bIsMissionItem][0].LifeSpan == 999.0,
        "its lifespan is %r" % ([x for x in high if x.bIsMissionItem][0].LifeSpan,),
    )
    check(
        "a pickup of a different lifespan type is not deleted by the short-lived line alone",
        [x for x in high if x.LifeSpanType == OTHER_TYPE][0].LifeSpan == 999.0,
        "its lifespan is %r" % ([x for x in high if x.LifeSpanType == OTHER_TYPE][0].LifeSpan,),
    )

    # The long-lived warning and deletion path, mirroring the short one above.
    hud_said[:] = []
    C._shown_long = False
    long_high = [_Pickup(False, LONG_TYPE) for _ in range(C.DELETE_LONGLIVED - 1)] + [
        _Pickup(False, SHORT_TYPE),
    ]
    _use(long_high)
    C.on_spawn_items(None, None, None, None)
    check(
        "over the long deletion line, long-lived pickups are marked to expire too",
        all(x.LifeSpan == 1 for x in long_high if x.LifeSpanType == LONG_TYPE),
        "a sample: %r" % ([x.LifeSpan for x in long_high if x.LifeSpanType == LONG_TYPE][:5],),
    )
    check(
        "the long warning message fires too, worded for the higher-rarity drops",
        any(text == C.WARN_LONG_TEXT for _title, text in hud_said),
        "hud said %r" % (hud_said,),
    )

    # Switched off: nothing happens even well over every threshold.
    hud_said[:] = []
    off_test = [_Pickup(False, SHORT_TYPE) for _ in range(C.DELETE_LONGLIVED + 10)]
    _use(off_test)
    C.raid_crash_prevention.value = False
    C.on_spawn_items(None, None, None, None)
    check(
        "turning the feature off in the menu really stops it, however much loot is on the ground",
        hud_said == [] and all(x.LifeSpan == 999.0 for x in off_test),
        "hud said %r, a lifespan is %r" % (hud_said, off_test[0].LifeSpan),
    )
    C.raid_crash_prevention.value = True

    # A guest: nothing happens even with the switch on and the count sky-high.
    hud_said[:] = []
    guest_test = [_Pickup(False, SHORT_TYPE) for _ in range(C.DELETE_LONGLIVED + 10)]
    _use(guest_test)
    C._is_host = lambda: False
    C.on_spawn_items(None, None, None, None)
    check(
        "a guest's machine never deletes or warns, because ground loot is the host's to change",
        hud_said == [] and all(x.LifeSpan == 999.0 for x in guest_test),
        "on a guest, hud said %r, a lifespan is %r" % (hud_said, guest_test[0].LifeSpan),
    )
    C._is_host = lambda: True

    # A pickup that raises the moment it is read must not stop the well-formed ones after it.
    angry_list = [_Angry()] + [_Pickup(False, SHORT_TYPE) for _ in range(C.DELETE_SHORTLIVED)]
    _use(angry_list)
    C.on_spawn_items(None, None, None, None)
    check(
        "one pickup raising when read does not stop the well-formed ones after it",
        angry_list[-1].LifeSpan == 1,
        "the last pickup's lifespan is %r" % (angry_list[-1].LifeSpan,),
    )

    # The whole list is walked even when the count only clears the LOWER deletion line: a
    # long-lived pickup sitting in a list that is over the short line but under the long one must
    # come through untouched, and the short-lived ones around it must still be marked.
    mixed = (
        [_Pickup(False, SHORT_TYPE) for _ in range(C.DELETE_SHORTLIVED)]
        + [_Pickup(False, LONG_TYPE)]
    )
    _use(mixed)
    C.on_spawn_items(None, None, None, None)
    check(
        "between the two deletion lines, only the cheap loot is marked and the better loot is not",
        mixed[-1].LifeSpan == 999.0 and mixed[0].LifeSpan == 1,
        "the long-lived one is %r, a short-lived one is %r"
        % (mixed[-1].LifeSpan, mixed[0].LifeSpan),
    )

finally:
    C._find_all = real_find_all
    C._is_host = real_is_host
    C._lifespan_types = real_lifespan_types
    C.show_hud_message = real_show_hud_message
    C.raid_crash_prevention.value = was["raid"]
    C._shown_short = was["shown_short"]
    C._shown_long = was["shown_long"]
    C._short_lifespan_type = was["short_type"]
    C._long_lifespan_type = was["long_type"]
    print("restored every stub and every setting")

summary()
