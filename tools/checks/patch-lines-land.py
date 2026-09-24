# Did every patch line land? - the read-back audit (tickets 49 and 52: core._run, patchset.py,
# and the game's own hotfix service)
# Run: ASK_TIMEOUT=120 bash bl2-mcp/tools/ask.sh bl2-mcp/tools/checks/patch-lines-land.py
#
# Reads the lines the pack runs back out of the game with patchset.check, which writes nothing.
#   - Plain lines run once, at the first main menu, through core._run - as BLCMM's exec does for
#     a real player. A level load reloads some packages and undoes a few, which is what hotfixes
#     are for, so the known list below is held to at the first menu of a launch and only
#     reported after that. A line the engine cannot even read (ticket 54: malformed text, a
#     property the object does not have) is the patch's own, listed but never a failure here.
#   - Hotfixes are applied by the game itself - every level's on each level load, a map's when it
#     loads, a package's when the game loads it on demand. So they are judged only in a map, and
#     only the ones in effect there (core.in_effect): a line a later one overwrites is left out.
#
# The sentinel sandwich at the end is the red/green for core._run's own route: 2 to 5 landed
# array-path lines are each moved to a sentinel, sent through the console (the old route: must
# stay at the sentinel), then through core._run (must come back, counted as landed). Each ends at
# the patch's own value again. It needs landed array-path lines, which are hotfixes, so in a map.

reset()
import collections

import unrealsdk
from bl2_modern import core, patchfile, patchset
from mods_base import get_pc

# The Community Patch's own plain lines that the engine takes but that never read back as
# written (ticket 54), measured at the first main menu on 2026-09-24: MaxParticles 0 held as 1,
# a Description the game keeps as its own text, and two effect lists. Keyed (object, property).
KNOWN_UNTAKEABLE = {
    ("gd_weap_smg.barrel.smg_barrel_dahl_bane", "weaponattributeeffects"),
    ("gd_shields.accessory.absorption_shield_skill_aequitas", "skilleffectdefinitions"),
    ("gd_attributepresentation.health.attrpresent_healthactiveregenerationrate", "description"),
    ("fx_fluidrendering_px.sph.gun_sph", "maxparticles"),
    ("fx_fluidrendering_px.sph.largegoo", "maxparticles"),
    ("fx_shared_fluids_px.fx_fluid_grass", "maxparticles"),
    ("fx_shared_fluids_px.fx_fluid_heavysmoke_px", "maxparticles"),
    ("fx_shared_fluids_px.fx_fluid_rock_px", "maxparticles"),
    ("fx_shared_fluids_px.fx_fluid_spark_px", "maxparticles"),
}
# Written again by a feature after the patch: the difficulty feature keeps its own table there.
REWRITTEN_BY_FEATURES = {("gd_playthrough3tuning.balance.balancemod_pt3", "balancemodifiers")}
# A hotfix whose object comes in after the game has applied a New Game's first map's hotfixes, so
# it reads back unapplied there - for a real player too (ticket 52, 2026-09-24).
KNOWN_LATE_OBJECT = {("gd_balance_healthanddamage.healthanddamage.init_playerskillstatuseffectdamage", "valueformula")}


def key(cmd):
    p = patchfile.parse_set(cmd)
    if p is None:
        return cmd.lower(), ""
    return p[0].lower(), ".".join(n if i is None else f"{n}[{i}]" for n, i in p[1]).lower()


def related(a, b):
    return a == b or b.startswith((a + ".", a + "[")) or a.startswith((b + ".", b + "["))


def route(cmd):
    parsed = patchfile.parse_set(cmd)
    return "array-path" if parsed and patchset.needs_python(parsed[1]) else "flat"


pc = get_pc()
here = pc.WorldInfo.GetMapName(False).lower()
at_menu = here == "menumap"
_log = core.Path(core.__file__).parents[2] / "Binaries" / "Win32" / "Plugins" / "unrealsdk.log"
first_menu = at_menu and "Second Wind: arrived in " not in _log.read_text(encoding="utf-8", errors="replace")

# Plain lines, in file order, from the files the pack runs.
plain = []
for feature in core.all_features():
    if feature.failed is not None or feature.patch_sections is None:
        continue
    wanted = feature.patch_sections()
    if wanted is None:
        continue
    text = (core.Path(core.__file__).parent / "data" / feature.patch_file).read_text(
        encoding="utf-8", errors="replace",
    )
    plain += patchfile.commands_from(text, wanted)[0]
later = collections.defaultdict(list)
for i, cmd in enumerate(plain):
    later[key(cmd)[0]].append((i, key(cmd)[1]))
