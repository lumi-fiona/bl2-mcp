# Core and feature registry - checks for the claims in
#   AUDIT-RAW/core-registry-options-patch-timing-map-w.md
#   AUDIT-RAW/feature-registry-list.md
#   AUDIT-RAW/developer-bridge.md
# Run: bash bl2-mcp/tools/ask.sh bl2-mcp/tools/checks/core-and-registry.py
#
# Everything here is read-only about the game world. The three things it does change - the
# module-level get_pc, one feature's `failed` mark, and a handful of pretend features pushed
# into core._features - are all put back in the finally at the bottom.

reset()

import re
import tomllib
from pathlib import Path

import bl2_modern
from bl2_modern import core, mod
from bl2_modern.features import FEATURES, bridge
from mods_base import BoolOption, NestedOption
from save_options.registration import load_callbacks, registered_save_options

_real_get_pc = core.get_pc
_injected = []          # pretend Features pushed into core._features, removed in the finally
_handshake = next((f for f in core.all_features() if f.name == "Version handshake"), None)
_hs_hook = _handshake.hooks[0] if _handshake and _handshake.hooks else None


def _pretend(name, failed=None, how_many_options=1):
    """A Feature that never came from a file, carrying one sentinel of every kind."""
    feature = core.Feature(
        name=name,
        hooks=["hook sentinel " + name],
        keybinds=["keybind sentinel " + name],
        network_functions=["network sentinel " + name],
        save_options=["save sentinel " + name],
        options=[BoolOption(f"{name} option {n}", False) for n in range(how_many_options)],
        failed=failed,
    )
    core._features.append(feature)
    _injected.append(feature)
    return feature


