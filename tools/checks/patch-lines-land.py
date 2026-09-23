# Did every patch line land? - the read-back audit for ticket 49 (core._run, patchset.py)
# Run: ASK_TIMEOUT=120 bash bl2-mcp/tools/ask.sh bl2-mcp/tools/checks/patch-lines-land.py
#
# Reads every line the pack runs back out of the game with patchset.check, which writes nothing,
# and counts landed / failed / not loaded for the two routes separately: flat lines (the console's
# own set) and array-path lines (Prop[N].Field, set from Python since ticket 49). Only the last
# line to write a property is judged; one that a later line overwrites is counted as superseded.
#
# The sentinel sandwich at the end is the red/green: 3 to 5 landed array-path lines are each moved
# to a sentinel, sent through the console (the old route: must stay at the sentinel), then through
# core._run (must come back, counted as landed). Each ends at the patch's own value again.
#
# Works at the main menu or in a map. Lines held for a map read "not loaded" anywhere else.

reset()
import collections
import html
import re

import unrealsdk
from bl2_modern import core, patchfile, patchset
from mods_base import get_pc

CAT = re.compile(r'<category name="([^"]*)"')
LEV = re.compile(r'level="([^"]*)"')
PKG = re.compile(r'package="([^"]*)"')


def labelled(feature):
    """(section, hotfix kind, command) for every line this feature's switches run."""
    wanted = feature.patch_sections()
    if wanted is None:
        return []
    text = (core.Path(core.__file__).parent / "data" / feature.patch_file).read_text(
        encoding="utf-8", errors="replace",
    )
    path, kind, out = [], None, []
    for raw in text.splitlines():
        s = raw.strip()
        if s.startswith("</BLCMM"):
            break
        c = CAT.search(s)
        if c:
            path.append(c.group(1))
        if "</category>" in s and path:
            path.pop()
        if c:
            continue
        if s.startswith("<hotfix"):
            m, p = LEV.search(s), PKG.search(s)
            kind = ("everywhere" if m.group(1) in ("None", "") else "map:" + m.group(1).lower()) if m else ("package" if p else "everywhere")
            continue
        if s.startswith("</hotfix"):
            kind = None
            continue
        if not s.startswith("<code") or patchfile.section_of(path) not in wanted:
            continue
        cmd = html.unescape(s[s.find(">") + 1 : s.rfind("</code>")]).strip()
        if cmd:
            out.append((patchfile.section_of(path), kind or "plain", cmd))
    return out


rows = []
for feature in core.all_features():
    if feature.failed is None and feature.patch_sections is not None:
        rows += [(feature.name, *row) for row in labelled(feature)]


def key(cmd):
    p = patchfile.parse_set(cmd)
    if p is None:
        return cmd.lower(), ""
    steps = ".".join(n if i is None else f"{n}[{i}]" for n, i in p[1])
    return p[0].lower(), steps.lower()


def related(a, b):
    return a == b or b.startswith((a + ".", a + "[")) or a.startswith((b + ".", b + "["))


by_obj = collections.defaultdict(list)
for i, (_f, _s, _k, cmd) in enumerate(rows):
    obj, prop = key(cmd)
    by_obj[obj].append((i, prop))

here = get_pc().WorldInfo.GetMapName(False).lower()
at_menu = here == "menumap"
judged = []
for i, (feat, sec, kind, cmd) in enumerate(rows):
    if kind.startswith("map:") and kind != "map:" + here:
        continue  # held for another map: _run does not send it until that map loads
    obj, prop = key(cmd)
    superseded = any(j > i and related(prop, q) for j, q in by_obj[obj])
    parsed = patchfile.parse_set(cmd)
    route = "array-path" if parsed and patchset.needs_python(parsed[1]) else "flat"
    verdict, why = patchset.check(cmd)
    judged.append((feat, sec, kind, route, "superseded" if superseded else verdict, why, cmd))

