# Things on screen - the claims that need a real fight, a real drop and a person looking at the
# screen. Same file, run four times; it works out which phase it is in from what it left behind.
#
# THE OPERATOR RUNS EXACTLY THIS, from the Borderlands 2 folder, with a character loaded:
#
#   bash bl2-mcp/tools/ask.sh bl2-mcp/tools/harness.py                      # once a session
#   bash bl2-mcp/tools/ask.sh bl2-mcp/tools/checks/things-on-screen-needs-travel.py
#       phase 1: turns all four features on, widens their settings so ordinary play trips
#                them, and wraps counters around the six functions that matter
#
#   >>> NOW, BY HAND: go and kill things for a couple of minutes. It must include at least
#   >>> one BADASS - the boss bar only appears for badasses and named enemies - and you must
#   >>> keep shooting it long enough to look at the top of the screen while it is alive.
#   >>> Kill it with the gun you are holding and do not swap weapons.
#
#   bash bl2-mcp/tools/ask.sh bl2-mcp/tools/checks/things-on-screen-needs-travel.py
#       phase 2: photographs the screen, then reports whether the bar went up, whether kills
#                were counted on the gun in your hands, and whether any drop was marked
#
#   >>> NOW, BY HAND: open your backpack and hover the gun you were shooting with, so its
#   >>> card is drawn. Then close the backpack.
#
#   bash bl2-mcp/tools/ask.sh bl2-mcp/tools/checks/things-on-screen-needs-travel.py
#       phase 3: reports whether the card hooks fired and what history text they produced
#
#   >>> NOW, BY HAND: fast travel anywhere. Wait for the new map.
#
#   ASK_TIMEOUT=90 bash bl2-mcp/tools/ask.sh bl2-mcp/tools/checks/things-on-screen-needs-travel.py
#       phase 4: checks the markers were cleaned up by the map change, puts everything back
#
# IF YOU STOP EARLY, RUN PHASE 4 ANYWAY. Until it runs, four features are wearing counters and
# their settings are at test values rather than yours. Running phase 4 twice is harmless.
#
# TWO OF THESE CANNOT BE SETTLED BY A SCRIPT AT ALL, and the file says so rather than pretending:
# whether the bar is legible where it is drawn, and whether the marker on the compass is the
# right shape and in the right place. Both are in the screenshot phase 2 takes, and a person or
# a later image read has to look at it. The file records everything a script CAN settle around
# them - that the calls were made, with what, and that nothing raised.

from bl2_modern.features import bossbar as bb
from bl2_modern.features import gunhistory as gh
from bl2_modern.features import lootmarker as lm
from bl2_modern.features import truedamage as td

if not hasattr(bb, "_check_state"):
    bb._check_state = {
        "phase": 0,
        "bars_shown": [],
        "bars_hidden": 0,
        "markers_made": 0,
        "markers_refused": 0,
        "kills_stored": [],
        "cards_seen": 0,
        "card_lines": [],
        "damage_lines": [],
        "originals": {},
        "options": [],
        "held_uid": None,
        "history_before": None,
    }
state = bb._check_state

MODULES = {"bb": bb, "td": td, "lm": lm, "gh": gh}
P = pc()

reset()


