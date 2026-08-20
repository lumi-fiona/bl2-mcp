# The difficulty readout - what it says, and the one thing it must never do.
# Run: bash bl2-mcp/tools/ask.sh bl2-mcp/tools/harness.py
#      bash bl2-mcp/tools/ask.sh bl2-mcp/tools/checks/difficulty-readout.py
#
# The whole feature is arithmetic over events, so all of it is decidable here by feeding it
# events. Nothing dies, nothing travels, nothing waits.
#
# The check that matters more than the rest: asking for a readout must leave every number on the
# difficulty page exactly where it was. Every value is photographed before and compared after, in
# all four branches the suggestion can take. If that one ever comes back FAIL, the feature has
# started doing the one thing its own description promises it will not.
reset()

import re
import time

from bl2_modern import core, mod as pack
from bl2_modern.features import difficulty as D
from bl2_modern.features import difficultyreport as R
from bl2_modern.features import nightlog as N

scratch = None
was = {
    "enabled": R.enabled.value,
    "target": R.target_seconds.value,
    "slack": R.slack.value,
    "downs": R.downs_an_hour.value,
    "least": R.least_kills.value,
    "areas": {k: dict(v) for k, v in R._areas.items()},
    "downs_by": dict(R._downs),
    "began": R._began,
    "report_folder": R.FOLDER,
    # The synthetic events below go through nightlog.note, which is also what WRITES the real
    # night's log. So the log is switched off for the duration and its folder is redirected -
    # a check that quietly appends forty fake skag kills to last night's diary would be worse
    # than no check.
    "log_on": N.enabled.value,
    "log_folder": N.FOLDER,
}

# Every dial on the difficulty page, photographed. This is the list the "changes nothing" check
# compares against, and it deliberately includes the preset and the start level as well as the
# custom sliders - the readout could in principle reach any of them.
WATCHED = [D.preset, D.start_level, *D.CUSTOM_SLIDERS]


def photograph():
    return {o.identifier: o.value for o in WATCHED}


ORIGINAL = photograph()


def feed(kills, seconds, where="CheckLand_P", downs=0, who="Lumi"):
    """Push synthetic events through the exact path a real night takes."""
    # `where` has to be passed through: note() stamps the real current map and only a field of
    # the same name overrides it (nightlog.py:214-215). Without this the events landed under
    # whatever map the game was actually in, and the check looked for an area that never existed.
    for _ in range(kills):
        N.note("killed", where=where, what="Skag", by=who, took_seconds=seconds)
    for _ in range(downs):
        N.note("went down", where=where, who=who)


def wipe():
    R._areas.clear()
    R._downs.clear()
    R._began = time.time() - 3600.0  # exactly one hour, so downs-an-hour is the downs count


