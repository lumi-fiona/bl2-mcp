# Replayable content - checks for features/replayables.py
# Run: bash bl2-mcp/tools/ask.sh bl2-mcp/tools/checks/behavior-replayables.py
#
# The echo dialogue group and the five missions are shared, persistent game data, so the parts
# that would actually rewrite it are exercised here with STAND-IN objects, not the real ones -
# nothing about a real character's echoes or missions is touched by those parts. The two
# exceptions are deliberate, tiny, and reversible: a real dialogue tag's Priority and a real
# mission's bRepeatable are each read and written back to the SAME value they already held, to
# prove the write mechanism itself works on the real object types, without changing anything.
#
# Nothing here reassigns unrealsdk.find_object. That attribute is read by the whole live game, and
# a check that aborts halfway through would leave the session holding a stub for the rest of its
# life. The feature owns a _find of its own for exactly this, and that is what gets stubbed.
#
# Note on the option flips below: assigning an option's value fires the feature's own on_change
# callback EVERY time, even when the value assigned is the one it already held. So each flip here
# is the real user path - the feature has already applied itself by the time the line returns -
# and the explicit _apply_*() calls that follow some of them are second passes, not the first one.
reset()

import unrealsdk
from bl2_modern.features import replayables as R

p = pc()

look_up = unrealsdk.find_object  # read-only real lookups, for the real-game section at the end

# --- everything we are about to change, so the finally can put it back --------------------

real_find = R._find

was = {
    "reusable": R.reusable_echoes.value,
    "missions": R.repeatable_missions.value,
    "echo_objects": dict(R._echo_objects),
    "echo_tried": R._echo_tried,
    "dialog_group_obj": R._dialog_group_obj,
    "saved_talk_data": list(R._saved_talk_data),
    "original_priority": dict(R._original_priority),
    "original_event_tag": R._original_event_tag,
    "echoes_written": R._echoes_written,
    "mission_first_seen": dict(R._mission_first_seen),
    "missions_written": R._missions_written,
}

# --- stand-ins ---------------------------------------------------------------------------


class _TalkData(object):
    def __init__(self, ak_event):
        self.TalkAkEvent = ak_event


class _TalkAct(object):
    def __init__(self, ak_event, delay):
        self.TalkData = [_TalkData(ak_event)]
        self.OutputDelay = delay


class _DialogGroup(object):
    def __init__(self, acts, event_tag):
        self.TalkActs = acts
        self.EventTags = [event_tag]


class _Tag(object):
    def __init__(self, priority):
        self.Priority = priority


class _Priority(object):
    pass


class _Item(object):
    """A stand-in for whatever `caller` is in the ConsumeItem hook."""

    def __init__(self, definition, raises=False):
        self._definition = definition
        self._raises = raises

    def GetInventoryDefinition(self):
        if self._raises:
            raise RuntimeError("no definition available")
        return self._definition


class _Mission(object):
    def __init__(self, repeatable):
        self.bRepeatable = repeatable


VANILLA_EVENT_TAG = "the-groups-own-original-event-tag"
VANILLA_PRIORITY = "vanilla_priority_marker"

# MEASURED in the live game 2026-08-20, and the whole point of the mission checks below: the three
# slaughter missions are ALREADY repeatable before this pack writes anything - the bundled
# Community Patch sets them. Only the two DLC finales are False. So "off" must put THESE values
# back, not a blanket False.
FIRST_SEEN = {
    "GD_Z2_CreatureSlaughter.M_CreatureSlaughter_5": True,
    "GD_Z1_BanditSlaughter.M_BanditSlaughter5": True,
    "GD_Z3_RobotSlaughter.M_RobotSlaughter_5": True,
    "GD_Sage_Ep5.M_Sage_Mission05": False,
    "GD_IrisEpisode06.M_IrisEp6_LongWayToTheTop": False,
}

