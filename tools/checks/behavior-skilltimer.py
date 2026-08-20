# Action skill cooldown timer - behavior checks for features/skilltimer.py
# Run: bash bl2-mcp/tools/ask.sh bl2-mcp/tools/checks/behavior-skilltimer.py
#
# Run this WITH A CHARACTER LOADED. The probe section below calls the real candidate functions on
# the real player controller. That measurement was taken on 2026-08-20 with the action skill IDLE,
# and the numbers it produced are recorded in IDLE_BASELINE below and written into the feature's
# own docstring; re-running this file re-takes it and says whether the game still agrees.
#
# WHAT IS STILL MISSING, and why the switch is still off: every recorded number was read while the
# skill was READY. Nobody has yet used an action skill and watched the remaining-seconds number
# fall against a stopwatch. The last section of this file takes exactly that measurement, but only
# if it happens to run while a real cooldown is ticking - so to finish this port off, use your
# action skill and then run this file within the next few seconds.
#
# THE TICK-LOGIC SECTION IS ENTIRELY FAKE, on purpose - it drives on_tick.__wrapped__ against a
# small stand-in controller with a controllable clock and cooldown state, and a spy in place of
# show_hud_message, so the countdown maths and the co-op guard can be proven on a deterministic
# schedule rather than by waiting around for a real cooldown to actually tick down.
reset()

from bl2_modern import core
from bl2_modern.features import skilltimer as ST

p = pc()

# What the real player controller answered on 2026-08-20 with the action skill IDLE. These are
# measurements, not expectations - a re-run that disagrees is worth knowing about, which is why
# the probe section below prints the comparison.
IDLE_BASELINE = {
    "IsActionSkillOnCooldown()": False,
    "GetSkillCooldownTimeRemaining()": 0.0,
    "GetSkillCooldownTime()": 15.0,
    "ActionSkillTime": -1.0,
}

was = {
    "enabled": ST.enabled.value,
    "last_shown_at": ST._last_shown_at,
    "was_on_cooldown": ST._was_on_cooldown,
}
real_get_pc = ST.get_pc
real_show = ST.show_hud_message


class FakeWorldInfo:
    def __init__(self, t):
        self.TimeSeconds = t


class FakeSkillPC:
    """A controller with a settable clock and controllable, or angry, cooldown answers."""

    def __init__(self, t, on_cooldown=False, remaining=0.0, angry_cooldown=False, angry_remaining=False):
        self.WorldInfo = FakeWorldInfo(t)
        self._on_cooldown = on_cooldown
        self._remaining = remaining
        self._angry_cooldown = angry_cooldown
        self._angry_remaining = angry_remaining
        self.cooldown_calls = 0
        self.remaining_calls = 0

    def IsActionSkillOnCooldown(self):
        self.cooldown_calls += 1
        if self._angry_cooldown:
            raise RuntimeError("pretend this function does not exist here")
        return self._on_cooldown

    def GetSkillCooldownTimeRemaining(self):
        self.remaining_calls += 1
        if self._angry_remaining:
            raise RuntimeError("pretend this function does not exist here")
        return self._remaining


shown = []


def _spy_show(title, msg, duration=2.5):
    shown.append((title, msg, duration))