try:
    print(f"{len(judged)} lines read back, map {here}, {len(rows) - len(judged)} held for other maps not judged")
    by_route = collections.Counter((route, v) for _f, _s, _k, route, v, _w, _c in judged)
    for route in ("flat", "array-path"):
        print(f"   {route:10s} " + ", ".join(f"{v} {by_route[(route, v)]}" for v in ("landed", "failed", "not loaded", "superseded")))

    print("   array-path lines by section (landed / failed / not loaded / superseded):")
    per = collections.defaultdict(collections.Counter)
    for _f, sec, _k, route, v, _w, _c in judged:
        if route == "array-path":
            per[sec][v] += 1
    for sec, c in sorted(per.items(), key=lambda kv: -sum(kv[1].values())):
        print(f"      {c['landed']:5d} {c['failed']:4d} {c['not loaded']:5d} {c['superseded']:4d}  {sec[:60]}")

    failed = [row for row in judged if row[4] == patchset.FAILED]
    print(f"   every line that failed ({len(failed)}):")
    for feat, sec, _k, route, _v, why, cmd in failed:
        print(f"      [{route}] {sec[:22]} | {why[:70]} | {cmd[:110]}")

    arr = [row for row in judged if row[3] == "array-path"]
    arr_landed = sum(1 for row in arr if row[4] == patchset.LANDED)
    arr_failed = sum(1 for row in arr if row[4] == patchset.FAILED)
    check(
        "array-path lines land: not one whose object and index are there failed",
        arr_landed > 0 and arr_failed == 0,
        f"{arr_landed} landed, {arr_failed} failed of {len(arr)}",
    )
    flat = [row for row in judged if row[3] == "flat"]
    flat_landed = sum(1 for row in flat if row[4] == patchset.LANDED)
    flat_failed = sum(1 for row in flat if row[4] == patchset.FAILED)
    # The Community Patch itself has lines the engine cannot take - malformed text, a property the
    # object does not have, a clamped value; 27 at the menu on 2026-09-24. Well under 2% of the
    # flat lines that land. A console route that broke would fail hundreds.
    # Plain lines run once, at the main menu, as they do for real players; a level load reloads
    # some packages and undoes them (50 of Loot Pool's on 2026-09-24), which is what hotfixes are
    # for. So the threshold holds at the menu, and in a map the count is only reported.
    if at_menu:
        check(
            "flat lines still land through the console: under 2% of the judged ones fail",
            flat_landed > 1000 and flat_failed < 0.02 * (flat_landed + flat_failed),
            f"{flat_landed} landed, {flat_failed} failed",
        )
    else:
        plain = sum(1 for row in flat if row[4] == patchset.FAILED and row[2] == "plain")
        print(f"   in a map: {flat_failed} flat lines failed, {plain} of them plain lines (run once at the menu: the patch's own malformed ones, and those a level load undid)")

    # --- the sentinel sandwich: red through the console, green through core._run ---------------
    pc = get_pc()
    floats = []
    for _f, _s, _k, route, v, _w, cmd in arr:
        if v != patchset.LANDED:
            continue
        obj, steps, text = patchfile.parse_set(cmd)
        try:
            float(text)
        except ValueError:
            continue
        if text.strip() in ("0", "1"):  # may be a bool field, which takes no sentinel
            continue
        floats.append((obj, ".".join(n if i is None else f"{n}[{i}]" for n, i in steps), text, cmd))
        if len(floats) == 5:
            break
    red, green = [], []
    for obj, prop, text, cmd in floats:
        sentinel = f"set {obj} {prop} {float(text) + 12.25}"
        try:
            moved = patchset.run(pc, sentinel)[0] == patchset.LANDED and patchset.check(cmd)[0] == patchset.FAILED
            pc.ConsoleCommand(cmd)
            red.append(moved and patchset.check(cmd)[0] == patchset.FAILED)
            green.append(core._run([cmd]) == (1, 0, 0) and patchset.check(cmd)[0] == patchset.LANDED)
        finally:
            patchset.run(pc, cmd)  # the patch's own value, whatever happened above
    check(
        "red: through the console the same lines leave the sentinel alone",
        len(floats) >= 3 and all(red),
        f"{sum(red)} of {len(floats)} stayed at the sentinel: {[f[3][:70] for f in floats]}",
    )
    check(
        "green: through core._run they come back, counted as landed",
        len(floats) >= 3 and all(green),
        f"{sum(green)} of {len(floats)} came back",
    )

    # --- the pools ticket 43 caught -----------------------------------------------------------
    for name in ("GD_CustomItemPools_MainGame.Rewards.DigitalEdHeads", "GD_CustomItemPools_MainGame.Rewards.DigitalEdSkins",
                 "GD_CustomItemPools_Aster.Rewards.AsterHead"):
        pool = unrealsdk.find_object("Object", name)
        print(f"   {name.rsplit('.', 1)[-1]}: " + (", ".join(
            f"[{i}] {str(b.InvBalanceDefinition).split('.')[-1][:-1] or '-'} / pool {str(b.ItmPoolDefinition).split('.')[-2:]}"
            for i, b in enumerate(pool.BalancedItems)
        ) or "empty"))
except Exception:
    import traceback
    print("\n--- this file raised; the checks below this point never ran ---")
    traceback.print_exc()

summary()