judged_plain = []
for i, cmd in enumerate(plain):
    obj, prop = key(cmd)
    if any(j > i and related(prop, q) for j, q in later[obj]):
        continue  # a later plain line writes it again
    verdict, why = patchset.check(cmd)
    judged_plain.append((verdict, why, cmd))

hot = [] if at_menu else core.in_effect(pc, here)
judged_hot = []
for when, cmd in hot:
    verdict, why = patchset.check(cmd)
    judged_hot.append((core._kind(when), when, verdict, why, cmd))

try:
    by = collections.Counter(v for v, _w, _c in judged_plain)
    print(f"{len(judged_plain)} plain lines read back in {here}: landed {by[patchset.LANDED]}, "
          f"failed {by[patchset.FAILED]}, not loaded {by[patchset.ABSENT]}")
    plain_failed = [(key(c), why, c) for v, why, c in judged_plain if v == patchset.FAILED]
    unreadable = [f for f in plain_failed if not f[1].startswith("the value read back")]
    mismatched = [f for f in plain_failed if f[1].startswith("the value read back")]
    unknown = [(k, why, c) for k, why, c in mismatched if k not in KNOWN_UNTAKEABLE | REWRITTEN_BY_FEATURES]
    print(f"   {len(unreadable)} plain lines the engine cannot read at all, the patch's own (ticket 54): "
          f"{[(why[:40], c[:60]) for _k, why, c in unreadable[:3]]}")
    if first_menu:
        check(
            "plain lines land through the console: the only ones reading back wrong are the patch's own known ones",
            by[patchset.LANDED] > 1000 and not unknown,
            f"{by[patchset.LANDED]} landed, {len(mismatched)} read back wrong, {len(unknown)} of them not on "
            f"the known list: {[(why[:50], c[:90]) for _k, why, c in unknown[:4]]}",
        )
    else:
        print(f"   after a level load: {len(mismatched)} plain lines read back wrong, {len(unknown)} of them not "
              f"on the known list (run once at the first menu; a level load undoes some): "
              f"{[c[:80] for _k, _w, c in unknown[:3]]}")

    if at_menu:
        print(f"   hotfixes are not judged at the main menu: the game applies them on level loads "
              f"and package loads ({len(core._hotfixes)} in its hotfix service)")
    else:
        kinds = collections.defaultdict(collections.Counter)
        for kind, _w, v, _why, _c in judged_hot:
            kinds[kind][v] += 1
        for kind in ("everywhere", "map", "package"):
            c = kinds[kind]
            print(f"   {kind:10s} hotfixes in effect: landed {c[patchset.LANDED]}, failed {c[patchset.FAILED]}, "
                  f"not loaded {c[patchset.ABSENT]}")
        packages = collections.Counter(w for kind, w, v, _why, _c in judged_hot if kind == "package" and v == patchset.LANDED)
        print(f"   package lines landed, by package: {dict(packages)}")
        hot_failed = [(key(c), why, c) for _k, _w, v, why, c in judged_hot if v == patchset.FAILED]
        hot_unknown = [(k, why, c) for k, why, c in hot_failed if k not in KNOWN_LATE_OBJECT]
        check(
            "every hotfix the game has applied here reads back as asked",
            sum(kinds[k][patchset.LANDED] for k in kinds) > 1000 and not hot_unknown,
            f"{len(hot_failed)} failed, {len(hot_unknown)} not known: "
            f"{[(why[:50], c[:90]) for _k, why, c in hot_unknown[:4]]}",
        )
        arr = [(k, w, v, why, c) for k, w, v, why, c in judged_hot if route(c) == "array-path"]
        arr_landed = sum(1 for r in arr if r[2] == patchset.LANDED)
        arr_failed = sum(1 for r in arr if r[2] == patchset.FAILED and key(r[4]) not in KNOWN_LATE_OBJECT)
        check(
            "array-path hotfixes land: the game's hotfix service reaches inside arrays and structs",
            arr_landed > 0 and arr_failed == 0,
            f"{arr_landed} landed, {arr_failed} failed of {len(arr)}",
        )

        # --- the sentinel sandwich: red through the console, green through core._run ---------
        floats = []
        for _k, _w, v, _why, cmd in arr:
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
            len(floats) >= 2 and all(red),
            f"{sum(red)} of {len(floats)} stayed at the sentinel: {[f[3][:70] for f in floats]}",
        )
        check(
            "green: through core._run they come back, counted as landed",
            len(floats) >= 2 and all(green),
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