def instrument():
    """Wrap the six functions whose being called is the whole question."""
    saved = {}

    saved["bb._show"] = bb._show
    saved["bb._hide"] = bb._hide
    saved["lm._spawn_marker"] = lm._spawn_marker
    saved["gh._store"] = gh._store
    saved["gh._line_for"] = gh._line_for
    saved["gh._item_from"] = gh._item_from
    saved["td.logging"] = td.logging

    def show(pawn):
        try:
            state["bars_shown"].append(str(pawn.Name))
        except Exception:
            state["bars_shown"].append(repr(pawn))
        return saved["bb._show"](pawn)

    def hide():
        state["bars_hidden"] += 1
        return saved["bb._hide"]()

    def spawn(where):
        made = saved["lm._spawn_marker"](where)
        if made is None:
            state["markers_refused"] += 1
        else:
            state["markers_made"] += 1
        return made

    def store(uid, entry):
        state["kills_stored"].append((int(uid), list(entry)))
        return saved["gh._store"](uid, entry)

    def line_for(item):
        made = saved["gh._line_for"](item)
        state["card_lines"].append(made)
        return made

    def item_from(args):
        state["cards_seen"] += 1
        return saved["gh._item_from"](args)

    class Log:
        def info(self, message):
            state["damage_lines"].append(str(message))

        def error(self, message):
            state["damage_lines"].append("ERROR " + str(message))

        def warning(self, message):
            state["damage_lines"].append("WARNING " + str(message))

        def dev_warning(self, message):
            pass

        def misc(self, message):
            pass

    bb._show = show
    bb._hide = hide
    lm._spawn_marker = spawn
    gh._store = store
    gh._line_for = line_for
    gh._item_from = item_from
    td.logging = Log()

    state["originals"] = saved


def restore():
    saved = state.get("originals") or {}
    for key, value in saved.items():
        module, name = key.split(".")
        setattr(MODULES[module], name, value)
    state["originals"] = {}
    for option, value in state.get("options") or []:
        option.value = value
    state["options"] = []


# --------------------------------------------------------------------------------------

phase = state["phase"] + 1
state["phase"] = phase
print(f"--- phase {phase} ---")

if phase == 1:
    state["options"] = [
        (o, o.value)
        for o in (
            bb.enabled, bb.include_badasses, bb.include_bosses, bb.follow_latest,
            td.enabled, td.where, td.smallest, td.show_target,
            lm.enabled, lm.floor, lm.ding, lm.most_at_once,
            gh.enabled, gh.show_kills, gh.show_place,
        )
    ]

    bb.enabled.value = True
    bb.include_badasses.value = True
    bb.include_bosses.value = True
    bb.follow_latest.value = False

    td.enabled.value = True
    td.where.value = td.TO_LOG
    # Four digits, not seven. A normal fight at a normal level does not do a million damage,
    # and a threshold nothing ever clears would make "no lines at all" mean nothing.
    td.smallest.value = 4
    td.show_target.value = True

    lm.enabled.value = True
    # Purple, not legendary. Waiting for a legendary to drop is not a test plan.
    lm.floor.value = lm.FROM_PURPLE
    lm.ding.value = True
    lm.most_at_once.value = 20

    gh.enabled.value = True
    gh.show_kills.value = True
    gh.show_place.value = True

    # The kills gained during the test fight are real play and are deliberately kept - this is
    # the one thing here that is not put back, because putting it back would delete a record of
    # something that actually happened.
    try:
        state["held_uid"] = gh._uid_of(P.Pawn.Weapon)
    except Exception:
        state["held_uid"] = None

    instrument()

    check(
        "all four features are switched on and their hooks are bound",
        bb.on_damage.get_active_count() > 0
        and td.on_damage_shown.get_active_count() > 0
        and lm.on_landed.get_active_count() > 0
        and gh.on_kill.get_active_count() > 0,
        f"bossbar {bb.on_damage.get_active_count()}, "
        f"truedamage {td.on_damage_shown.get_active_count()}, "
        f"lootmarker {lm.on_landed.get_active_count()}, "
        f"gunhistory {gh.on_kill.get_active_count()}",
    )
    check(
        "the gun in your hands has an id, so its kills can be counted",
        state["held_uid"] is not None,
        f"id {state['held_uid']}",
    )
    print("\nNOW GO AND FIGHT. Include at least one badass. Do not change weapons.")

