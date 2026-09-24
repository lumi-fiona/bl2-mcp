# Co-op rules and pause + Version handshake - checks for the claims in
#   AUDIT-RAW/co-op-rules-and-pause.md  and  AUDIT-RAW/version-handshake.md
# Run: bash bl2-mcp/tools/ask.sh bl2-mcp/tools/checks/co-op-and-handshake.py
#
# What is deliberately NOT here:
#   - "pause actually works in co-op" (co-op claim 6), "the announcement reaches the other
#     player's machine" (handshake claim 3) and "matching fingerprints mean the two machines
#     behave the same" (handshake claim 9) all need a second player. Nothing solo stands in
#     for them, so they are not faked here.
#   - bosses-regen-on-reset (claim 7) and enemies-forget-downed (claim 8) need a boss arena
#     and a real Fight For Your Life. Neither is reachable from one frame of one request.
#   - The live self-delivery round trip and the re-announce on a level load need a tick and a
#     map change: they are in co-op-and-handshake-needs-travel.py.
#
# Everything below either reads the running game or drives the feature's own code with
# forged input. Nothing here spawns, sells, or grinds an item, so no real gear is at risk.

import copy
import hashlib
import pathlib
import shutil
import tempfile
import time

import unrealsdk

import networking.registration as netreg
from bl2_modern import core
from bl2_modern.features import coopfixes as CF
from bl2_modern.features import extras as EX
from bl2_modern.features import handshake as H
from bl2_modern.gamefiles import config_dir

reset()


class LogSpy:
    """
    Stands in for unrealsdk.logging inside ONE module, so which branch fired is visible.

    handshake.py's only output is a log line, so "did the mismatch get reported" and "did the
    self-delivery guard stay quiet" are otherwise unanswerable without tailing a file.
    """

    def __init__(self):
        self.lines = []

    def __getattr__(self, kind):
        def say(message, *_a, **_k):
            self.lines.append((kind, str(message)))

        return say

    def said(self, needle):
        return [message for _kind, message in self.lines if needle in message]


PATCH = pathlib.Path(H.__file__).parent.parent / "data" / "patch.txt"
MINE = (H.__version__, H.patch_fingerprint())

# --- the fingerprint itself ---------------------------------------------------------------

try:
    # Rewritten 2026-08-20. This used to expect sha256 over patch.txt alone, which the module
    # stopped doing when extras.txt was added to the fingerprint - so the check failed for the
    # implementation being RIGHT. Every shipped patch file goes in, each preceded by its own
    # name, so renaming a file changes the answer too.
    digest = hashlib.sha256()
    for _name in H.PATCH_FILES:
        _path = PATCH.parent / _name
        if _path.exists():
            digest.update(_name.encode())
            digest.update(_path.read_bytes())
    want = digest.hexdigest()[:12]
    got = H.patch_fingerprint()
    check(
        "the patch fingerprint is sha256 over every shipped patch file, each named",
        got == want,
        f"{got} vs {want}, over {[n for n in H.PATCH_FILES]}",
    )

    started = time.perf_counter()
    H.patch_fingerprint()
    H.patch_fingerprint()
    cost = (time.perf_counter() - started) * 1000
    # The announce path hashes the file twice - handshake.py:75 to send, handshake.py:42 on
    # the message that comes straight back - on the frame the player spawns into the world.
    check(
        "hashing the patch file the two times one announce does costs under 5 ms of the frame "
        "a player spawns into",
        cost < 5.0,
        f"{cost:.1f} ms for two passes over {PATCH.stat().st_size} bytes",
    )
except Exception as ex:
    check("the patch fingerprint could be read and timed", False, repr(ex))

# --- what the fingerprint does and does not notice -----------------------------------------
#
# patch_fingerprint() builds its own path from Path(__file__), so pointing the module's Path
# at a fake handshake.py moves the whole lookup into a scratch install we can edit freely.
# Nothing under the real sdk_mods folder is touched.

tmp = pathlib.Path(tempfile.mkdtemp(prefix="secondwind-fingerprint-"))
real_Path = H.Path
real_print = H._fingerprint


def _fresh():
    """The answer is cached on purpose - the files cannot change while the game runs."""
    H._fingerprint = None
    return H.patch_fingerprint()


