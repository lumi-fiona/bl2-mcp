# Version handshake - the two claims that need a tick and a level load to pass.
#
# THIS FILE IS RUN TWICE. The first run arms the recorders and sends one real broadcast; the
# second run reads what happened and puts everything back. Between them the map must change,
# because SpawningProcessComplete - the hook under test - fires on every level load.
#
#   bash bl2-mcp/tools/ask.sh bl2-mcp/tools/checks/co-op-and-handshake-needs-travel.py
#   sleep 3                              # the message queue sends one message per tick
#   echo 'print(travel_to("Sanctuary"), where())' | bash bl2-mcp/tools/ask.sh
#   for i in $(seq 24); do sleep 5; echo 'print(where())' | ASK_TIMEOUT=90 bash bl2-mcp/tools/ask.sh; done
#   # stop polling once where() reports the new map, then:
#   bash bl2-mcp/tools/ask.sh bl2-mcp/tools/checks/co-op-and-handshake-needs-travel.py
#
# Already in Sanctuary? Travel anywhere else instead - any map change does. If the second run
# happens without a map change it says so and fails the level-load check rather than passing it
# by not running.
#
# Why not one request: the map change needs the very frame a wait loop would be holding, and a
# broadcast is delivered a tick after it is queued (message_queue.py:15-30). Both are invisible
# from inside a single bridge request.
#
# NOT covered, and no solo run can cover it: whether the announcement reaches the OTHER
# player's machine (handshake claim 3). That needs a second install. What this file proves is
# the half that is testable alone - the message really does go out onto the transport and come
# back, and the guard that stops a solo player being told "another player matches" holds.
#
# Everything this file patches forwards to the real thing, so a run that is armed and never
# read back changes no behaviour - it only records.

import json

import networking.registration as netreg
from bl2_modern.features import handshake as H

STATE = "_COOP_HANDSHAKE_ARMED"
# Run 1 swaps H.announce for a recording spy (a plain function) and keeps the real one in the
# armed state. This line runs at the top of EVERY send of this file, so on run 2 it must take
# the identifier from the real announce, not ask the spy for an attribute only the real one
# carries - measured 2026-08-20: run 2 raised "'function' object has no attribute
# 'network_identifier'" and the whole second half never ran.
IDENT = (
    globals()[STATE]["real_announce"].network_identifier
    if STATE in globals()
    else H.announce.network_identifier
)


class ForwardingSpy:
    """unrealsdk.logging for one module, recording every line and passing it straight on."""

    def __init__(self, real, lines):
        self._real = real
        self._lines = lines

    def __getattr__(self, kind):
        onward = getattr(self._real, kind)

        def say(message, *args, **kwargs):
            self._lines.append((kind, str(message)))
            return onward(message, *args, **kwargs)

        return say


if STATE not in globals() and pc() is None:
    # Nothing to arm against: where() and the announce hook both need a live character.
    reset()
    check(
        "a character is live, without which there is nothing to arm",
        False,
        "load a character first - this file is about what happens on the NEXT level load",
    )
    summary()

elif STATE not in globals():
    # ---- first run: arm ------------------------------------------------------------------
    reset()

    state = {
        "map": where(),
        "announced_at_arm": H._announced,
        "sent": [],
        "received": [],
        "logged": [],
        "real_announce": H.announce,
        "real_logging": H.logging,
        "real_callback": netreg.registered_callbacks.get(IDENT),
        "mine": (H.__version__, H.patch_fingerprint()),
    }

    # The third argument arrived when announce grew its mods report (2026-08-20). A two-arg
    # spy raised TypeError on every arrival announce, the raise was swallowed by the map
    # watcher's callback guard, and this file then blamed the latch - the recorder must
    # always match the real signature, defaults included.
    def record_sent(version, fingerprint, mods=None, _state=state):
        _state["sent"].append((version, fingerprint))
        return _state["real_announce"](version, fingerprint, mods)

    def record_received(sender, message, _state=state):
        _state["received"].append((str(sender), message))
        if _state["real_callback"] is not None:
            _state["real_callback"](sender, message)

    H.announce = record_sent
    H.logging = ForwardingSpy(state["real_logging"], state["logged"])
    if state["real_callback"] is not None:
        netreg.registered_callbacks[IDENT] = record_received
    state["wrapper"] = record_received

    check(
        "the handshake's network function was registered before this was armed",
        state["real_callback"] is not None,
        f"{IDENT}; without it nothing can be delivered and the second run proves nothing",
    )

    # Sent through the real function, not the recorder, so anything the recorder catches later
    # came from the spawn hook rather than from here.
    state["real_announce"](*state["mine"])
    globals()[STATE] = state

    print(f"armed in {state['map']}, announced {state['mine']}, "
          f"_announced was {state['announced_at_arm']}")
    print("now: wait 3 seconds, change map, wait for the load, then run this file again")
    summary()

else:
    # ---- second run: read it back and put everything away ---------------------------------
    reset()
    state = globals()[STATE]
    try:
        check(
            "the broadcast this machine sent came back to it, so the transport really carried it",
            len(state["received"]) >= 1,
            f"{len(state['received'])} messages received since arming",
        )
        payloads = []
        for _sender, message in state["received"]:
            try:
                args, _kwargs = json.loads(message)
                payloads.append(tuple(args))
            except Exception as ex:
                payloads.append(f"undecodable: {ex!r}")
        check(
            "what came back is the version and fingerprint that went out",
            state["mine"] in payloads,
            f"sent {state['mine']}, received {payloads}",
        )

        heard = [m for _k, m in state["logged"]
                 if "another player matches" in m or "MISMATCH" in m]
        check(
            "playing alone is never told that another player matches, or mismatches",
            not heard,
            f"handshake logged: {heard}",
        )

        moved = where() != state["map"]
        check(
            "the map changed since this was armed, which is what fires the announce hook",
            moved,
            f"armed in {state['map']}, now in {where()}",
        )
        if not state["announced_at_arm"]:
            check(
                "this machine had already announced before the level load, which is the state "
                "joining a friend's game puts you in",
                False,
                "_announced was still False when this was armed, so the level-load check below "
                "cannot mean anything - load a character first, then arm",
            )
        elif not moved:
            check(
                "a level load announces again, so joining a friend after playing solo is compared",
                False,
                "no map change happened, so the hook never fired - travel and run this again",
            )
        else:
            check(
                "a level load announces again, so joining a friend after playing solo is compared",
                len(state["sent"]) >= 1,
                "handshake.py:53 latches _announced for the life of the process, so every level "
                f"load after the first sends nothing: {state['sent']}",
            )
    finally:
        H.announce = state["real_announce"]
        H.logging = state["real_logging"]
        if netreg.registered_callbacks.get(IDENT) is state["wrapper"]:
            netreg.registered_callbacks[IDENT] = state["real_callback"]
        del globals()[STATE]
        check(
            "the recorders were taken back out",
            H.announce is state["real_announce"]
            and H.logging is state["real_logging"]
            and netreg.registered_callbacks.get(IDENT) is state["real_callback"],
            f"announce={H.announce!r}",
        )
    summary()
