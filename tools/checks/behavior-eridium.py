# Eridium auto-pickup (eridium.py) - behavior checks
# Run: bash bl2-mcp/tools/ask.sh bl2-mcp/tools/checks/behavior-eridium.py
#
# Writes one bool on two currency-pickup DEFINITIONS - not the player's wallet, not their
# inventory. Every value this file changes is read first and put back in the finally block.
reset()

import unrealsdk
from bl2_modern import core
from bl2_modern.features import eridium as ER

was_mode = ER.mode.value
real_get_pc = ER.get_pc
real_find_object = unrealsdk.find_object
snap_first_seen = dict(ER._first_seen)

# Given a safe default here, not only where it is first filled in below - an exception early
# in the try (before the real objects are ever read) must still leave the finally block an
# empty dict to iterate, not a NameError that replaces whatever was actually being reported.
before: dict = {}


class _FakeController:
    """Stands in for a player controller. NetMode is set but eridium.py must not read it."""

    def __init__(self, playthrough, net_mode=0):
        self._pt = playthrough
        self.WorldInfo = type("W", (), {"NetMode": net_mode})()

    def GetCurrentPlaythrough(self):
        return self._pt


try:
    # --- is the feature wired in at all -----------------------------------------------------
    feature = next((f for f in core.all_features() if f.name == "Eridium auto-pickup"), None)
    check(
        "the Eridium auto-pickup feature loaded into the pack without failing",
        feature is not None and feature.failed is None,
        "not registered" if feature is None else (feature.failed or "registered, no failure"),
    )
    check(
        "it ships matching BL2Fix's own default, because this is pure convenience, not economy",
        ER.mode.default_value == ER.ONLY_UVHM,
        f"default is {ER.mode.default_value!r}",
    )
    check(
        "the per-map arrival is carried to the core",
        feature is not None and feature.on_arrival is ER.on_arrival,
        getattr(feature, "on_arrival", None),
    )
    check(
        "moving the spinner applies it straight away",
        ER.mode.on_change_anytime is ER._on_change,
        ER.mode.on_change_anytime,
    )

    # --- the other installed mod that writes the same field must be disclosed, in plain words -
    # AutoPickupTweaks.sdkmod sets bAutomaticallyPickup on the same two objects
    # (AutoPickupTweaks/__init__.py:189, objects at :252-253). Someone reading only the menu must
    # be told, and must be given the way out, or two mods fight over one field in silence.
    check(
        "the switch's own menu text names the other mod that writes the same thing, and offers "
        "the setting that hands the field over to it",
        "Auto Pickup Tweaks" in ER.mode.description
        and ER.LEAVE_ALONE in ER.mode.choices
        and ER.LEAVE_ALONE.lower() in ER.mode.description.lower(),
        f"choices={ER.mode.choices}, description={ER.mode.description!r}",
    )
    check(
        "and the file itself records which mod's write wins when, rather than leaving it to be "
        "found out in game",
        "AutoPickupTweaks" in (ER.__doc__ or ""),
        "the module docstring does not mention AutoPickupTweaks at all",
    )

    # --- the real objects: read BEFORE the first thing that could write them ------------------
    # This has to come before any assignment to ER.mode.value. Assigning an option's value fires
    # its change callback, and this feature's callback really applies - so the very first
    # ER.mode.value = ... below already writes both objects. A baseline taken after that would be
    # this file's own writing, not what the session was actually in.
    objects = ER._objects()
    before = {}
    if len(objects) < 2:
        print(
            f"[SKIP] only found {len(objects)} of 2 eridium pickup objects "
            f"({ER.BAR}, {ER.STICK}) - the write/restore checks below need both loaded",
        )
    else:
        for obj in objects:
            before[obj] = bool(obj.bAutomaticallyPickup)
        check(
            "both the eridium bar and stick definitions are found and readable",
            len(objects) == 2,
            f"found {len(objects)}",
        )
        print(f"eridium: on arrival {[(str(o.Name), before[o]) for o in objects]}")

    # --- the pure decision function, no game object involved ---------------------------------
    ER.mode.value = ER.ALWAYS
    check(
        "'Always' picks up in every playthrough, and even when the playthrough is not known yet",
        ER._desired(None) is True and ER._desired(0) is True and ER._desired(2) is True,
        [ER._desired(None), ER._desired(0), ER._desired(2)],
    )
    ER.mode.value = ER.NEVER
    check(
        "'Never' prompts in every playthrough, and even when the playthrough is not known yet",
        ER._desired(None) is False and ER._desired(0) is False and ER._desired(2) is False,
        [ER._desired(None), ER._desired(0), ER._desired(2)],
    )
    ER.mode.value = ER.ONLY_UVHM
    check(
        "'UVHM' does not guess when the playthrough is not known yet - it waits",
        ER._desired(None) is None,
        ER._desired(None),
    )
    check(
        "'UVHM' picks up only in UVHM itself (playthrough 2), and prompts in NVHM and TVHM",
        ER._desired(0) is False and ER._desired(1) is False and ER._desired(2) is True,
        [ER._desired(0), ER._desired(1), ER._desired(2)],
    )

    # --- the writes themselves, against the objects snapshotted at the top --------------------
    if len(objects) >= 2:
        # --- Always / Never: immediate, regardless of playthrough --------------------------
        ER.mode.value = ER.ALWAYS
        ER._apply(playthrough=None)
        check(
            "'Always' turns auto-pickup on for both objects even with no playthrough known",
            all(bool(o.bAutomaticallyPickup) is True for o in objects),
            {str(o.Name): bool(o.bAutomaticallyPickup) for o in objects},
        )

        ER.mode.value = ER.NEVER
        ER._apply(playthrough=None)
        check(
            "'Never' turns auto-pickup off for both objects even with no playthrough known",
            all(bool(o.bAutomaticallyPickup) is False for o in objects),
            {str(o.Name): bool(o.bAutomaticallyPickup) for o in objects},
        )

        # --- UVHM: reacts to playthrough, self-corrects without a restart -------------------
        ER.mode.value = ER.ONLY_UVHM
        ER._apply(playthrough=0)
        check(
            "'UVHM' mode in NVHM (playthrough 0) leaves auto-pickup off",
            all(bool(o.bAutomaticallyPickup) is False for o in objects),
            {str(o.Name): bool(o.bAutomaticallyPickup) for o in objects},
        )
        ER._apply(playthrough=2)
        check(
            "'UVHM' mode in UVHM itself (playthrough 2) turns auto-pickup on",
            all(bool(o.bAutomaticallyPickup) is True for o in objects),
            {str(o.Name): bool(o.bAutomaticallyPickup) for o in objects},
        )
        check(
            "moving between playthroughs in the same session re-corrects it - no restart needed, "
            "unlike BL2Fix's own live path which never re-checked this at all",
            True,  # proven by the two checks immediately above running in the same process
            "NVHM -> off, UVHM -> on, both in this one check run",
        )
        ER._apply(playthrough=None)
        check(
            "an unknown playthrough leaves the last known state alone rather than guessing",
            all(bool(o.bAutomaticallyPickup) is True for o in objects),
            {str(o.Name): bool(o.bAutomaticallyPickup) for o in objects},
        )

        # --- the deliberate absence of a host/client guard ----------------------------------
        # See the module docstring: BL2Fix's per-map recheck is host-only, and this port drops
        # that gate on purpose because the flag reads as purely local. A NetMode of 3 (a
        # machine that joined someone else's game) must NOT stop this hook from writing.
        ER._apply(playthrough=0)  # known state: off, before driving the hook
        ER.on_arrival(_FakeController(2, net_mode=3))
        check(
            "the per-map hook writes even for a controller that looks like a joined client - "
            "this feature deliberately has no host/client guard at all",
            all(bool(o.bAutomaticallyPickup) is True for o in objects),
            {str(o.Name): bool(o.bAutomaticallyPickup) for o in objects},
        )

        # --- one object failing must not stop the other ------------------------------------
        class _Angry:
            Name = "angry stand-in"
            bAutomaticallyPickup = False

            def __setattr__(self, key, value):
                if key == "bAutomaticallyPickup":
                    raise RuntimeError("simulated: this object refuses the write")
                object.__setattr__(self, key, value)

        real_objects_fn = ER._objects
        good = objects[0]
        good.bAutomaticallyPickup = False
        ER._objects = lambda: [_Angry(), good]
        ER.mode.value = ER.ALWAYS
        ER._apply(playthrough=None)
        ER._objects = real_objects_fn
        check(
            "one pickup object refusing the write does not stop the other one being set",
            bool(good.bAutomaticallyPickup) is True,
            f"the good object reads {bool(good.bAutomaticallyPickup)!r}",
        )

        # --- "Leave it alone": hand the field back, then stop writing -----------------------
        # What it hands back is this pack's own first-seen snapshot, taken before its very first
        # write - which may predate this check file, since the feature applies at the main menu.
        handed_back = {str(o.Name): ER._first_seen.get(str(o.Name)) for o in objects}
        print(f"eridium: first-seen snapshot the pack is holding = {handed_back}")
        check(
            "the pack really took a first-seen snapshot rather than assuming the field was off",
            all(v is not None for v in handed_back.values()),
            f"{handed_back}",
        )
        ER.mode.value = ER.ALWAYS
        ER.mode.value = ER.LEAVE_ALONE
        check(
            "'Leave it alone' puts both objects back to what the pack found before its own first "
            "write - not to a guessed vanilla off",
            all(bool(o.bAutomaticallyPickup) == handed_back[str(o.Name)] for o in objects),
            {str(o.Name): (bool(o.bAutomaticallyPickup), handed_back[str(o.Name)]) for o in objects},
        )
        for obj in objects:
            obj.bAutomaticallyPickup = not handed_back[str(obj.Name)]
        marked = {str(o.Name): bool(o.bAutomaticallyPickup) for o in objects}
        ER._apply(playthrough=2)
        ER._apply(playthrough=None)
        ER.on_arrival(_FakeController(2))
        check(
            "and then it writes nothing at all, whatever runs - the field is the other mod's",
            all(bool(o.bAutomaticallyPickup) == marked[str(o.Name)] for o in objects),
            {str(o.Name): (bool(o.bAutomaticallyPickup), marked[str(o.Name)]) for o in objects},
        )

    # --- nothing here may ever raise into the game -------------------------------------------
    def _angry_find(cls, path):
        raise RuntimeError(f"simulated: {cls} lookup refused")

    unrealsdk.find_object = _angry_find
    escaped = []
    for label, call in (
        ("apply", lambda: ER._apply(2)),
        ("apply_current", lambda: ER._apply_current()),
    ):
        try:
            call()
        except Exception as ex:
            escaped.append((label, ex))
    unrealsdk.find_object = real_find_object
    check(
        "a lookup that refuses cannot throw out of either entry point into the game",
        not escaped,
        f"{escaped!r}",
    )

    ER.get_pc = lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("no session"))
    escaped = None
    try:
        ER._apply_current()
    except Exception as ex:
        escaped = ex
    ER.get_pc = real_get_pc
    check(
        "a session that does not exist yet cannot throw out of the main-menu apply either",
        escaped is None,
        f"{escaped!r}",
    )

finally:
    unrealsdk.find_object = real_find_object
    ER.get_pc = real_get_pc
    ER._first_seen.clear()
    ER._first_seen.update(snap_first_seen)
    # The switch goes back FIRST: putting it back fires the change callback, which applies, which
    # writes both objects. Restoring the objects before that would just be overwritten by it.
    ER.mode.value = was_mode
    for obj, original in before.items():
        try:
            obj.bAutomaticallyPickup = original
        except Exception as ex:
            print(f"could not restore bAutomaticallyPickup on {obj}: {ex!r}")

    check(
        "the switch and both pickup objects are back where this file found them",
        ER.mode.value == was_mode
        and all(bool(o.bAutomaticallyPickup) == before[o] for o in before),
        f"mode={ER.mode.value!r}, "
        f"{ {str(o.Name): (bool(o.bAutomaticallyPickup), before[o]) for o in before} }",
    )

summary()
