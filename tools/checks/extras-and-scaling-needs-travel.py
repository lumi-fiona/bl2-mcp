# Extras and level scaling - the claims that need a map change or time to pass.
# Claims covered: extras.md #4 (the map-gated text fixes actually run) and #6's behaviour half
# (dying costs 1% of your money); level-scaling.md #2 (the untouched game ships 1.13), #7 (the
# change survives a level load) and #9 (enemies and gear move together).
#
# ONE file, run over and over. It remembers where it got to in SCALE_TRIP, which lives in the
# bridge's scope between requests. The operator runs exactly this, from the game folder:
#
#   # optional, for level-scaling claim 2 only: relaunch with steal_focus=False and run PHASE 0
#   # at the title screen, BEFORE the main menu appears. Otherwise start with a character loaded.
#   bash bl2-mcp/tools/ask.sh bl2-mcp/tools/checks/extras-and-scaling-needs-travel.py   # PHASE 0
#   sleep 60                                                                  # the map loads
#   bash bl2-mcp/tools/ask.sh bl2-mcp/tools/checks/extras-and-scaling-needs-travel.py   # PHASE 1
#   sleep 60
#   bash bl2-mcp/tools/ask.sh bl2-mcp/tools/checks/extras-and-scaling-needs-travel.py   # PHASE 2
#   sleep 60
#   bash bl2-mcp/tools/ask.sh bl2-mcp/tools/checks/extras-and-scaling-needs-travel.py   # PHASE 3
#   # PHASES 4 and 5 KILL YOUR CHARACTER on purpose, to price a death. Stop here if you would
#   # rather not. No gear is lost - the money is measured and handed straight back.
#   bash bl2-mcp/tools/ask.sh bl2-mcp/tools/checks/extras-and-scaling-needs-travel.py   # PHASE 4
#   sleep 40                                                    # bleed out, then the New-U
#   bash bl2-mcp/tools/ask.sh bl2-mcp/tools/checks/extras-and-scaling-needs-travel.py   # PHASE 5
#
# To redo a phase, or to fix a station name this guessed wrong, send a one-line request:
#   SCALE_TRIP["phase"] = 1                 # go back
#   SCALE_TRIP["there"] = "ice_"            # the Three Horns Valley station's name
#   SCALE_TRIP["home"]  = "sanctuary"       # somewhere to bounce off so enemies respawn
# PHASE 0 prints every station the game knows, so the right spelling is in that output.
#
# The slider is moved to 105, then 100, and put back in PHASE 3. There is no finally that can
# put it back sooner: the whole point is that it stays changed BETWEEN requests, across a map
# load. Every phase therefore prints the one line that restores it by hand.

reset()

import pathlib

import unrealsdk

from bl2_modern import core
from bl2_modern.features import extras as E
from bl2_modern.features import grinder as G
from bl2_modern.features import levelscaling as LS
from bl2_modern.patchfile import commands_from

try:
    SCALE_TRIP
except NameError:
    SCALE_TRIP = {"phase": 0, "there": "ice_", "home": "sanctuary"}

PHASE = SCALE_TRIP["phase"]
HIGH = 105  # deliberately not 113: a level load that RESET the constant would land on 113 and
LOW = 100   # look exactly like one that carried 113 through, which would prove nothing.


def _where():
    try:
        return where()
    except Exception:
        return "(no controller yet)"


def _constant():
    try:
        return float(
            unrealsdk.find_object("ConstantAttributeValueResolver", LS.TARGET).ConstantValue,
        )
    except Exception as ex:
        print(f"   the scaling object cannot be read: {ex!r}")
        return None


def _station_named(fragment):
    """The station whose name contains this, or None with the real list printed."""
    names = sorted(stations())
    hits = [n for n in names if fragment.lower() in n.lower()]
    if not hits:
        print(f"   no station matching {fragment!r}. Stations: {names}")
        return None
    if len(hits) > 1:
        print(f"   {len(hits)} stations match {fragment!r}, taking {hits[0]!r} of {hits}")
    return hits[0]