try:
    # --- wired in, and wired in the way it claims -------------------------------------------
    feature = next((f for f in core.all_features() if f.name == "Difficulty readout"), None)
    check(
        "the difficulty readout loaded into the pack without failing",
        feature is not None and feature.failed is None,
        "not registered" if feature is None else (feature.failed or "registered, no failure"),
    )
    check(
        "it installs no hooks of its own - it really does ride on the night's log",
        feature is not None and feature.hooks == [],
        f"{[] if feature is None else feature.hooks}",
    )
    check(
        "it is subscribed to the night's log exactly once, so nothing is counted twice",
        [listener for listener in N.LISTENERS if listener is R._heard] == [R._heard],
        f"{sum(1 for listener in N.LISTENERS if listener is R._heard)} subscriptions among "
        f"{len(N.LISTENERS)} listeners",
    )
    check(
        "its key is handed to the pack, so the menu can rebind or disable it",
        feature is not None and [k.identifier for k in feature.keybinds] == [R._show.identifier],
        f"{[] if feature is None else [k.identifier for k in feature.keybinds]}",
    )
    check(
        "all five settings belong to the pack that owns the settings file",
        all(
            o.mod is pack
            for o in (R.enabled, R.target_seconds, R.slack, R.downs_an_hour, R.least_kills)
        ),
        f"{[getattr(o.mod, 'name', None) for o in (R.enabled, R.target_seconds, R.slack, R.downs_an_hour, R.least_kills)]}",
    )

    # --- the readout is written to a scratch folder, not next to the real logs ----------------
    scratch = N.FOLDER.parent / "nights-check-readout"
    R.FOLDER = scratch
    N.FOLDER = scratch
    N.enabled.value = False
    R.enabled.value = True
    R.target_seconds.value = 4
    R.slack.value = 40
    R.downs_an_hour.value = 6
    R.least_kills.value = 25

    # --- events actually reach the tally --------------------------------------------------------
    wipe()
    feed(30, 8.0)
    check(
        "kills recorded by the night's log arrive in the readout's tally",
        R._areas.get("CheckLand_P", {}).get("kills") == 30,
        f"{R._areas}",
    )
    check(
        "the middle kill time is what was fed in, not an average of nothing",
        abs(R._middle(R._areas["CheckLand_P"]["times"]) - 8.0) < 0.01,
        f"{R._middle(R._areas['CheckLand_P']['times'])}",
    )

    # --- an area with too few kills is left out of the opinion -----------------------------------
    wipe()
    feed(5, 30.0)
    advice, _evidence = R._suggestion()
    check(
        "five kills in an area is not enough to have an opinion about",
        "Nothing to go on yet" in advice,
        advice,
    )

    # --- slow enemies -> suggest lowering enemy health --------------------------------------------
    wipe()
    feed(40, 20.0)
    advice, evidence = R._suggestion()
    check(
        "enemies taking twenty seconds against a target of four asks for enemy health to come down",
        "enemy health" in advice and "20.0 seconds" in advice,
        advice,
    )
    proposed = int(re.search(r"Try (\d+)", advice).group(1))
    check(
        "the number it suggests is genuinely lower than what is set now",
        proposed < int(D.custom_health.value),
        f"suggested {proposed}, currently {int(D.custom_health.value)}",
    )

    # --- fast enemies -> suggest raising it --------------------------------------------------------
    wipe()
    feed(40, 0.5)
    advice, _evidence = R._suggestion()
    raised = int(re.search(r"Try (\d+)", advice).group(1))
    check(
        "enemies dying in half a second asks for enemy health to go up",
        "enemy health" in advice and raised > int(D.custom_health.value),
        f"{advice} -> {raised} against {int(D.custom_health.value)}",
    )

    # --- being flattened wins over kill times -------------------------------------------------------
    wipe()
    feed(40, 20.0, downs=12)
    advice, _evidence = R._suggestion()
    check(
        "going down twelve times an hour changes the subject to how hard enemies hit",
        "enemy damage" in advice and "enemy health" not in advice,
        advice,
    )

    # --- inside the band, say nothing ----------------------------------------------------------------
    wipe()
    feed(40, 4.0)
    advice, _evidence = R._suggestion()
    check(
        "enemies landing on the target time produce no suggestion at all",
        advice.startswith("Nothing to change"),
        advice,
    )

    # --- ONE number, never two -------------------------------------------------------------------------
    for kills, seconds, downs in ((40, 20.0, 0), (40, 0.5, 0), (40, 20.0, 12), (40, 4.0, 0)):
        wipe()
        feed(kills, seconds, downs=downs)
        advice, _evidence = R._suggestion()
        named = sum(1 for phrase in ("enemy health", "enemy damage", "enemy shields") if phrase in advice)
        check(
            f"at {kills} kills of {seconds}s with {downs} downs it names at most one number",
            named <= 1,
            f"named {named}: {advice}",
        )

    # --- THE ONE THAT MATTERS: it changes nothing --------------------------------------------------------
    before = photograph()
    for kills, seconds, downs in ((40, 20.0, 0), (40, 0.5, 0), (40, 20.0, 12), (40, 4.0, 0)):
        wipe()
        feed(kills, seconds, downs=downs)
        R._suggestion()
        R.report()
    after = photograph()
    moved = {k: (before[k], after[k]) for k in before if before[k] != after[k]}
    check(
        "asking for a readout leaves every single number on the difficulty page exactly as it was",
        not moved,
        f"MOVED: {moved}" if moved else f"all {len(before)} difficulty settings unchanged",
    )
    check(
        "the readout says out loud, every time, that it has changed nothing",
        "changed nothing" in R.report(),
        R.report()[-160:],
    )

    # --- the preset warning -------------------------------------------------------------------------------
    was["preset"] = D.preset.value
    D.preset.value = "UVHM"
    wipe()
    feed(40, 20.0)
    with_preset = R.report()
    D.preset.value = "Custom"
    on_custom = R.report()
    D.preset.value = was["preset"]
    check(
        "on a preset, the readout says those numbers are not even in use",
        "does not read those numbers" in with_preset,
        with_preset,
    )
    check(
        "on Custom, it does not say that",
        "does not read those numbers" not in on_custom,
        on_custom,
    )

    # --- with the night's log switched off, say so rather than reporting a flawless night -----------------
    live_before = N.on_kill.get_active_count()
    N.on_kill.disable()
    silent = R.report()
    N.on_kill.enable()
    check(
        "with the night's log hooks off, the readout says it has been watching nothing",
        "switched off" in silent,
        silent,
    )
    check(
        "the night's log hooks were put back on afterwards",
        N.on_kill.get_active_count() == live_before,
        f"{N.on_kill.get_active_count()} of {live_before}",
    )

    # --- the readout survives a broken difficulty page -----------------------------------------------------
    real_health = D.custom_health
    try:
        del D.custom_health
        wipe()
        feed(40, 20.0)
        escaped = None
        try:
            fallback = R._suggestion()[0]
        except Exception as ex:
            escaped, fallback = ex, ""
    finally:
        D.custom_health = real_health
    check(
        "a missing difficulty slider costs the readout its exact number, not the readout",
        escaped is None and "Custom: enemy health" in fallback,
        f"{escaped!r}" if escaped else fallback,
    )

    # --- a broken event never reaches the game ----------------------------------------------------------
    escaped = None
    try:
        R._heard({})
        R._heard({"kind": "killed", "took_seconds": "not a number"})
        R._heard({"kind": "went down"})
    except Exception as ex:
        escaped = ex
    check(
        "an event with missing or nonsense fields does not throw out of the listener",
        escaped is None,
        f"{escaped!r}" if escaped else "three malformed events survived",
    )