try:
    (tmp / "data").mkdir()
    (tmp / "data" / "patch.txt").write_bytes(b"set Foo Bar 1\n")
    (tmp / "data" / "extras.txt").write_bytes(b"set Baz Qux 2\n")
    H.Path = lambda _file, _root=tmp: _root / "features" / "handshake.py"

    check(
        "the answer is worked out once and kept, so the spawn frame never re-hashes 4 MB",
        H.patch_fingerprint() == H.patch_fingerprint() and H._fingerprint is not None,
        f"cached value {H._fingerprint}",
    )

    first = _fresh()
    (tmp / "data" / "patch.txt").write_bytes(b"set Foo Bar 9\n")
    second = _fresh()
    check(
        "the fingerprint changes when data/patch.txt changes",
        first != second,
        f"{first} -> {second}",
    )

    third = _fresh()
    (tmp / "data" / "extras.txt").write_bytes(b"set Baz Qux 3\n")
    fourth = _fresh()
    check(
        "the fingerprint changes when the pack's OTHER patch file, data/extras.txt, changes",
        third != fourth,
        f"{third} -> {fourth}",
    )

    (tmp / "data" / "patch.txt").unlink()
    (tmp / "data" / "extras.txt").unlink()
    absent = _fresh()
    check(
        "no patch file at all fingerprints as 'none' instead of raising",
        absent == "none",
        absent,
    )
finally:
    H.Path = real_Path
    H._fingerprint = real_print
    shutil.rmtree(tmp, ignore_errors=True)

ships = sorted({
    feature.patch_file
    for feature in core.all_features()
    if feature.failed is None and feature.patch_sections is not None
})
check(
    "every patch file a feature ships is one the fingerprint hashes",
    ships == sorted(H.PATCH_FILES),
    f"features declare {ships}, the fingerprint covers {sorted(H.PATCH_FILES)}",
)

# The fingerprint is a hash of file BYTES, and which sections of those bytes actually run is a
# per-machine switch kept in the settings folder - which is deliberately not hashed, because
# settings are personal. So two installs can be byte-identical and still send different game
# data to the engine.
#
# Until 2026-08-20 nothing carried that across and the two machines reported a match. The fix is
# not to fold the switches into the fingerprint - a changed hash says "something differs" and a
# player cannot act on that. The ticked section NAMES travel instead, so the warning can say
# which box to look at. Flipping one switch and asking what the other machine would be told is
# therefore the whole test.
switch = None
switch_was = None
try:
    switch_name, switch = sorted(EX._switches.items())[0]
    switch_was = switch.value
    before_sections = EX.wanted_sections()
    theirs = copy.deepcopy(H.mods_report())
    switch.value = not switch_was
    after_sections = EX.wanted_sections()
    check(
        "switching an extras section off really does change which commands this machine runs",
        before_sections != after_sections,
        f"{switch_name}: {len(before_sections)} sections -> {len(after_sections)}",
    )
    told = H.differences(theirs)
    check(
        "a patch section ticked on one machine and not the other is reported, so two machines "
        "running different commands cannot report a match",
        len(told) == 1,
        f"{switch_name} {switch_was} -> {not switch_was} gave {told}",
    )
    check(
        "and the warning names the section, because a player cannot act on a hash",
        bool(told) and switch_name in told[0],
        f"{told}",
    )
except Exception as ex:
    check("the section switches could be flipped and the handshake re-asked", False, repr(ex))
finally:
    if switch is not None:
        switch.value = switch_was

# --- receiving another player's announcement ------------------------------------------------

IDENT = H.announce.network_identifier
callback = netreg.registered_callbacks.get(IDENT)
check(
    "the handshake's network function is registered, so a real message would reach it",
    callback is not None,
    f"{IDENT}; {len(netreg.registered_callbacks)} identifiers registered",
)


def local_replication_info():
    """
    The PlayerReplicationInfo the guard compares against, read the way handshake.py reads it.

    Deliberately mods_base.get_pc rather than the harness's pc(): the guard at
    handshake.py:38-39 asks get_pc(), and testing against a different controller would prove
    something about the harness instead of about the feature.
    """
    try:
        found = H.get_pc()
    except Exception:
        return None
    return found.PlayerReplicationInfo if found is not None else None


LOCAL_PRI = local_replication_info()


def every(class_name):
    """All live objects of a class, or nothing if the game has never heard of that class."""
    try:
        return list(unrealsdk.find_all(class_name))
    except Exception:
        return []


def foreign_sender():
    """Some PlayerReplicationInfo that is not this machine's, so the self-guard cannot fire."""
    for class_name in ("WillowPlayerReplicationInfo", "PlayerReplicationInfo"):
        for obj in every(class_name):
            if LOCAL_PRI is None or obj != LOCAL_PRI:
                return obj
    return None