elif phase == 2:
    screenshot()

    check(
        "a badass or named enemy was given the health bar",
        bool(state["bars_shown"]),
        f"the bar was given to {state['bars_shown'][:5]}",
    )
    check(
        "the bar came down again afterwards",
        state["bars_hidden"] > 0,
        f"taken down {state['bars_hidden']} times",
    )
    check(
        "the bar is not stuck on an enemy that is already dead",
        bb._tracked is None or bool(getattr(bb._tracked, "Health", 0)),
        f"tracking {bb._tracked}",
    )

    real_damage = [line for line in state["damage_lines"] if line.startswith("truedamage:")]
    check(
        "the real damage number was written down during the fight",
        bool(real_damage),
        f"{len(real_damage)} lines, first: {real_damage[0] if real_damage else ''}",
    )
    check(
        "the damage lines name what was hit rather than an object name",
        bool(real_damage) and any(" to " in line for line in real_damage),
        real_damage[-1] if real_damage else "",
    )
    complaints = [line for line in state["damage_lines"] if line.startswith(("ERROR", "WARNING"))]
    check(
        "nothing in the damage readout complained",
        not complaints,
        f"{complaints[:3]}",
    )

    kills_here = [entry for uid, entry in state["kills_stored"] if uid == state["held_uid"]]
    check(
        "kills were counted onto the gun you were holding",
        bool(kills_here),
        f"{len(kills_here)} kills recorded for id {state['held_uid']}",
    )
    check(
        "the count on the gun matches how many kills were recorded",
        state["held_uid"] is not None
        and gh._entry(state["held_uid"])[0] >= len(kills_here),
        f"the gun says {gh._entry(state['held_uid'])[0] if state['held_uid'] else '-'} kills",
    )

    # Drops. Purple and better only, so a short fight may honestly produce none - which is why
    # the refusal count is a separate claim from the marker count.
    check(
        "nothing refused to place a marker",
        state["markers_refused"] == 0,
        f"{state['markers_refused']} refusals, {state['markers_made']} placed",
    )
    print(
        f"\n{state['markers_made']} markers were placed and {len(lm._markers)} are still up.\n"
        "If that is zero, nothing purple or better dropped - fight more and run phase 2 again\n"
        "rather than reading zero as a failure.\n"
        "\nLOOK AT THE SCREENSHOT. It is in Steam/userdata/<id>/760/remote/49520/screenshots/.\n"
        "Two things only a person can settle are in it: whether the health bar is where it\n"
        "should be, and whether a marker sits on the compass where the loot actually is.\n"
        "\nNOW OPEN YOUR BACKPACK and hover the gun you were shooting with, then close it.",
    )

elif phase == 3:
    check(
        "the game asked for an item card while the backpack was open",
        state["cards_seen"] > 0,
        f"{state['cards_seen']} cards drawn",
    )
    check(
        "the card knew which item it was drawing",
        state["cards_seen"] > 0 and gh._said and "card-arg" in gh._said,
        f"what the feature worked out: {sorted(gh._said)}",
    )
    real_lines = [line for line in state["card_lines"] if line]
    check(
        "at least one card was given a history line",
        bool(real_lines),
        f"{len(real_lines)} of {len(state['card_lines'])} cards, first: {real_lines[0] if real_lines else ''}",
    )
    check(
        "the history line reads as plain English",
        bool(real_lines) and "kill" in real_lines[0],
        real_lines[0] if real_lines else "",
    )
    print(
        "\nDID YOU SEE IT ON THE CARD? The check above only proves the text was produced and\n"
        "handed over. Whether it appears at the bottom of the card, and whether it collides\n"
        "with Python Part Notifier's own text, needs your eyes.\n"
        "\nNOW FAST TRAVEL ANYWHERE, wait for the map, then run phase 4.",
    )

else:
    check(
        "loading a new map cleaned every marker away",
        not lm._markers,
        f"{len(lm._markers)} markers survived the map change",
    )
    check(
        "the health bar did not survive the map change",
        bb._tracked is None,
        f"tracking {bb._tracked}",
    )
    restore()
    check(
        "everything this file changed has been put back",
        bb._show is not None and not state["originals"] and not state["options"],
        "settings restored and the counters taken off",
    )
    state["phase"] = 0
    print("\nRestored. Run phase 1 again to start over.")

summary()