group = _DialogGroup(
    [_TalkAct("orig_ak_0", 0.1), _TalkAct("orig_ak_1", 0.2), _TalkAct("orig_ak_2", 0.3)],
    VANILLA_EVENT_TAG,
)
stand_in_tags = {path: _Tag(VANILLA_PRIORITY) for path in R.DIALOG_TAGS}
stand_in_priority = _Priority()
stand_in_vending_tag = "the-vending-machine-event-tag"
stand_in_missions = {path: _Mission(FIRST_SEEN[path]) for path, _label in R.MISSIONS}

lookups = []


def _fake_find(cls, path):
    """Every lookup the feature makes, answered with a stand-in. Nothing real is reached."""
    lookups.append(path)
    if cls == R.PRIORITY_CLASS and path == R.PRIORITY_PATH:
        return stand_in_priority
    if cls == R.VENDING_EVENT_CLASS and path == R.VENDING_EVENT_PATH:
        return stand_in_vending_tag
    if cls == R.DIALOG_TAG_CLASS and path in stand_in_tags:
        return stand_in_tags[path]
    if cls == R.DIALOG_GROUP_CLASS and path == R.DIALOG_GROUP_PATH:
        return group
    if cls == R.MISSION_CLASS and path in stand_in_missions:
        return stand_in_missions[path]
    raise RuntimeError("no stand-in for find_object(%r, %r)" % (cls, path))


def _mission_values():
    return {path: m.bRepeatable for path, m in stand_in_missions.items()}