def deliver(sender, version, fingerprint):
    """
    Hand the module one message exactly as the network layer would, and return what it logged.

    Goes through the callback the networking package registered, not through announce()
    directly: that callback is what sets announce.sender, which is the thing the guard reads.
    """
    spy = LogSpy()
    real_logging = H.logging
    H.logging = spy
    try:
        message = H.announce._encode_message(version, fingerprint)
        if callback is not None:
            callback(sender, message)
        else:
            H.announce.sender = sender
            try:
                H.announce._decode_message_and_run(message)
            finally:
                H.announce.sender = None
    finally:
        H.logging = real_logging
    return spy


stranger = foreign_sender()
check(
    "a player replication info that is not this machine's could be found to forge a sender with",
    stranger is not None,
    str(stranger),
)

try:
    spy = deliver(stranger, "0.0.0", "deadbeefcafe")
    mismatches = spy.said("MISMATCH")
    check(
        "an announcement carrying a different version and fingerprint is reported as a mismatch",
        bool(mismatches),
        mismatches[:1] or spy.lines,
    )
    check(
        "the mismatch names both machines - this one's pack and the other's",
        bool(mismatches)
        and all(part in mismatches[0] for part in ("0.0.0", "deadbeefcafe", MINE[0], MINE[1])),
        mismatches[:1],
    )
    check(
        "the mismatch is logged at error level rather than buried in info",
        any(kind == "error" and "MISMATCH" in message for kind, message in spy.lines),
        [kind for kind, _m in spy.lines],
    )

    spy = deliver(stranger, MINE[0], MINE[1])
    check(
        "an announcement from a player running the identical pack reports a match",
        bool(spy.said("another player matches")),
        spy.lines,
    )
    check(
        "a match is not reported as an error",
        not any(kind == "error" for kind, _m in spy.lines),
        spy.lines,
    )
except Exception as ex:
    check("a forged announcement could be delivered to the module", False, repr(ex))

# The guard at handshake.py:38-40. A broadcast comes back to its own sender, so without this
# every solo player would be told another player matches.
local_pri = LOCAL_PRI
if local_pri is None:
    check(
        "this machine has a live character, without which the self-delivery guard cannot be tested",
        False,
        "no player controller with a PlayerReplicationInfo - load a character and run this again",
    )
else:
    spy = deliver(local_pri, MINE[0], MINE[1])
    check(
        "an announcement this machine sent itself is ignored, so playing alone never reports "
        "another player",
        not spy.lines,
        spy.lines,
    )

    real_get_pc = H.get_pc
    try:
        H.get_pc = lambda *_a, **_k: None
        spy = deliver(local_pri, MINE[0], MINE[1])
        check(
            "a message that arrives with no local player is not compared at all",
            not spy.said("matches") and not spy.said("MISMATCH"),
            f"{spy.lines}",
        )
        check(
            "and it says why rather than going quiet",
            bool(spy.said("no way to tell whose it was")),
            f"{spy.lines}",
        )

        # get_pc RAISES rather than returning None when there is no local player - measured
        # 2026-08-20, IndexError('no local player'). An exception escaping here would land
        # inside the network layer, which is the worst place for it.
        def _raise(*_a, **_k):
            raise IndexError("no local player")

        H.get_pc = _raise
        spy = deliver(local_pri, MINE[0], MINE[1])
        check(
            "a get_pc that raises is handled the same way, not thrown into the network layer",
            not spy.said("matches") and not spy.said("MISMATCH"),
            f"{spy.lines}",
        )
    finally:
        H.get_pc = real_get_pc

# --- announcing -----------------------------------------------------------------------------

announced_was = H._announced
real_announce = H.announce
sent = []


class FakeController:
    """Stands in for the controller the spawn hook is handed. Only its identity matters."""