finally:
    if scratch is not None and scratch.is_dir():
        for path in sorted(scratch.glob("*")):
            try:
                path.unlink()
            except Exception:
                pass
        try:
            scratch.rmdir()
        except Exception:
            pass

    R.FOLDER = was["report_folder"]
    N.FOLDER = was["log_folder"]
    N.enabled.value = was["log_on"]
    R.enabled.value = was["enabled"]
    R.target_seconds.value = was["target"]
    R.slack.value = was["slack"]
    R.downs_an_hour.value = was["downs"]
    R.least_kills.value = was["least"]
    R._areas.clear()
    R._areas.update(was["areas"])
    R._downs.clear()
    R._downs.update(was["downs_by"])
    R._began = was["began"]
    if "preset" in was:
        D.preset.value = was["preset"]

    check(
        "everything this file changed has been put back",
        R.enabled.value == was["enabled"]
        and R.target_seconds.value == was["target"]
        and R.least_kills.value == was["least"]
        and R._areas == was["areas"]
        and R._downs == was["downs_by"]
        and N.enabled.value == was["log_on"]
        and N.FOLDER == was["log_folder"]
        and photograph() == ORIGINAL
        and (scratch is None or not scratch.exists()),
        f"areas={len(R._areas)} downs={len(R._downs)} target={R.target_seconds.value} "
        f"difficulty moved: {[k for k in ORIGINAL if ORIGINAL[k] != photograph()[k]]}",
    )

summary()