try:
    # --- wiring into the core ----------------------------------------------------------------

    feature = next(
        (f for f in core.all_features() if f.name == "Action skill cooldown timer"), None,
    )
    check(
        "the skill timer feature loaded",
        feature is not None and feature.failed is None,
        feature.failed if feature else "no feature by that name",
    )
    if feature is not None:
        check(
            "the tick hook is carried to the core",
            ST.on_tick in feature.hooks,
            f"feature.hooks has {len(feature.hooks)} entries",
        )
    check(
        "the switch ships OFF, per the brief - nothing here has been measured yet",
        ST.enabled.default_value is False,
        f"default_value={ST.enabled.default_value!r}",
    )

    # --- THE REAL PROBE: which of the candidate functions/properties actually answer ---------
    # Load-bearing candidates get a real check(); the fallbacks the feature does not call get a
    # plain diagnostic line, because they are not required for this feature to work.

    try:
        cooldown_now = p.IsActionSkillOnCooldown()
        cooldown_ok = True
    except Exception as ex:
        cooldown_now = repr(ex)
        cooldown_ok = False
    check(
        "IsActionSkillOnCooldown() answers on the real player controller, without raising",
        cooldown_ok,
        f"IsActionSkillOnCooldown() -> {cooldown_now!r}",
    )

    try:
        remaining_now = p.GetSkillCooldownTimeRemaining()
        remaining_ok = True
    except Exception as ex:
        remaining_now = repr(ex)
        remaining_ok = False
    check(
        "GetSkillCooldownTimeRemaining() answers on the real player controller, without raising",
        remaining_ok,
        f"GetSkillCooldownTimeRemaining() -> {remaining_now!r}",
    )

    for label, get in (
        ("GetSkillCooldownTime()", lambda: p.GetSkillCooldownTime()),
        ("ActionSkillTime (property)", lambda: p.ActionSkillTime),
        ("SkillCooldownPool (property)", lambda: p.SkillCooldownPool),
    ):
        try:
            value = get()
            print(f"[PROBE] {label} -> {value!r}")
        except Exception as ex:
            print(f"[PROBE] {label} -> raised {ex!r}")

    if cooldown_ok and remaining_ok:
        print(
            f"[PROBE] right now, live: on_cooldown={cooldown_now!r} "
            f"remaining={remaining_now!r}",
        )
        if not cooldown_now:
            # An IDLE reading is directly comparable to what was recorded on 2026-08-20. Said as
            # a plain line rather than a check(): a different character or a different patch
            # disagreeing here is information, not a failure of this feature.
            for label, recorded, live in (
                ("IsActionSkillOnCooldown()", IDLE_BASELINE["IsActionSkillOnCooldown()"], cooldown_now),
                ("GetSkillCooldownTimeRemaining()", IDLE_BASELINE["GetSkillCooldownTimeRemaining()"], remaining_now),
            ):
                verdict = "matches" if live == recorded else "DISAGREES WITH"
                print(f"[PROBE] idle {label} -> {live!r}, {verdict} the recorded {recorded!r}")
            print(
                "[PROBE] the skill is READY right now, so this run cannot measure a countdown - "
                "use your action skill, then run this file again within a few seconds",
            )

    # --- the tick logic, entirely against fakes ----------------------------------------------

    ST.show_hud_message = _spy_show

    # A: switched off does nothing at all.
    ST.enabled.value = False
    ST._was_on_cooldown = True  # deliberately wrong, to prove the off-branch clears it
    fake = FakeSkillPC(t=100.0)
    ST.get_pc = lambda: fake
    shown.clear()
    ST.on_tick.__wrapped__(fake, None, None, None)
    check(
        "switched off, nothing is shown and stale cooldown state is forgotten",
        shown == [] and ST._was_on_cooldown is False,
        f"shown={shown}, _was_on_cooldown={ST._was_on_cooldown}",
    )

    # B: switched on, on cooldown - the first check.
    ST.enabled.value = True
    ST._last_shown_at = -1.0
    fake = FakeSkillPC(t=100.0, on_cooldown=True, remaining=42.3)
    ST.get_pc = lambda: fake
    shown.clear()
    ST.on_tick.__wrapped__(fake, None, None, None)
    check(
        "on cooldown, the seconds remaining are rounded UP and shown",
        shown == [("Action skill", "Ready in 43s", ST.DURATION)],
        f"shown={shown}",
    )
    check(
        "the module remembers it was on cooldown, and when it last said so",
        ST._was_on_cooldown is True and ST._last_shown_at == 100.0,
        f"_was_on_cooldown={ST._was_on_cooldown}, _last_shown_at={ST._last_shown_at}",
    )

    # C: the same instant again must not refresh - not enough time has passed.
    shown.clear()
    ST.on_tick.__wrapped__(fake, None, None, None)
    check(
        "checking again in the same instant shows nothing new",
        shown == [],
        f"shown={shown}",
    )

    # D: a full interval later, the number moves.
    fake.WorldInfo.TimeSeconds = 100.0 + ST.INTERVAL
    fake._remaining = 41.0
    shown.clear()
    ST.on_tick.__wrapped__(fake, None, None, None)
    check(
        "a full interval later, the countdown has moved",
        shown == [("Action skill", "Ready in 41s", ST.DURATION)],
        f"shown={shown}",
    )

    # E: cooldown ends - one last "ready" message, exactly once.
    fake.WorldInfo.TimeSeconds += ST.INTERVAL
    fake._on_cooldown = False
    shown.clear()
    ST.on_tick.__wrapped__(fake, None, None, None)
    check(
        "the moment the cooldown ends, one ready message is shown",
        shown == [("Action skill", "Action skill ready", ST.DURATION)],
        f"shown={shown}",
    )
    check(
        "and the module no longer believes it is on cooldown",
        ST._was_on_cooldown is False,
        f"_was_on_cooldown={ST._was_on_cooldown}",
    )

    # F: staying ready must not repeat the message.
    fake.WorldInfo.TimeSeconds += ST.INTERVAL
    shown.clear()
    ST.on_tick.__wrapped__(fake, None, None, None)
    check(
        "once ready, it stays quiet rather than repeating 'ready' every second",
        shown == [],
        f"shown={shown}",
    )

    # G: THE CO-OP GUARD. A different controller ticking (the guest, on the host's own
    # machine) must never make it onto THIS screen.
    fake.WorldInfo.TimeSeconds += ST.INTERVAL
    fake._on_cooldown = True
    fake._remaining = 10.0
    other_players_controller = FakeSkillPC(t=fake.WorldInfo.TimeSeconds, on_cooldown=True, remaining=5.0)
    shown.clear()
    ST.on_tick.__wrapped__(other_players_controller, None, None, None)
    check(
        "a tick for a DIFFERENT controller than the local player's own is ignored entirely",
        shown == [] and other_players_controller.cooldown_calls == 0,
        f"shown={shown}, the foreign controller was asked its cooldown "
        f"{other_players_controller.cooldown_calls} times",
    )
    # And the real local one still works right afterwards - the guard does not wedge anything.
    shown.clear()
    ST.on_tick.__wrapped__(fake, None, None, None)
    check(
        "and the local player's own tick still works normally straight after",
        shown == [("Action skill", "Ready in 10s", ST.DURATION)],
        f"shown={shown}",
    )

    # H: IsActionSkillOnCooldown raising is contained, and complained about once.
    ST._said.discard("read")
    ST._last_shown_at = -1.0
    angry = FakeSkillPC(t=200.0, angry_cooldown=True)
    ST.get_pc = lambda: angry
    shown.clear()
    blew_up = None
    try:
        ST.on_tick.__wrapped__(angry, None, None, None)
    except Exception as ex:
        blew_up = repr(ex)
    check(
        "IsActionSkillOnCooldown raising does not take the pack down",
        blew_up is None and shown == [],
        f"raised {blew_up}, shown={shown}",
    )
    check(
        "and it is recorded as a reason this cannot work, once",
        "read" in ST._said,
        f"_said={ST._said}",
    )

    # I: GetSkillCooldownTimeRemaining raising is contained too.
    ST._said.discard("remaining")
    ST._last_shown_at = -1.0
    angry2 = FakeSkillPC(t=210.0, on_cooldown=True, angry_remaining=True)
    ST.get_pc = lambda: angry2
    shown.clear()
    blew_up = None
    try:
        ST.on_tick.__wrapped__(angry2, None, None, None)
    except Exception as ex:
        blew_up = repr(ex)
    check(
        "GetSkillCooldownTimeRemaining raising does not take the pack down either",
        blew_up is None and shown == [],
        f"raised {blew_up}, shown={shown}",
    )
    check(
        "and it too is recorded once",
        "remaining" in ST._said,
        f"_said={ST._said}",
    )

    # --- one real call, only if there happens to be a real cooldown running right now --------

    ST.get_pc = real_get_pc
    ST.show_hud_message = real_show
    ST._last_shown_at = -1.0
    if cooldown_ok and cooldown_now:
        shown_real = []
        ST.show_hud_message = lambda title, msg, duration=2.5: shown_real.append(msg)
        ST.on_tick.__wrapped__(p, None, None, None)
        check(
            "with a real cooldown actually running, the real hook puts a real message on screen",
            bool(shown_real),
            f"shown_real={shown_real}",
        )
        # THE MEASUREMENT THIS PORT IS STILL WAITING ON, taken as far as one run can take it: a
        # remaining that sits between zero and the whole cooldown length is the first hard
        # evidence that the two numbers share a unit at all. Only a stopwatch can finish the
        # job - run this file twice, a few seconds apart, during one cooldown.
        try:
            total_now = float(p.GetSkillCooldownTime())
            live_remaining = float(p.GetSkillCooldownTimeRemaining())
            check(
                "mid-cooldown, the seconds remaining sit between zero and the whole cooldown "
                "length - the two numbers really are in the same unit",
                0.0 < live_remaining <= total_now,
                f"remaining={live_remaining!r} out of a total of {total_now!r}",
            )
            print(
                f"[PROBE] MID-COOLDOWN SAMPLE: remaining={live_remaining!r} "
                f"total={total_now!r} ActionSkillTime={p.ActionSkillTime!r} - run this again in "
                f"a few seconds and check 'remaining' has fallen by about that many seconds",
            )
        except Exception as ex:
            print(f"[PROBE] mid-cooldown sample could not be taken: {ex!r}")
    else:
        print(
            "[SKIP] a real on-screen message driven by a real cooldown   "
            "your action skill is not on cooldown right now - use it, then run this again "
            "within a few seconds to see the real number",
        )

finally:
    ST.get_pc = real_get_pc
    ST.show_hud_message = real_show
    ST.enabled.value = was["enabled"]
    ST._last_shown_at = was["last_shown_at"]
    ST._was_on_cooldown = was["was_on_cooldown"]
    ST._said.clear()
    check(
        "every stub and every setting this file touched is back where it started",
        ST.get_pc is real_get_pc
        and ST.show_hud_message is real_show
        and ST.enabled.value == was["enabled"],
        f"enabled={ST.enabled.value!r}",
    )

summary()