try:
    H.announce = lambda *a, **k: sent.append(a)  # the message gained a third field when
    # the handshake was widened to cover every mod, so this takes whatever it is given
    H._announced = None
    first_character = FakeController()
    H.announce_on_spawn(first_character, None, None, None)
    check(
        "a character going live announces this machine's version and patch fingerprint",
        len(sent) == 1 and sent[0][:2] == MINE,
        f"{[a[:2] for a in sent]}, wanted [{MINE}]",
    )
    check(
        "and it sends the mod list with it, not just the two numbers",
        len(sent) == 1 and isinstance(sent[0][2], dict) and "sections" in sent[0][2],
        f"third field: {type(sent[0][2]).__name__ if sent else 'nothing sent'}",
    )
    # The SAME controller spawning again is one character load, not two - the hook fires more
    # than once per character and announcing on each would be a message storm.
    H.announce_on_spawn(first_character, None, None, None)
    check(
        "the same character spawning again does not announce a second time",
        len(sent) == 1,
        f"{len(sent)} messages for one character",
    )
    # A DIFFERENT controller is a different character: quitting to the menu and joining
    # somebody's game. This is the exact moment the check exists for, and a flag latched for
    # the life of the process used to make it send nothing at all.
    #
    # The latch is a TIME WINDOW now (2026-08-20): one announce per arrival, where duplicate
    # hook fires inside a few seconds are one arrival. Two real character loads are minutes
    # apart; this simulation is milliseconds apart, so the window must be aged past by hand -
    # the same lever the forced-announce above already uses.
    H._announced = False
    H.announce_on_spawn(FakeController(), None, None, None)
    check(
        "a later character load - quitting to the menu and joining a co-op game - announces again",
        len(sent) == 2,
        f"{len(sent)} messages across two character loads",
    )
finally:
    H.announce = real_announce
    H._announced = announced_was

handshake_feature = next(
    (f for f in core.all_features() if f.name == "Version handshake"), None,
)
check(
    "the version handshake loaded",
    handshake_feature is not None and handshake_feature.failed is None,
    handshake_feature.failed if handshake_feature else "no feature by that name",
)
check(
    "the handshake's announce function is carried to build_mod as a network function",
    handshake_feature is not None
    and any(fn is real_announce for fn in handshake_feature.network_functions),
    getattr(handshake_feature, "network_functions", None),
)

# --- the co-op levers, as the running engine sees them ---------------------------------------


def game_info():
    """The live GameInfo, and which route found it."""
    here = pc()
    try:
        found = here.WorldInfo.Game
        if found is not None:
            return found, "WorldInfo.Game"
    except Exception:
        pass
    for class_name in ("WillowCoopGameInfo", "WillowGameInfo"):
        live = [o for o in every(class_name) if not o.Name.startswith("Default__")]
        if live:
            return live[-1], class_name
    return None, "nothing"


info, how = game_info()
check("the game has a live GameInfo object to read the co-op levers off", info is not None, how)

if info is not None:
    for prop, wanted, sentence in (
        ("bResurrectAllPlayersWhenOneDies", CF.shared_death.value,
         "one death sends both players to New-U follows the owner's option"),
        ("bEnemiesForgetDownedPlayers", CF.forget_downed.value,
         "enemies forgetting a downed player follows the owner's option"),
        ("bBossesRegenHealthOnReset", not CF.bosses_stay_hurt.value,
         "bosses healing when the fight resets follows the owner's option"),
        ("bAdminCanPause", CF.admin_pause.value, "the host pausing follows the owner's option"),
    ):
        try:
            live_value = getattr(info, prop)
        except Exception as ex:
            live_value = f"unreadable ({ex!r})"
        check(
            f"the running game agrees that {sentence}",
            live_value == wanted,
            f"{how}.{prop} = {live_value!r}, the ini asks for {wanted!r}. The engine read the "
            f"ini at startup, so this is the value as of THIS launch - a lever flipped since "
            f"then legitimately disagrees until the next one",
        )

try:
    default_game_info = unrealsdk.find_class("GameInfo").ClassDefaultObject
    check(
        "the ini's [Engine.GameInfo] bAdminCanPause reached the class every game is built from",
        default_game_info.bAdminCanPause,
        f"GameInfo default object bAdminCanPause = {default_game_info.bAdminCanPause!r}",
    )
except Exception as ex:
    check("the GameInfo class default object could be read", False, repr(ex))

# --- the option writes the file, and puts everything else back -------------------------------

INI = config_dir() / "WillowGame.ini"


def ini_value(section, key):
    """The value of one key inside one section of the live ini, or None."""
    current = None
    for line in INI.read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            current = stripped
        elif current == section and "=" in stripped:
            name, _, value = stripped.partition("=")
            if name.strip().lower() == key.lower():
                return value.strip()
    return None


KEY = "bResurrectAllPlayersWhenOneDies"
check(
    "the ini on disk agrees with the option the owner has set right now",
    ini_value(CF.WILLOW_GAME_INFO, KEY) == ("true" if CF.shared_death.value else "false"),
    f"ini says {ini_value(CF.WILLOW_GAME_INFO, KEY)!r}, the option is {CF.shared_death.value!r}",
)
check(
    "the callback is installed as on_change_anytime, the one that actually fires",
    CF.shared_death.on_change_anytime is CF._on_change,
    f"on_change_anytime={CF.shared_death.on_change_anytime!r}",
)