try:
    # Everything from here on answers to stand-ins only.
    R._find = _fake_find
    R._dialog_group_obj = group

    # --- reusable echo logs: the snapshot/restore mechanism, in isolation -------------------
    R._saved_talk_data = []
    R._snapshot_talk_data(group, from_apply=True)
    check(
        "the snapshot captures every TalkActs entry's original TalkAkEvent and OutputDelay",
        R._saved_talk_data == [("orig_ak_0", 0.1), ("orig_ak_1", 0.2), ("orig_ak_2", 0.3)],
        "captured %r - if this is empty or wrong-shaped, the TalkData[0].TalkAkEvent path this "
        "file corrected against the spec may be wrong" % (R._saved_talk_data,),
    )

    snapshot_again = list(R._saved_talk_data)
    group.TalkActs[0].TalkData[0].TalkAkEvent = "should_not_be_recaptured"
    R._snapshot_talk_data(group, from_apply=True)
    check(
        "the snapshot is taken once only - a second call does not recapture already-changed data",
        R._saved_talk_data == snapshot_again,
        "snapshot is now %r" % (R._saved_talk_data,),
    )

    # Simulate some OTHER echo log clobbering the shared data in the meantime.
    group.TalkActs[0].TalkData[0].TalkAkEvent = "someone_elses_ak"
    group.TalkActs[1].OutputDelay = 999.0
    R._restore_talk_data(group)
    check(
        "restoring puts every entry back to its original value, undoing the corruption",
        [(a.TalkData[0].TalkAkEvent, a.OutputDelay) for a in group.TalkActs]
        == [("orig_ak_0", 0.1), ("orig_ak_1", 0.2), ("orig_ak_2", 0.3)],
        "after restore: %r"
        % ([(a.TalkData[0].TalkAkEvent, a.OutputDelay) for a in group.TalkActs],),
    )

    # --- reusable echo logs: never switched on this session means never written --------------
    R._original_priority = {}
    R._original_event_tag = R._UNSET
    R._echoes_written = False
    R._missions_written = False
    R._mission_first_seen = {}
    lookups[:] = []

    R.reusable_echoes.value = False  # fires the feature's own apply, which must write nothing
    R._apply_echoes()
    check(
        "a switch that has never been turned on this session writes nothing to the echo data",
        group.EventTags[0] == VANILLA_EVENT_TAG
        and all(tag.Priority == VANILLA_PRIORITY for tag in stand_in_tags.values())
        and R._original_event_tag is R._UNSET,
        "event tag %r, priorities %r, snapshot taken: %r"
        % (
            group.EventTags[0],
            {k: v.Priority for k, v in stand_in_tags.items()},
            R._original_event_tag is not R._UNSET,
        ),
    )

    # --- reusable echo logs: on, then off ---------------------------------------------------
    R.reusable_echoes.value = True
    check(
        "turning it on raises every tag's dialogue priority to the shared priority object",
        all(tag.Priority is stand_in_priority for tag in stand_in_tags.values()),
        "priorities are now %r" % ({k: v.Priority for k, v in stand_in_tags.items()},),
    )
    check(
        "turning it on also puts the vending-machine event tag in the group's first slot "
        "(BL2Fix source line 5759 - the live line an earlier draft left out)",
        group.EventTags[0] == stand_in_vending_tag,
        "the group's first event tag is now %r" % (group.EventTags[0],),
    )
    check(
        "and the tag that was in that slot was remembered before it was overwritten",
        R._original_event_tag == VANILLA_EVENT_TAG,
        "remembered %r" % (R._original_event_tag,),
    )

    R.reusable_echoes.value = False
    check(
        "turning it off puts every tag's priority back to what it held before this feature ran",
        all(tag.Priority == VANILLA_PRIORITY for tag in stand_in_tags.values()),
        "priorities are now %r" % ({k: v.Priority for k, v in stand_in_tags.items()},),
    )
    check(
        "turning it off puts the group's own original event tag back in that first slot",
        group.EventTags[0] == VANILLA_EVENT_TAG,
        "the group's first event tag is now %r" % (group.EventTags[0],),
    )
    R.reusable_echoes.value = True

    # --- reusable echo logs: the ConsumeItem hook -------------------------------------------
    known_def = object()  # stands in for one of the four real UsableItemDefinitions
    other_def = object()  # stands in for an unrelated item's definition
    R._echo_objects.clear()
    R._echo_objects["stand-in-echo-path"] = known_def
    R._echo_tried = True

    # Corrupt the shared data again, so a successful block-and-restore is actually observable.
    group.TalkActs[0].TalkData[0].TalkAkEvent = "corrupted_again"

    known_item = _Item(known_def)
    result = R.on_consume_item(known_item, None, None, None)
    check(
        "consuming one of the four known echoes blocks the vanilla consumption",
        result is R.Block,
        "returned %r" % (result,),
    )
    check(
        "and restores the shared dialogue data as it does",
        group.TalkActs[0].TalkData[0].TalkAkEvent == "orig_ak_0",
        "TalkAkEvent is now %r" % (group.TalkActs[0].TalkData[0].TalkAkEvent,),
    )

    other_item = _Item(other_def)
    result2 = R.on_consume_item(other_item, None, None, None)
    check(
        "consuming an unrelated item is left alone entirely",
        result2 is None,
        "returned %r" % (result2,),
    )

    R.reusable_echoes.value = False
    result3 = R.on_consume_item(known_item, None, None, None)
    check(
        "turning the feature off in the menu lets the four echoes consume normally again",
        result3 is None,
        "returned %r" % (result3,),
    )
    R.reusable_echoes.value = True

    angry_item = _Item(None, raises=True)
    result4 = R.on_consume_item(angry_item, None, None, None)
    check(
        "an item that cannot even report its own definition is left alone, not crashed on",
        result4 is None,
        "returned %r" % (result4,),
    )

    # If the shared dialogue group can never be found, a known echo must NOT be blocked either -
    # trapping it as permanently un-consumable with no way to fix its dialogue would be worse
    # than just letting it consume normally. This is a real fix made while reviewing this file,
    # not a restated assumption - the first draft returned Block here regardless.
    R._dialog_group_obj = None
    R._find = lambda cls, path: (_ for _ in ()).throw(
        RuntimeError("the dialogue group cannot be found in this test"),
    )
    result5 = R.on_consume_item(known_item, None, None, None)
    check(
        "a known echo is not blocked when the shared dialogue group cannot be found at all",
        result5 is None,
        "returned %r" % (result5,),
    )
    R._find = _fake_find
    R._dialog_group_obj = group

    # --- repeatable missions: never switched on this session means never written ------------
    R._mission_first_seen = {}
    R._missions_written = False
    lookups[:] = []

    R.repeatable_missions.value = False  # fires the feature's own apply
    R._apply_missions()
    check(
        "with this switch never turned on, no mission is written and none is even looked up - "
        "the three the Community Patch already made repeatable stay that way",
        _mission_values() == FIRST_SEEN
        and R._mission_first_seen == {}
        and not [path for path in lookups if path in stand_in_missions],
        "missions are %r, remembered %r, looked up %r"
        % (_mission_values(), R._mission_first_seen, [p for p in lookups if p in stand_in_missions]),
    )

    # --- repeatable missions: on, then off --------------------------------------------------
    R.repeatable_missions.value = True
    check(
        "turning repeatable missions on sets bRepeatable True on all five",
        all(m.bRepeatable is True for m in stand_in_missions.values()),
        "values are now %r" % (_mission_values(),),
    )
    check(
        "and each one's own value was remembered first, before anything was written to it",
        R._mission_first_seen == FIRST_SEEN,
        "remembered %r, which should be %r" % (R._mission_first_seen, FIRST_SEEN),
    )

    R.repeatable_missions.value = False
    check(
        "turning it back off restores each mission's FIRST-SEEN value - not a blanket False, "
        "which would revert the Community Patch's own three",
        _mission_values() == FIRST_SEEN,
        "values are now %r, which should be %r" % (_mission_values(), FIRST_SEEN),
    )

    # One mission that cannot be found must not stop the other four being changed.
    missing_path, missing_mission = stand_in_missions.popitem()
    R.repeatable_missions.value = True
    check(
        "one mission failing to resolve does not stop the rest from being changed",
        all(m.bRepeatable is True for m in stand_in_missions.values()),
        "values are now %r" % (_mission_values(),),
    )
    R.repeatable_missions.value = False
    stand_in_missions[missing_path] = missing_mission

    # --- real game: does the object graph this feature depends on actually exist -----------
    def _resolves(cls, path, label):
        try:
            found = look_up(cls, path)
        except Exception as ex:
            print("[SKIP] %s (%s) resolves in this world - %r" % (label, path, ex))
            return None
        if found is None:
            print("[SKIP] %s (%s) resolves in this world - find_object returned None" % (label, path))
        return found

    all_echoes_found = True
    for path, class_name in R.ECHO_ITEMS:
        if _resolves(R.ECHO_ITEM_CLASS, path, "echo item for " + class_name) is None:
            all_echoes_found = False
    if all_echoes_found:
        check(
            "all four starting-echo UsableItemDefinitions resolve in this world",
            True,
            "found all of %r" % ([c for _p, c in R.ECHO_ITEMS],),
        )

    all_tags_found = True
    real_priority = _resolves(R.PRIORITY_CLASS, R.PRIORITY_PATH, "the target dialogue priority")
    for path in R.DIALOG_TAGS:
        tag_obj = _resolves(R.DIALOG_TAG_CLASS, path, "dialogue tag")
        if tag_obj is None:
            all_tags_found = False
        elif real_priority is not None:
            # The one real, reversible round trip: read this tag's own current priority, write
            # it back to itself, confirm the assignment does not raise, then leave it untouched.
            try:
                before = tag_obj.Priority
                tag_obj.Priority = before
                # Deliberately not asserting the re-read is the SAME object as `before`: two
                # reads of one object property need not hand back the same Python wrapper, so
                # that test would be flaky. Raising is the failure being looked for, and the
                # except below catches it.
                check(
                    "writing a real dialogue tag's own Priority back to itself does not raise",
                    True,
                    "%r written back to itself" % (before,),
                )
            except Exception as ex:
                print("[FAIL] writing %s.Priority raised: %r" % (path, ex))
    if all_tags_found:
        check(
            "all four dialogue event tags resolve in this world",
            True,
            "found all four",
        )

    # The event tag half of the echo mechanism, read-only: both ends of source line 5759 have to
    # exist for it to have anything to do.
    real_vending = _resolves(
        R.VENDING_EVENT_CLASS, R.VENDING_EVENT_PATH, "the vending-machine dialogue event",
    )
    if real_vending is not None:
        check(
            "the event tag BL2Fix puts in the echo group's first slot resolves in this world",
            True,
            R.VENDING_EVENT_PATH,
        )

    real_group = _resolves(R.DIALOG_GROUP_CLASS, R.DIALOG_GROUP_PATH, "the shared echo dialogue group")
    if real_group is not None:
        check(
            "the real dialogue group has a TalkActs array with entries to snapshot",
            bool(real_group.TalkActs) and len(real_group.TalkActs) > 0,
            "TalkActs has %r entries" % (len(real_group.TalkActs) if real_group.TalkActs else 0,),
        )
        try:
            slots = len(real_group.EventTags)
        except Exception as ex:
            slots = None
            print("[FAIL] reading the real group's EventTags raised: %r" % (ex,))
        check(
            "the real dialogue group has an EventTags slot 0 to snapshot and write",
            slots is not None and slots > 0,
            "EventTags has %r entries" % (slots,),
        )

    all_missions_found = True
    real_repeatable = {}
    for path, label in R.MISSIONS:
        mission_obj = _resolves(R.MISSION_CLASS, path, label)
        if mission_obj is None:
            all_missions_found = False
            continue
        try:
            before = bool(mission_obj.bRepeatable)
            real_repeatable[path] = before
            mission_obj.bRepeatable = before
            check(
                "writing a real mission's own bRepeatable back to itself does not raise (%s)" % label,
                bool(mission_obj.bRepeatable) == before,
                "bRepeatable is %r before and after" % (before,),
            )
        except Exception as ex:
            print("[FAIL] writing %s.bRepeatable raised: %r" % (path, ex))
    if all_missions_found:
        check(
            "all five repeatable-mission MissionDefinitions resolve in this world",
            True,
            "found all five",
        )

    # The measurement the off-path now depends on, re-taken every run rather than trusted: if the
    # three slaughters ever come back False here, either the Community Patch stopped setting them
    # or something in this pack wrote False over them, and the off-path's "restore" is then wrong.
    slaughters = {p: v for p, v in real_repeatable.items() if "Slaughter" in p}
    if len(slaughters) == 3:
        check(
            "the three slaughter missions are repeatable in the real game before this feature "
            "writes anything - which is why off must not mean False",
            all(slaughters.values()),
            "real values %r" % (slaughters,),
        )
    else:
        print("[SKIP] the three slaughter missions' real values - only %r resolved" % (len(slaughters),))

finally:
    # Module state first, option values second. Assigning a value fires the feature's apply, and
    # that apply has to run against the pack's own real state, not this file's stand-in bookkeeping.
    R._find = real_find
    R._echo_objects.clear()
    R._echo_objects.update(was["echo_objects"])
    R._echo_tried = was["echo_tried"]
    R._dialog_group_obj = was["dialog_group_obj"]
    R._saved_talk_data = was["saved_talk_data"]
    R._original_priority = was["original_priority"]
    R._original_event_tag = was["original_event_tag"]
    R._echoes_written = was["echoes_written"]
    R._mission_first_seen = was["mission_first_seen"]
    R._missions_written = was["missions_written"]
    R.reusable_echoes.value = was["reusable"]
    R.repeatable_missions.value = was["missions"]
    print("restored every stub and every setting")

summary()
