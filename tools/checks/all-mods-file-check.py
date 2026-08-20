# The co-op file check, widened to every mod - checks for features/handshake.py
# Run: bash bl2-mcp/tools/ask.sh bl2-mcp/tools/checks/all-mods-file-check.py
#
# What is deliberately NOT here: "the announcement reaches the other player's machine" needs a
# second player, and nothing solo stands in for it. Everything below either reads this machine's
# real sdk_mods folder or hands the module a forged message exactly as the network layer would.
#
# Nothing here writes to sdk_mods. The only files this creates live in a temporary folder that is
# deleted in the finally block, and the module is pointed at that folder by replacing
# handshake.mods_folder - the same trick the existing co-op-and-handshake.py uses on Path.
reset()

import json
import pathlib
import shutil
import tempfile
import time

from bl2_modern import core
from bl2_modern.features import handshake as H

import networking.registration as netreg


class LogSpy:
    """Stands in for unrealsdk.logging inside handshake, so which branch fired is visible."""

    def __init__(self):
        self.lines = []

    def __getattr__(self, kind):
        def say(message, *_a, **_k):
            self.lines.append((kind, str(message)))

        return say

    def said(self, needle):
        return [message for _kind, message in self.lines if needle in message]

    def errors(self):
        return [message for kind, message in self.lines if kind == "error"]


# Everything this file is allowed to change, remembered before it changes any of it.
real_mods_folder = H.mods_folder
real_switched_off = H.mods_switched_off
real_max_detail = H.MAX_DETAIL
files_cache_was = H._files