try:
    # --- the registry ---------------------------------------------------------------------

    check(
        "savebackup is first in the feature list, so everything after it runs on a backed-up machine",
        FEATURES[0] == "savebackup",
        f"first three are {FEATURES[:3]}",
    )
    check(
        "every name in the feature list imported, so each one is an attribute of the features package",
        all(hasattr(bl2_modern.features, name) for name in FEATURES),
        f"missing: {[n for n in FEATURES if not hasattr(bl2_modern.features, n)]}",
    )
    check(
        "each listed module registered exactly one feature",
        len(core.all_features()) == len(FEATURES),
        f"{len(core.all_features())} features registered from {len(FEATURES)} names",
    )
    check(
        "no feature failed to load",
        not [f for f in core.all_features() if f.failed is not None],
        f"failed: {[f.name for f in core.all_features() if f.failed is not None]}",
    )
    _real_count = len(core.all_features())   # before any pretend feature is pushed in

    # --- the version --------------------------------------------------------------------

    _toml = tomllib.loads(
        Path(core.__file__).with_name("pyproject.toml").read_text(encoding="utf-8"),
    )
    # Same precedence core._version() and build_mod both use: tool.sdkmod wins, project is next.
    _in_file = _toml.get("tool", {}).get("sdkmod", {}).get("version") or _toml["project"]["version"]
    check(
        "the version the pack reports, the version the mods menu shows and the version in pyproject are one number",
        core.__version__ == str(mod.version) == _in_file != "unknown",
        f"core {core.__version__!r}, menu {mod.version!r}, pyproject {_in_file!r}",
    )
    check(
        "the package itself carries the same version, which is the one the handshake compares",
        getattr(bl2_modern, "__version__", None) == core.__version__,
        f"bl2_modern.__version__ = {getattr(bl2_modern, '__version__', None)!r}",
    )

    # --- what reached build_mod ------------------------------------------------------------

    _hooks = core.all_hooks()
    check(
        "the core's own four hooks lead the hook list, without which the patch never runs",
        _hooks[:4]
        == [core.on_main_menu, core.on_loading_done, core.on_character_live, core.on_services_replaced],
        f"{len(_hooks)} hooks in total",
    )
    check(
        "every hook the core gathered is one the mod is actually holding",
        len(mod.hooks) == len(_hooks)
        and all(any(h is m for m in mod.hooks) for h in _hooks),
        f"mod holds {len(mod.hooks)}, core gathers {len(_hooks)}",
    )
    # The pack shipped with exactly one keybind (the grinder's) for a long time, and this check
    # said so literally. It has since grown a dozen more of its own accord - guncensus,
    # lootindex, museum, difficultyreport and others each earned a quick-access key as they were
    # written - so "exactly one" is now the check being stale, not the pack being wrong. What
    # still has to hold, with no count hardcoded: every keybind a feature file declares reaches
    # the built mod, and the mod holds none that did not come from a feature.
    check(
        "keybinds live in feature files and every one of them reaches the mod, with nothing "
        "gained or lost in the handoff",
        len(mod.keybinds) == len(core.all_keybinds())
        and {id(k) for k in mod.keybinds} == {id(k) for k in core.all_keybinds()},
        f"{len(core.all_keybinds())} gathered by the core, {len(mod.keybinds)} held by the mod: "
        f"{[k.identifier for k in mod.keybinds]}",
    )
    # Ticket 15 dropped the grinder's key H: the Golden Chest is the only way in. Its menu is
    # checked in grinder.py.
    _bind = next((k for k in mod.keybinds if k.identifier == "Open the grinder"), None)
    check(
        "the grinder has no keybind any more - only the Golden Chest opens it",
        _bind is None,
        f"found {getattr(_bind, 'identifier', None)!r}",
    )
    check(
        "network functions live in a feature file and still reach the mod",
        any(
            getattr(getattr(n, "__wrapped__", None), "__name__", "") == "announce"
            for n in getattr(mod, "network_functions", [])
        ),
        f"{[getattr(getattr(n, '__wrapped__', None), '__name__', n) for n in getattr(mod, 'network_functions', [])]}",
    )
    check(
        "per-character settings are registered under the pack's own id",
        bool(registered_save_options.get("bl2_modern")),
        f"ids registered: {sorted(registered_save_options)}",
    )
    # The audit calls this a suspected bug and it is exactly what this line proves: the thing
    # save_options calls after every character load is apply_all, which re-runs EVERY feature's
    # apply - including the bridge's _ready, which deletes an in-flight request.
    check(
        "loading a character re-runs every feature's apply, because apply_all is the save_options load callback",
        load_callbacks.get("bl2_modern") is core.apply_all,
        f"on_load = {getattr(load_callbacks.get('bl2_modern'), '__name__', None)!r}",
    )

    _total = len(core.all_features())
    check(
        "the status line names the version and how many features loaded",
        core.status_line() == f"Second Wind {core.__version__} - {_total} of {_total} loaded",
        core.status_line(),
    )

    # --- options: a big feature gets its own page ------------------------------------------

    _big = {
        f.name
        for f in core.all_features()
        if f.failed is None and len(f.options) >= core.GROUP_AT
    }
    _nested = {o.identifier for o in core.all_options() if isinstance(o, NestedOption)}
    check(
        "every feature with four or more settings got a page of its own, and no other feature did",
        _big == _nested and core.GROUP_AT == 4,
        f"grouped: {sorted(_nested)}",
    )

    # --- the bundled patch, and when it ran ------------------------------------------------

    check(
        "the bundled patch has already run, and it ran at the main menu",
        core._patch_has_run and core._main_menu_done,
        f"_patch_has_run={core._patch_has_run}, _main_menu_done={core._main_menu_done}",
    )
    _before = len(core._hotfixes)
    core.run_bundled_patch()   # must be a no-op the second time, or every list doubles
    _after = len(core._hotfixes)
    check(
        "asking for the bundled patch a second time does nothing at all",
        _before == _after,
        f"{_before} before, {_after} after",
    )

    _hot = core._hotfixes
    check(
        "the hotfixes were kept for the game's own hotfix service, every one a set line",
        len(_hot) > 0 and all(c.split()[0].lower() == "set" for _w, c in _hot if c.split()),
        f"{len(_hot)} hotfixes",
    )

    # Nothing hard-coded: the totals move the moment a patch section is unticked. The numbers the
    # patch runner announced to the log are compared against what it is still holding.
    _log = Path(core.__file__).parents[2] / "Binaries" / "Win32" / "Plugins" / "unrealsdk.log"
    try:
        _log_lines = _log.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception:
        _log_lines = []
    _announced = [
        re.search(
            r"Second Wind: (.+?) applied, \d+ commands run, \d+ failed; read back, \d+ landed and "
            r"\d+ are not loaded yet\. (\d+) hotfixes for the game's hotfix service: (\d+) for every "
            r"level load, (\d+) for particular maps, (\d+) for particular packages",
            line,
        )
        for line in _log_lines
    ]
    # "probe" is the throwaway Feature community-patch.py drives _run_one_patch with; its log
    # lines say nothing about what the pack itself holds.
    _announced = [m for m in _announced if m and m.group(1) != "probe"]
    _kinds = {k: sum(1 for w, _c in _hot if core._kind(w) == k) for k in ("everywhere", "map", "package")}
    check(
        "what the patch runner is still holding is exactly what it told the log it had kept",
        bool(_announced)
        and sum(int(m.group(2)) for m in _announced) == len(_hot)
        and [sum(int(m.group(i)) for m in _announced) for i in (3, 4, 5)]
        == [_kinds["everywhere"], _kinds["map"], _kinds["package"]],
        f"log: {[m.group(1) for m in _announced]} "
        f"{[sum(int(m.group(i)) for m in _announced) for i in (2, 3, 4, 5)]}; memory: "
        f"{len(_hot)} = {_kinds}"
        if _announced
        else f"no patch line in {_log} - was it deleted since the launch?",
    )

    # --- the game's own hotfix service holds them (ticket 52) -------------------------------
    _keys, _values = core._entries or ([], [])
    _service = core._hotfix_service()
    _live_keys = list(_service.Keys) if _service is not None else []
    _at = _live_keys.index(_keys[0]) if _keys and _keys[0] in _live_keys else -1
    check(
        "every hotfix is in the game's own hotfix service, after Gearbox's own and in the pack's order",
        _service is not None
        and str(_service.ServiceName) == core.MICROPATCH
        and len(_keys) == len(_hot)
        and _at >= 0
        and _live_keys[_at : _at + len(_keys)] == _keys
        and list(_service.Values)[_at : _at + len(_values)] == _values
        and len(_service.Keys) == len(_service.Values),
        f"{_service}: {len(_live_keys)} keys, the pack's {len(_keys)} start at {_at}",
    )

    def _first_field(when):
        kind = core._kind(when)
        if kind == "everywhere":
            return ""
        return when[len(core.PACKAGE):] if kind == "package" else when

    check(
        "each entry is the kind the game applies at that hotfix's moment: a package's on demand, the rest on a level load",
        all(
            k.startswith("SparkOnDemandPatchEntry-") == (core._kind(w) == "package")
            and v.split(",", 1)[0] == _first_field(w)
            and v.split(",", 3)[1:3] == c.split(None, 3)[1:3]
            for (w, c), k, v in zip(_hot, _keys, _values)
        ),
        f"{len(_keys)} entries; first three {[v[:60] for v in _values[:3]]}",
    )

    # --- one arrival per map load (ticket 05) -------------------------------------------------
    # The core's two arrival hooks driven with stand-ins: a finished map with no character yet
    # (New Game) waits for the spawn, a finished map with one (every travel, Continue) arrives at
    # once, a spawn with nothing waiting is not an arrival, and another player's controller is
    # nobody's arrival here. _arrive is swapped for a recorder so nothing reaches the game.
    class _Ctl:
        def __init__(self, address, pawn):
            self._address, self.Pawn = address, pawn

        def _get_address(self):
            return self._address

    _me, _other = _Ctl(1, None), _Ctl(2, "pawn")
    _arrivals = []
    _real_arrive = core._arrive
    core._arrive = lambda pc: _arrivals.append(pc._address)
    core.get_pc = lambda: _me
    try:
        core._arrival_pending = False
        core.on_loading_done(_me, None, None, None)          # New Game: map done, no character
        _waited = (list(_arrivals), core._arrival_pending)
        core.on_character_live(_me, None, None, None)        # ...the character spawns
        _new_game = list(_arrivals)
        _me.Pawn = "pawn"
        core.on_loading_done(_me, None, None, None)          # a fast travel
        core.on_character_live(_me, None, None, None)        # a spawn nothing waits for
        core.on_loading_done(_other, None, None, None)       # the host sees a partner's load
        _later = list(_arrivals)
    finally:
        core._arrive = _real_arrive
        core.get_pc = _real_get_pc
        core._arrival_pending = False
    check(
        "a map that finishes before the character spawns arrives at the spawn, once",
        _waited == ([], True) and _new_game == [1],
        f"after the load {_waited}, after the spawn {_new_game}",
    )
    check(
        "a map that finishes with the character there arrives at once, and nothing else is an arrival",
        _later == [1, 1],
        f"arrivals {_later}",
    )

    # --- one bad line cannot stop the rest --------------------------------------------------
    # Done against a stand-in controller rather than the real one, so not a single console
    # command reaches the game.

    class _FakeController:
        def __init__(self):
            self.seen = []

        def ConsoleCommand(self, command):
            self.seen.append(command)
            if command == "BOOM":
                raise RuntimeError("this line is broken")

    _fake = _FakeController()
    core.get_pc = lambda: _fake
    # Since ticket 49 _run reads each line back: "A" and "C" are no loaded object, so those two
    # count as not loaded; BOOM raises and counts as the one failure.
    _landed, _failed, _absent = core._run(["set A B 1", "BOOM", "set C D 2"])
    check(
        "a command that raises is counted and the commands after it still run",
        (_landed, _failed, _absent) == (0, 1, 2) and _fake.seen == ["set A B 1", "BOOM", "set C D 2"],
        f"{_landed} landed, {_failed} failed, {_absent} not loaded, saw {_fake.seen}",
    )

    # The other half of the same claim, and it does NOT hold: get_pc is called outside the
    # per-command try (core._run), so no controller means no commands at all rather than
    # one failure. This check passes while that is true.
    def _no_controller():
        raise IndexError("no local player yet")

    core.get_pc = _no_controller
    try:
        core._run(["set A B 1"])
        _escaped = False
    except Exception:
        _escaped = True
    check(
        "but with no player controller the whole batch dies as one, because get_pc sits outside the try",
        _escaped,
        "core._run - at the main menu this exception escapes into on_main_menu",
    )
    core.get_pc = _real_get_pc

    # --- marking a feature failed after load is cosmetic -------------------------------------

    if _hs_hook is not None:
        _handshake.failed = "pretend this blew up inside apply()"
        check(
            "a feature marked failed after load vanishes from all_hooks but the mod is still holding its hook",
            not any(h is _hs_hook for h in core.all_hooks())
            and any(h is _hs_hook for h in mod.hooks),
            "hooks were handed to build_mod at import - nothing unhooks them afterwards",
        )
        check(
            "the status line does name a feature that failed",
            "FAILED: Version handshake" in core.status_line(),
            core.status_line(),
        )
        _handshake.failed = None
    else:
        check("the version handshake feature is loaded and has a hook", False, "not found")

    # --- a failed feature contributes nothing ------------------------------------------------
    # The audit says this branch has never run. Here it runs, against pretend features that
    # come out again at the bottom.

    _dead = _pretend("pretend broken feature", failed="pretend traceback")
    _alive = _pretend("pretend healthy feature")

    check(
        "a failed feature's hooks, options, keybinds, network functions and save options are all left out",
        not any(h is _dead.hooks[0] for h in core.all_hooks())
        and not any(o is _dead.options[0] for o in core.all_options())
        and not any(k is _dead.keybinds[0] for k in core.all_keybinds())
        and not any(n is _dead.network_functions[0] for n in core.all_network_functions())
        and not any(s is _dead.save_options[0] for s in core.all_save_options()),
        "nothing from the pretend broken feature appears in any of the five lists",
    )
    check(
        "a healthy feature's five kinds of thing all do come through, so the check above is not passing on an empty list",
        any(h is _alive.hooks[0] for h in core.all_hooks())
        and any(o is _alive.options[0] for o in core.all_options())
        and any(k is _alive.keybinds[0] for k in core.all_keybinds())
        and any(n is _alive.network_functions[0] for n in core.all_network_functions())
        and any(s is _alive.save_options[0] for s in core.all_save_options()),
        "all five lists carry the pretend healthy feature",
    )

    _grouped = _pretend("pretend page feature", how_many_options=core.GROUP_AT)
    _flat = _pretend("pretend short feature", how_many_options=core.GROUP_AT - 1)
    _options = core.all_options()
    check(
        f"a feature with exactly {core.GROUP_AT} settings is folded into a page named after it",
        any(
            isinstance(o, NestedOption) and o.identifier == "pretend page feature"
            for o in _options
        )
        and not any(o is _grouped.options[0] for o in _options),
        f"{core.GROUP_AT} options -> one page, children not also loose in the main list",
    )
    check(
        f"a feature with {core.GROUP_AT - 1} settings keeps them in the main list instead",
        all(any(o is listed for listed in _options) for o in _flat.options)
        and not any(
            isinstance(o, NestedOption) and o.identifier == "pretend short feature"
            for o in _options
        ),
        f"{core.GROUP_AT - 1} options -> {core.GROUP_AT - 1} loose entries, no page",
    )

    # --- a feature that cannot be imported at all --------------------------------------------
    # This exercises the except branch in load_features, which the log has never shown running.
    # It proves the handler, not a genuinely broken feature file - for that, see
    # core-and-registry-files.py and the note about breaking ultrawide on purpose.

    _was = len(core._features)
    _named = len(core.all_features())
    core.load_features(["no_such_feature_this_is_a_probe"])
    _added = core._features[_was:]
    _injected.extend(_added)
    check(
        "a feature that cannot be imported is recorded as failed, with a traceback, and takes nothing else down",
        len(_added) == 1
        and _added[0].name == "no_such_feature_this_is_a_probe"
        and "ModuleNotFoundError" in (_added[0].failed or "")
        and len(core.all_features()) == _named + 1,
        f"failed with: {(_added[0].failed or '').splitlines()[-1][:80] if _added else 'nothing appended'}",
    )
    check(
        # not "FAILED: <name>" - the pretend broken feature above is in the same list, and
        # status_line joins every broken name with a comma.
        "and the status line then says so out loud",
        "FAILED:" in core.status_line()
        and "no_such_feature_this_is_a_probe" in core.status_line(),
        core.status_line(),
    )

    # take the pretend features out before looking at anything real again
    core._features[:] = [f for f in core._features if not any(f is p for p in _injected)]
    _injected.clear()
    check(
        "with the pretend features gone the registry is back to what it was",
        len(core.all_features()) == _real_count and core.status_line().endswith("loaded"),
        core.status_line(),
    )

    # --- the bridge this script arrived through ------------------------------------------------

    check(
        "the bridge is switched on and has served requests, one of which is this one",
        bridge.enabled.value is True and bridge._served >= 1,
        f"enabled={bridge.enabled.value}, {bridge._served} served, polls every {bridge.EVERY}th tick",
    )
    # The harness was exec'd by an EARLIER request, and its names are bare globals here. That is
    # only true because every request is exec'd into the same dict, which is what this compares.
    # If a future bridge handed each request a copy, this fails while everything still runs.
    check(
        "this request is running in the very dict the last one ran in, which is how state survives between requests",
        globals() is bridge._scope and bridge._scope["scope"] is bridge._scope,
        f"{len(bridge._scope)} names kept between requests, harness included: "
        f"{'check' in bridge._scope}",
    )
    # Bridge claim 9, measured rather than asserted. perf_counter only - a sleep here would
    # freeze the game, and 200 stat calls fit inside one frame with room to spare.
    import time as _clock

    _samples = []
    for _ in range(200):
        _started = _clock.perf_counter()
        bridge.REQUEST.is_file()
        _samples.append((_clock.perf_counter() - _started) * 1000.0)
    _samples.sort()
    _median = _samples[len(_samples) // 2]
    check(
        "asking the filesystem whether a request has arrived costs the game nothing measurable",
        _median < 0.2,
        f"median {_median:.3f} ms per look, worst {_samples[-1]:.3f} ms, "
        f"and it only looks every {bridge.EVERY}th tick",
    )

    _bridge_feature = next((f for f in core.all_features() if f.name == "Developer bridge"), None)
    check(
        "the bridge re-prepares its folder on every character load, which is what eats an in-flight request",
        _bridge_feature is not None
        and _bridge_feature.writes_game_data is True
        and _bridge_feature.apply is bridge._ready,
        "apply=_ready + writes_game_data means apply_all calls it again on every character load",
    )

finally:
    core.get_pc = _real_get_pc
    if _handshake is not None:
        _handshake.failed = None
    core._features[:] = [f for f in core._features if not any(f is p for p in _injected)]
    _injected.clear()
    restore()

summary()