death_was = CF.shared_death.value
whole_file_before = INI.read_text(encoding="utf-8", errors="replace")
try:
    CF.shared_death.value = not death_was
    check(
        "changing the option rewrites WillowGame.ini immediately rather than waiting for a launch",
        ini_value(CF.WILLOW_GAME_INFO, KEY) == ("false" if death_was else "true"),
        f"option now {CF.shared_death.value!r}, ini says "
        f"{ini_value(CF.WILLOW_GAME_INFO, KEY)!r}",
    )
    CF.shared_death.value = death_was
    check(
        "changing it back rewrites the file again",
        ini_value(CF.WILLOW_GAME_INFO, KEY) == ("true" if death_was else "false"),
        f"option back to {CF.shared_death.value!r}, ini says "
        f"{ini_value(CF.WILLOW_GAME_INFO, KEY)!r}",
    )
    check(
        "the two rewrites left every other byte of WillowGame.ini alone",
        INI.read_text(encoding="utf-8", errors="replace") == whole_file_before,
        f"{len(whole_file_before)} bytes before, "
        f"{len(INI.read_text(encoding='utf-8', errors='replace'))} after",
    )
except Exception as ex:
    check("the shared-death option could be flipped and put back", False, repr(ex))
finally:
    if CF.shared_death.value != death_was:
        CF.shared_death.value = death_was

# --- what an ini write that fails does to the option -----------------------------------------
#
# coopfixes._on_change has no try/except, and mods_base runs it from inside
# ValueOption.__setattr__ (options.py:142-153), which deletes its recursion guard with no
# try/finally. Both consequences are checked here, and both are cleaned up afterwards.


def explode(*_a, **_k):
    raise RuntimeError("pretend WillowGame.ini is missing, as gamefiles.py:114-116 does")


real_edit_ini = CF.edit_ini
raised = None
try:
    CF.edit_ini = explode
    try:
        CF.shared_death.value = not death_was
    except Exception as ex:
        raised = ex
    check(
        "an ini write that fails while changing the option is contained by the feature",
        raised is None,
        f"coopfixes.py:63-71 lets it out into mods_base: {raised!r}",
    )
    check(
        "after a failed write the option still holds what the menu now shows",
        CF.shared_death.value == (not death_was),
        f"option is {CF.shared_death.value!r} but the menu would show {not death_was!r} - "
        f"options.py:155 never runs when the callback raises",
    )
    check(
        "a failed write leaves the toggle working for the rest of the session",
        not hasattr(CF.shared_death, "_on_change_recursion_guard"),
        "the leaked _on_change_recursion_guard makes every later change to this option "
        "silently do nothing, with no error anywhere",
    )
except Exception as ex:
    check("the failed-write case could be exercised", False, repr(ex))
finally:
    CF.edit_ini = real_edit_ini
    if hasattr(CF.shared_death, "_on_change_recursion_guard"):
        del CF.shared_death._on_change_recursion_guard
    if CF.shared_death.value != death_was:
        CF.shared_death.value = death_was
    check(
        "the option is back where it started",
        CF.shared_death.value == death_was
        and not hasattr(CF.shared_death, "_on_change_recursion_guard"),
        f"{CF.shared_death.value!r}, guard left: "
        f"{hasattr(CF.shared_death, '_on_change_recursion_guard')}",
    )

# --- how the feature is wired into the core ---------------------------------------------------

coop_feature = next(
    (f for f in core.all_features() if f.name == "Co-op rules and pause"), None,
)
check(
    "the co-op rules feature loaded",
    coop_feature is not None and coop_feature.failed is None,
    coop_feature.failed if coop_feature else "no feature by that name",
)
if coop_feature is not None:
    check(
        "the core can re-run the co-op fixes when it re-applies game data",
        coop_feature.apply is not None,
        "coopfixes.py:81-86 passes no apply=, so neither core.apply_all() nor the main-menu "
        "pass at core.py:457-466 can ever run it; the only run is the one at import, before "
        "saved settings are loaded",
    )
    check(
        "the co-op fixes are marked as writing game data, so the main-menu pass includes them",
        coop_feature.writes_game_data,
        f"writes_game_data={getattr(coop_feature, 'writes_game_data', None)}",
    )

summary()