tmp = None
try:
    # --- is the feature wired in at all ------------------------------------------------------
    feature = next((f for f in core.all_features() if f.name == "Version handshake"), None)
    check(
        "the version handshake loaded",
        feature is not None and feature.failed is None,
        "not registered" if feature is None else (feature.failed or "registered, no failure"),
    )
    check(
        "the handshake's announce function is carried to build_mod as a network function",
        feature is not None and any(fn is H.announce for fn in feature.network_functions),
        getattr(feature, "network_functions", None),
    )

    # --- what it actually fingerprints on this machine ----------------------------------------
    H._files = None
    files = H.mod_files()
    folder = H.mods_folder()

    on_disk = sorted(p.stem for p in folder.iterdir() if p.suffix in (".sdkmod", ".py"))
    folders = sorted(
        p.name
        for p in folder.iterdir()
        if p.is_dir() and p.name not in H.NOT_MODS and not p.name.startswith(".")
    )

    check(
        "the folder the check reads is the one the mod loader reads",
        folder.exists() and (folder / "mods_base.sdkmod").exists(),
        f"{folder}",
    )

    # Found 2026-08-20, and it broke this very file further down: mod_files() used to hand back
    # the cache itself, so anything that edited the result edited the machine's own record of
    # what is installed for the rest of the session. mods_report() then put that live dict
    # straight into the outgoing message. The symptom was a MISMATCH warning that listed nothing
    # as different, because "ours" and "theirs" had become the same object.
    handed_out = H.mod_files()
    handed_out["ThisModDoesNotExist"] = "aaaaaa"
    del handed_out[on_disk[0]]
    check(
        "editing what mod_files() hands back does not change what the machine believes",
        "ThisModDoesNotExist" not in H.mod_files() and on_disk[0] in H.mod_files(),
        f"after editing the copy, the real list says {sorted(H.mod_files())[:3]}...",
    )
    report_one = H.mods_report()
    report_one["files"]["ThisModDoesNotExist"] = "aaaaaa"
    check(
        "and the message it sends carries a copy too, not the live record",
        "ThisModDoesNotExist" not in H.mods_report()["files"],
        f"{sorted(H.mods_report()['files'])[:3]}...",
    )
    check(
        "every .sdkmod and loose .py file in sdk_mods is fingerprinted",
        all(name in files for name in on_disk),
        f"missing: {[n for n in on_disk if n not in files]} out of {len(on_disk)} files",
    )
    check(
        "every mod installed as a folder is fingerprinted too",
        all(name in files for name in folders),
        f"folders on disk {folders}, missing {[n for n in folders if n not in files]}",
    )
    check(
        "the eight bundled mods are all in the list, which is the whole point of widening this",
        all(
            name in files
            for name in (
                "AlwaysTeleportVehicles",
                "AutoPickupTweaks",
                "AutomaticReloadFix",
                "BetterUIControls",
                "CoopSaveQuit",
                "ItemLights",
                "sliding",
                "ping",
            )
        ),
        f"{sorted(files)}",
    )
    check(
        "the pack's own settings folder is not fingerprinted, because saved options are personal "
        "and are meant to differ between the two of you",
        "settings" not in files,
        f"{sorted(files)}",
    )
    check(
        "no fingerprint came back unreadable",
        all(value != "unread" for value in files.values()),
        f"{[n for n, v in files.items() if v == 'unread']}",
    )

    # --- the message that goes across the wire -------------------------------------------------
    report = H.mods_report()
    encoded = H.announce._encode_message(H.__version__, H.patch_fingerprint(), report)
    check(
        "the whole list of mods fits in one message, so the other player is told file by file",
        "files" in report,
        f"{len(encoded)} characters encoded, the module gives up on detail past {H.MAX_DETAIL}",
    )
    check(
        "that message is smaller than the module's own limit",
        len(encoded) <= H.MAX_DETAIL + 200,
        f"{len(encoded)} characters for {len(files)} mods",
    )
    check(
        "the message survives being encoded and decoded",
        json.loads(encoded)[0][2] == report,
        f"{encoded[:120]}...",
    )

    started = time.perf_counter()
    H.mods_report()
    H.mods_report()
    cost = (time.perf_counter() - started) * 1000
    check(
        "asking for the report twice on the frame a character spawns costs under 2 ms, because "
        "the fingerprints are worked out once and kept",
        cost < 2.0,
        f"{cost:.2f} ms for two reports over {len(files)} mods",
    )

    # --- telling the three kinds of difference apart --------------------------------------------
    theirs_same = {"files": dict(files), "off": list(H.mods_switched_off())}
    check(
        "two machines with the same files and the same switches have nothing to complain about",
        H.differences(theirs_same) == [],
        H.differences(theirs_same),
    )

    victim = sorted(files)[0]
    changed = {"files": dict(files), "off": list(H.mods_switched_off())}
    changed["files"][victim] = "000000"
    lines = H.differences(changed)
    check(
        "a mod whose file differs is named, and named as a different version",
        lines == [f"{victim} is a different version on the two machines"],
        lines,
    )
    check(
        "that sentence contains no hash, because a player cannot act on a hash",
        lines and "000000" not in lines[0] and files[victim] not in lines[0],
        lines,
    )

    missing = {"files": dict(files), "off": list(H.mods_switched_off())}
    del missing["files"][victim]
    missing["files"]["SomethingWeDoNotHave"] = "abcdef"
    lines = H.differences(missing)
    check(
        "a mod only one of you has is reported as missing, not as a different version",
        sorted(lines)
        == sorted([
            f"{victim} is installed on this machine and not on the other one",
            "SomethingWeDoNotHave is installed on the other machine and not on this one",
        ]),
        lines,
    )

    # The distinction the assignment turns on: same file, different switch.
    H.mods_switched_off = lambda: ["Ping!"]
    both_ways = H.differences({"files": dict(files), "off": []})
    check(
        "a mod that is merely switched off on one side is reported as switched off, and never as "
        "a different version",
        both_ways == ["Ping! is switched off here and switched on over there"],
        both_ways,
    )
    H.mods_switched_off = lambda: []
    other_way = H.differences({"files": dict(files), "off": ["Ping!"]})
    check(
        "the same difference the other way round says which machine it is switched off on",
        other_way == ["Ping! is switched off over there and switched on here"],
        other_way,
    )
    H.mods_switched_off = real_switched_off

    # --- what happens when the list is too big to send --------------------------------------------
    H.MAX_DETAIL = 10
    small = H.mods_report()
    check(
        "when the list would be too long to send, a single fingerprint goes instead of nothing",
        "all" in small and "files" not in small,
        small,
    )
    same_overall = H.differences({"all": small["all"], "off": list(H.mods_switched_off())})
    other_overall = H.differences({"all": "deadbeefcafe", "off": list(H.mods_switched_off())})
    check(
        "two machines that match still report a match in that short form",
        same_overall == [],
        same_overall,
    )
    check(
        "two machines that differ are still warned, and told to compare the folders by hand",
        len(other_overall) == 1 and "sdk_mods" in other_overall[0],
        other_overall,
    )
    H.MAX_DETAIL = real_max_detail

    # --- compiled Python must not count, or the warning becomes noise -----------------------------
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="secondwind-mods-"))
    (tmp / "FakeMod").mkdir()
    (tmp / "FakeMod" / "thing.py").write_text("x = 1", encoding="utf-8")
    (tmp / "FakeMod" / "__pycache__").mkdir()
    (tmp / "FakeMod" / "__pycache__" / "thing.cpython-314.pyc").write_bytes(b"\x00\x01")
    (tmp / "Fake.sdkmod").write_bytes(b"pretend zip")

    H.mods_folder = lambda: tmp
    H._files = None
    first = H.mod_files()
    check(
        "a folder mod and a .sdkmod in the same place are both picked up",
        sorted(first) == ["Fake", "FakeMod"],
        first,
    )

    (tmp / "FakeMod" / "__pycache__" / "thing.cpython-314.pyc").write_bytes(b"\x99" * 40)
    H._files = None
    after_pyc = H.mod_files()
    check(
        "compiled Python changing does not move the fingerprint, so two machines on different "
        "Python releases do not report a permanent false mismatch",
        after_pyc == first,
        f"{first} -> {after_pyc}",
    )

    (tmp / "FakeMod" / "thing.py").write_text("x = 2", encoding="utf-8")
    H._files = None
    after_source = H.mod_files()
    check(
        "real source changing does move it",
        after_source["FakeMod"] != first["FakeMod"],
        f"{first['FakeMod']} -> {after_source['FakeMod']}",
    )

    (tmp / "Fake.sdkmod").write_bytes(b"pretend zip, edited")
    H._files = None
    after_archive = H.mod_files()
    check(
        "a .sdkmod archive changing moves it too",
        after_archive["Fake"] != first["Fake"],
        f"{first['Fake']} -> {after_archive['Fake']}",
    )

    H.mods_folder = real_mods_folder
    H._files = None

    # --- a forged announcement, delivered exactly as the network layer would ------------------------
    IDENT = H.announce.network_identifier
    callback = netreg.registered_callbacks.get(IDENT)
    check(
        "the handshake's network function is registered, so a real message would reach it",
        callback is not None,
        f"{IDENT}",
    )

    LOCAL_PRI = None
    try:
        local = H.get_pc()
        LOCAL_PRI = local.PlayerReplicationInfo if local is not None else None
    except Exception as ex:
        LOCAL_PRI = None

    def foreign_sender():
        import unrealsdk

        for class_name in ("WillowPlayerReplicationInfo", "PlayerReplicationInfo"):
            try:
                found = list(unrealsdk.find_all(class_name))
            except Exception:
                continue
            for obj in found:
                if LOCAL_PRI is None or obj != LOCAL_PRI:
                    return obj
        return None

    def deliver(sender, *args):
        spy = LogSpy()
        real_logging = H.logging
        H.logging = spy
        try:
            message = H.announce._encode_message(*args)
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
        "a player replication info that is not this machine's could be found to forge a sender",
        stranger is not None,
        str(stranger),
    )

    MINE = (H.__version__, H.patch_fingerprint())

    spy = deliver(stranger, MINE[0], MINE[1], H.mods_report())
    check(
        "another player running the identical everything reports a match",
        bool(spy.said("another player matches")) and not spy.errors(),
        spy.lines,
    )

    theirs = H.mods_report()
    theirs["files"][victim] = "000000"
    # A name nothing on this machine can possibly have, so the sentence it produces does not
    # depend on which mods this player happens to have un-ticked today.
    theirs["off"] = ["AModNobodyHas"]
    spy = deliver(stranger, MINE[0], MINE[1], theirs)
    check(
        "a mod file that differs is reported as a mismatch even though the pack's own version "
        "and patch files match - which the old check could never notice",
        bool(spy.said("MISMATCH")),
        spy.lines[:2],
    )
    check(
        "the report names the mod that differs",
        any(victim in message and "different version" in message for message in spy.errors()),
        spy.errors(),
    )
    check(
        "the report also names the mod that is only switched off on one side, in different words",
        any("AModNobodyHas" in message and "switched off" in message for message in spy.errors()),
        spy.errors(),
    )
    check(
        "the first line still carries both machines' version and patch fingerprint, so it can be "
        "pasted at somebody as-is",
        any(
            all(part in message for part in (MINE[0], MINE[1]))
            for message in spy.said("MISMATCH")
        ),
        spy.said("MISMATCH")[:1],
    )

    # An older pack sends two values, not three. That must not raise inside the network layer.
    spy = deliver(stranger, MINE[0], MINE[1])
    check(
        "a message from a pack too old to describe its mods is handled instead of raising",
        bool(spy.said("too old")),
        spy.lines,
    )
    check(
        "and it is not on its own called a mismatch, because the version difference already is",
        not spy.said("MISMATCH"),
        spy.lines,
    )

    # The guard that stops a solo player being told another player matches.
    if LOCAL_PRI is None:
        check(
            "this machine has a live character, without which the self-delivery guard cannot be "
            "tested",
            False,
            "no player controller with a PlayerReplicationInfo - load a character and re-run",
        )
    else:
        spy = deliver(LOCAL_PRI, MINE[0], MINE[1], H.mods_report())
        check(
            "an announcement this machine sent itself is still ignored",
            not spy.lines,
            spy.lines,
        )

    # --- what a character going live actually sends -------------------------------------------------
    announced_was = H._announced
    real_announce = H.announce
    sent = []
    try:
        H.announce = lambda *args: sent.append(args)
        H._announced = False
        H.announce_on_spawn(None, None, None, None)
        check(
            "a character going live sends the version, the patch fingerprint AND the mod list",
            len(sent) == 1 and len(sent[0]) == 3 and "files" in sent[0][2],
            f"{[(a[0], a[1], sorted(a[2])) for a in sent]}",
        )
        check(
            "the mod list it sends is the real one from this machine",
            sent and sent[0][2].get("files", {}) == H.mod_files(),
            f"{len(sent[0][2].get('files', {})) if sent else 0} mods sent, "
            f"{len(H.mod_files())} on disk",
        )
    finally:
        H.announce = real_announce
        H._announced = announced_was

finally:
    H.mods_folder = real_mods_folder
    H.mods_switched_off = real_switched_off
    H.MAX_DETAIL = real_max_detail
    H._files = files_cache_was
    if tmp is not None:
        shutil.rmtree(tmp, ignore_errors=True)
    check(
        "everything this file changed has been put back",
        H.mods_folder is real_mods_folder
        and H.mods_switched_off is real_switched_off
        and H.MAX_DETAIL == real_max_detail,
        f"folder={H.mods_folder is real_mods_folder} off={H.mods_switched_off is real_switched_off} "
        f"limit={H.MAX_DETAIL}",
    )

summary()