def _stage_of(pawn):
    for attempt in ("GetGameStage", "GameStage"):
        try:
            value = getattr(pawn, attempt)
            return int(value() if callable(value) else value)
        except Exception:
            continue
    return -1


def _max_health(pawn):
    for attempt in ("GetMaxHealth", "HealthMax"):
        try:
            value = getattr(pawn, attempt)
            value = value() if callable(value) else value
            if value:
                return float(value)
        except Exception:
            continue
    return 0.0


def _enemy_buckets():
    """
    Live enemies grouped by (what they are, what stage they spawned at) -> their max healths.

    Grouped rather than listed because the same map hands back a different set of pawns on
    every visit; only buckets that appear on both visits can be compared at all.
    """
    buckets = {}
    for pawn in unrealsdk.find_all("WillowAIPawn"):
        if pawn.Name.startswith("Default__"):
            continue
        try:
            if float(pawn.Health) <= 0:
                continue
        except Exception:
            continue
        health = _max_health(pawn)
        if health <= 0:
            continue
        try:
            kind = str(pawn.AIClass.Name)
        except Exception:
            kind = str(pawn.Class.Name)
        buckets.setdefault(f"{kind}@{_stage_of(pawn)}", []).append(health)
    return buckets


def _median(numbers):
    ordered = sorted(numbers)
    return ordered[len(ordered) // 2] if ordered else 0.0


def _weapon_damage(stage, tries=12):
    """
    Median damage of `tries` rare weapons made at one game stage, under whatever the constant
    is right now. The game makes them and they are never added to anyone's backpack.
    """
    try:
        pool = unrealsdk.find_object("ItemPoolDefinition", G.POOLS[("weapon", 3)])
    except Exception as ex:
        print(f"   cannot reach the weapon pool: {ex!r}")
        return 0.0
    damages = []
    for _ in range(tries):
        for weapon in G._spawn_from_pool(pc(), pool, stage):
            try:
                damage = float(weapon.InstantHitDamage)
            except Exception:
                damage = 0.0
            if damage > 0:
                damages.append(damage)
    return _median(damages)


def _sample(label):
    """Enemy health and weapon damage measured together, at one stage, in one map."""
    buckets = _enemy_buckets()
    stages = [
        int(key.rsplit("@", 1)[-1])
        for key in buckets
        if key.rsplit("@", 1)[-1].lstrip("-").isdigit()
    ]
    stage = int(_median(stages)) if stages else level()
    damage = _weapon_damage(stage)
    print(
        f"   {label}: {len(buckets)} enemy buckets, stage {stage}, "
        f"median weapon damage {damage:.0f}",
    )
    return {"buckets": buckets, "stage": stage, "damage": damage}


# The three Ice_P text fixes the pack held back, read out of the same file the pack read.
_TEXT = (pathlib.Path(core.__file__).parent / "data" / "extras.txt").read_text(
    encoding="utf-8", errors="replace",
)
# Only the Text Fixes section, and only if it is switched on. ice_p also holds two
# DLC-scaling numbers whose objects do not even exist on this map, and reading those back is
# not what this claim is about - measured 2026-08-20: the count read "3 of 5" with two
# '5.0's, while all three actual text fixes were holding fine.
_, _HOT, _ = commands_from(_TEXT, [s for s in E.wanted_sections() if s == "Text Fixes"])
ICE_COMMANDS = [c for lvl, c in _HOT if lvl.lower() == "ice_p"]


def _reads_back(command):
    """True when the object this command names already carries the value it asks for."""
    bits = command.split(None, 3)
    if len(bits) != 4:
        return False, "not a four-part set command"
    token, prop, want = bits[1], bits[2], bits[3]
    if "'" in token:
        cls, _, inner = token.partition("'")
        inner = inner.rstrip("'")
    else:
        cls, inner = "Object", token
    for attempt in (cls, "Object"):
        try:
            obj = unrealsdk.find_object(attempt, inner)
        except Exception:
            continue
        if obj is not None:
            got = str(getattr(obj, prop))
            return got.strip() == want.strip(), repr(got[:60])
    return False, f"{inner[:60]} is not loaded here"


print(f"--- PHASE {PHASE} --- map {_where()!r}, slider {LS.percent.value!r}")

try:
    if PHASE == 0:
        # Level-scaling claim 2. Only meaningful before FrontendGFxMovie:Start has fired: that
        # is the last moment the object still carries the game's own number.
        constant = _constant()
        if core._main_menu_done:
            print(
                f"   the main menu already ran, so {constant!r} is the pack's number and not "
                "the game's. Relaunch with steal_focus=False and run PHASE 0 at the title "
                "screen to check level-scaling claim 2. No check is recorded for it here.",
            )
        else:
            check(
                "the untouched game ships the per-level growth constant at 1.13",
                constant is not None and abs(constant - 1.13) < 1e-6,
                f"read {constant!r} before the main menu patch ran",
            )

        if pc() is None:
            print("   no player controller yet - load a character and run PHASE 0 again.")
        else:
            print(f"   stations: {sorted(stations())}")
            SCALE_TRIP["percent"] = LS.percent.value
            LS.percent.value = HIGH
            there = _station_named(SCALE_TRIP["there"])
            check(
                "there is a fast travel station for the map the held-back text fixes belong to",
                there is not None,
                f"matching {SCALE_TRIP['there']!r}: {there!r}",
            )
            if there:
                travel_to(there)
                SCALE_TRIP["phase"] = 1
                print(f"   left for {there!r} at {HIGH}%. Wait for the load, then run this again.")

    elif PHASE == 1:
        here = _where()
        arrived = here.lower() == "ice_p"
        check(
            "the map holding the held-back text fixes actually loaded",
            arrived,
            f"the game calls this map {here!r}",
        )

        # Level-scaling claim 7. levelscaling.py:57 says the change is re-applied on every level
        # load; there is no level-load hook in that file, so this measures what really happens.
        constant = _constant()
        check(
            "the level scaling change is still on the object after a map load",
            constant is not None and abs(constant - HIGH / 100) < 1e-5,
            f"set to {HIGH}% before travelling, reads {constant!r} after",
        )

        # Extras claim 4.
        check(
            "the map watcher noticed this map, so the commands held for it were run",
            core._map_done == "ice_p",
            f"core._map_done = {core._map_done!r}, core._by_level carries "
            f"{len(core._by_level.get('ice_p', []))} commands for ice_p",
        )
        verdicts = [_reads_back(command) for command in ICE_COMMANDS]
        check(
            "all three text fixes held for this map now read back their fixed wording",
            len(verdicts) == 3 and all(ok for ok, _seen in verdicts),
            f"{sum(1 for ok, _s in verdicts if ok)} of {len(verdicts)} - "
            f"{[seen for ok, seen in verdicts if not ok][:2]}",
        )

        if arrived:
            SCALE_TRIP["high"] = _sample(f"at {HIGH}%")
            LS.percent.value = LOW
            home = _station_named(SCALE_TRIP["home"])
            if home:
                travel_to(home)
                SCALE_TRIP["phase"] = 2
                print(f"   dropped to {LOW}% and left for {home!r}, so enemies respawn on return.")

    elif PHASE == 2:
        check(
            "the trip out of the test map worked, so the next arrival spawns fresh enemies",
            _where().lower() != "ice_p",
            f"now in {_where()!r}",
        )
        there = _station_named(SCALE_TRIP["there"])
        if there:
            travel_to(there)
            SCALE_TRIP["phase"] = 3
            print(f"   going back to {there!r} at {LOW}%. Wait for the load, then run this again.")

    elif PHASE == 3:
        high = SCALE_TRIP.get("high") or {}
        low = _sample(f"at {LOW}%")
        SCALE_TRIP["low"] = low

        shared = [key for key in low["buckets"] if key in high.get("buckets", {})]
        ratios = [
            _median(low["buckets"][key]) / _median(high["buckets"][key])
            for key in shared
            if _median(high["buckets"][key]) > 0
        ]
        enemy_ratio = _median(ratios)
        weapon_ratio = (low["damage"] / high["damage"]) if high.get("damage") else 0.0

        check(
            "the same kinds of enemy came back at both settings, so there is something to compare",
            len(shared) >= 1 and enemy_ratio > 0 and weapon_ratio > 0,
            f"{len(shared)} shared buckets of {len(low['buckets'])}: {shared[:3]}",
        )
        # Without this one, a constant that moved nothing at all would sail through the check
        # below on two ratios of 1.0.
        check(
            "lowering the constant really did shrink both enemies and gear",
            0 < enemy_ratio < 0.9 and 0 < weapon_ratio < 0.9,
            f"enemy health x{enemy_ratio:.3f}, weapon damage x{weapon_ratio:.3f} going "
            f"{HIGH}% -> {LOW}%",
        )
        check(
            "enemies and gear moved by the same factor, so relative difficulty is unchanged",
            enemy_ratio > 0 and weapon_ratio > 0 and abs(enemy_ratio - weapon_ratio) < 0.15,
            f"enemies x{enemy_ratio:.3f} against gear x{weapon_ratio:.3f}, difference "
            f"{abs(enemy_ratio - weapon_ratio):.3f}; at stage {low['stage']} the arithmetic "
            f"predicts x{(LOW / HIGH) ** max(low['stage'] - 1, 0):.4f}",
        )

        LS.percent.value = SCALE_TRIP.get("percent", LS.VANILLA_PERCENT)
        SCALE_TRIP["phase"] = 4
        print(f"   slider put back to {LS.percent.value!r}.")
        print("   PHASE 4 next, and it KILLS YOUR CHARACTER to price a death. Stop here if not.")

    elif PHASE == 4:
        SCALE_TRIP["money"] = money()
        killed = "nothing was tried"
        for attempt in ("no argument", "one argument", "Pawn.Died"):
            try:
                if attempt == "no argument":
                    pc().CausePlayerDeath()
                elif attempt == "one argument":
                    pc().CausePlayerDeath(True)
                else:
                    pc().Pawn.Died(None, None, unrealsdk.make_struct("Vector"))
            except Exception as ex:
                killed = f"{attempt} raised {ex!r}"
                continue
            killed = None
            break
        check(
            "the character can be killed on demand, which is the only way to price a death",
            killed is None,
            killed or f"carrying {SCALE_TRIP['money']} credits at the moment of death",
        )
        if killed is None:
            SCALE_TRIP["phase"] = 5
            print("   wait about 40 seconds - bleeding out, then the New-U - and run this again.")

    elif PHASE == 5:
        before = SCALE_TRIP.get("money", 0)
        after = money()
        lost = before - after
        share = (lost / before) if before else 0.0
        check(
            "dying costs 1% of the money you were carrying, not the stock 7%",
            before > 0 and abs(share - 0.01) < 0.002,
            f"{before} -> {after}, {lost} gone, {share * 100:.3f}% of what was carried",
        )
        if lost > 0:
            add_money(lost)
            print(f"   handed the {lost} credits back, now carrying {money()}")
        SCALE_TRIP["phase"] = 0
        print("   done. SCALE_TRIP is back at PHASE 0.")

    else:
        check(
            "SCALE_TRIP names a phase this file knows how to run",
            False,
            f"phase {PHASE!r} is not one of 0-5; send SCALE_TRIP['phase'] = 0 to start over",
        )

finally:
    print(
        f"   next: PHASE {SCALE_TRIP['phase']}. If you stop here, put the slider back with: "
        f"LS.percent.value = {SCALE_TRIP.get('percent', LS.percent.value)!r}",
    )

summary()
