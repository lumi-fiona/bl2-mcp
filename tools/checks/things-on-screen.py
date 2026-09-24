# Things on screen - boss bar, true damage, loot marker, gun history.
# Run: bash bl2-mcp/tools/ask.sh bl2-mcp/tools/checks/things-on-screen.py
#
# Run the harness first, once per session:
#     bash bl2-mcp/tools/ask.sh bl2-mcp/tools/harness.py
#
# Run this WITH A CHARACTER LOADED and standing somewhere ordinary, not at the main menu.
# Almost every check needs a live player controller, a live pawn and a world.
#
# NOTHING HERE WAITS. The claims that need time to pass - does a marker really follow a gun
# that is still bouncing, does the bar really appear on screen, does the item card really show
# the history when you open your backpack - are in things-on-screen-needs-travel.py, because a
# sleep inside a bridge request freezes the game rather than waiting.
#
# THE TRICK THAT MAKES THIS POSSIBLE. Every one of these features is a hook, and a hook is
# handed a WrappedStruct of the game's own arguments. WrappedStruct can be built from a
# UFunction directly, so this file builds real argument structs for TakeDamage,
# DisplayRecentDamageForPlayer, AwardCombatExperience and SetFunStats, fills them in, and calls
# each feature's hook body with them. That means these are the real fields with the real names -
# a check that passes here has genuinely proved the field exists.
#
# WHAT IT CHANGES AND PUTS BACK, all in the finally:
#   every option on all four features
#   bossbar's tracked pawn, and the bar itself is taken down
#   lootmarker's marker list and its failure count. Its one constructed definition is left in
#     place on purpose - it is built once and reused, and throwing it away would leak it.
#   gunhistory's whole remembered list
#   any weapons spawned for the test are removed from the backpack again
# It spawns its own guns with give() and never touches gear you own.

import unrealsdk
from unrealsdk.unreal import WrappedStruct

from bl2_modern.features import bossbar as bb
from bl2_modern.features import gunhistory as gh
from bl2_modern.features import lootmarker as lm
from bl2_modern.features import truedamage as td

reset()

P = pc()

LEGENDARY_POOL = "GD_Itempools.WeaponPools.Pool_Weapons_All_06_Legendary"
COMMON_POOL = "GD_Itempools.WeaponPools.Pool_Weapons_All_01_Common"

saved_options = [
    (o, o.value)
    for o in (
        bb.enabled, bb.include_badasses, bb.include_bosses,
        td.enabled, td.where, td.smallest, td.show_target,
        lm.enabled, lm.floor, lm.ding, lm.shape, lm.most_at_once,
        gh.enabled, gh.show_kills, gh.show_place, gh.remember,
    )
]
saved_history = gh.history.value
saved_owner = bb._owner
spawned = []
made_markers = []


class Log:
    """Stands in for unrealsdk.logging inside a feature and remembers what it was told."""

    def __init__(self):
        self.infos = []
        self.errors = []
        self.warnings = []

    def info(self, message):
        self.infos.append(str(message))

    def error(self, message):
        self.errors.append(str(message))

    def warning(self, message):
        self.warnings.append(str(message))

    def dev_warning(self, message):
        pass

    def misc(self, message):
        pass

    def all(self):
        return self.infos + self.errors + self.warnings


class FakePickup:
    """
    Stands in for a WillowPickup on the floor.

    The feature only ever reads three things off a pickup, so this is all a pickup needs to be.
    The item inside it is a REAL gun rolled out of a real pool, which is the half that matters -
    the rarity number has to come from the game, not from this file.
    """

    def __init__(self, item, location, mission=False):
        self.Inventory = item
        self.Location = location
        self.bIsMissionItem = mission
        self.bDeleteMe = False


def params_for(class_name, function_name):
    """A real, empty argument struct for one of the game's own functions."""
    return WrappedStruct(unrealsdk.find_class(class_name)._find(function_name))


def a_pawn():
    """Any live non-player pawn, or None if the map is empty of them."""
    mine = P.Pawn
    for pawn in find_actor("WillowPawn"):
        if pawn is not mine:
            return pawn
    return None


try:
    # ---------------------------------------------------------------------------------
    # 1. A HEALTH BAR FOR NAMED ENEMIES
    # ---------------------------------------------------------------------------------

    gri = P.WorldInfo.GRI
    check(
        "the game has somewhere to put a boss bar",
        gri is not None,
        f"GRI is {gri}",
    )
    check(
        "the game knows how to show and hide a boss bar",
        gri is not None and hasattr(gri, "InitBossBar") and hasattr(gri, "UpdateBossBarInfo"),
        "InitBossBar and UpdateBossBarInfo on the replication info",
    )

    # This map may honestly have nothing alive in it - that is an empty map, not a broken
    # feature, so it is reported as a skip rather than a fail. Everything below that needs a
    # pawn is already wrapped in `if pawn is not None`, so it skips itself along with this one.
    pawn = a_pawn()
    if pawn is None:
        print(
            "[SKIP] there is an enemy in this map to ask about   "
            "no non-player WillowPawn found here - walk somewhere with enemies, or run "
            "things-on-screen-needs-travel.py, which drives this against a real fight"
        )
    else:
        check(
            "there is an enemy in this map to ask about",
            pawn is not None,
            f"found {pawn.Name}",
        )

    if pawn is not None:
        check(
            "the game can say whether an enemy is a badass",
            hasattr(pawn, "IsChampion"),
            f"on {pawn.Class.Name}",
        )
        check(
            "the game can say whether an enemy is a named boss",
            hasattr(pawn, "IsBoss"),
            f"on {pawn.Class.Name}",
        )
        # Both answers together, so the log records what this particular pawn is.
        try:
            says = (bool(pawn.IsChampion()), bool(pawn.IsBoss()))
        except Exception as ex:
            says = ("refused", repr(ex))
        check(
            "asking an enemy what it is does not raise",
            says[0] != "refused",
            f"{pawn.Name}: badass={says[0]} boss={says[1]}",
        )

        # The bar itself. Showing and hiding are separate claims because they fail separately.
        bb._owner = None
        bb._show(pawn)
        check(
            "showing the bar keeps hold of the enemy it belongs to",
            bb._pawn() == pawn and bb._up,
            f"owner {bb._pawn()}",
        )
        check(
            "an enemy the game can read counts as alive (ticket 62: pawn.Health does not exist)",
            bb._alive(pawn) == (not pawn.IsDead()),
            f"alive={bb._alive(pawn)} dead={pawn.IsDead()}",
        )
        bb._hide()
        check(
            "hiding the bar forgets the enemy",
            bb._owner is None and not bb._up,
            "",
        )

    # The tracking rules are this file's own logic and are checked without the game's opinion,
    # by making every pawn count as named. Two objects that are not pawns are fine here - the
    # feature only ever compares them by identity.
    real_deserves = bb._deserves_a_bar
    real_show = bb._show
    shown = []
    bb._deserves_a_bar = lambda _pawn: True
    bb._show = lambda p: shown.append(p) or setattr(bb, "_owner", lambda: p) or setattr(bb, "_up", True)
    try:
        first, second = object(), object()

        bb._owner = None
        bb.enabled.value = True
        bb.on_damage.__wrapped__(first, None, None, None)
        bb.on_damage.__wrapped__(second, None, None, None)
        check(
            "hitting a second named enemy moves the bar to it (ticket 62)",
            bb._pawn() is second,
            f"{len(shown)} enemies were given the bar",
        )

        bb._owner = None
        shown.clear()
        bb.enabled.value = False
        bb.on_damage.__wrapped__(first, None, None, None)
        check(
            "switching the health bar off stops it appearing",
            bb._owner is None and not shown,
            "",
        )
    finally:
        bb._deserves_a_bar = real_deserves
        bb._show = real_show
        bb.enabled.value = True
        bb._owner = None

    # The other half of the off switch: a bar already up must come down.
    hidden = []
    real_hide = bb._hide
    bb._hide = lambda: hidden.append(1) or setattr(bb, "_owner", None)
    try:
        bb._owner = lambda: object()
        bb.enabled.value = False
        bb.on_tick.__wrapped__(P, None, None, None)
        check(
            "switching the health bar off takes down a bar that is already up",
            bool(hidden) and bb._owner is None,
            "",
        )

        # And an enemy that vanished without dying must not leave the bar stranded.
        hidden.clear()
        bb.enabled.value = True
        bb._ticks = 29
        bb._owner = lambda: None  # what a WeakPointer says once its enemy is destroyed
        bb.on_tick.__wrapped__(P, None, None, None)
        check(
            "an enemy that disappears without dying does not leave the bar on screen",
            bool(hidden),
            "",
        )
    finally:
        bb._hide = real_hide
        bb._owner = None
        bb.enabled.value = True

    # ---------------------------------------------------------------------------------
    # 2. PRINT THE REAL DAMAGE NUMBER
    # ---------------------------------------------------------------------------------

    args = params_for("WillowDamageTypeDefinition", "DisplayRecentDamageForPlayer")
    check(
        "the damage display function takes the player it is drawing for",
        "PC" in dir(args),
        f"it offers {[n for n in dir(args) if not n.startswith('_')]}",
    )
    check(
        "the damage display function carries the damage event",
        "DamageEventData" in dir(args),
        "",
    )

    event = args.DamageEventData
    check(
        "the damage event carries the true total",
        "TotalDamageForDamageType" in dir(event),
        f"it offers {[n for n in dir(event) if not n.startswith('_')]}",
    )
    check(
        "the damage event says what was hit",
        "DamagedActor" in dir(event),
        "",
    )

    real_td_log = td.logging
    td_log = Log()
    td.logging = td_log
    hud_said = []
    try:
        import ui_utils

        real_hud = ui_utils.show_hud_message
        ui_utils.show_hud_message = lambda title, msg, duration=2.5: hud_said.append(msg)
    except Exception:
        real_hud = None

    try:
        BIG = 12_345_678_901.0
        SMALL = 500.0

        def fire(damage, for_player):
            a = params_for("WillowDamageTypeDefinition", "DisplayRecentDamageForPlayer")
            a.PC = for_player
            e = a.DamageEventData
            e.TotalDamageForDamageType = float(damage)
            if pawn is not None:
                e.DamagedActor = pawn
            a.DamageEventData = e
            # TotalDamageForDamageType is a real engine float - 32 bits wide, like every UE3
            # float property, not Python's 64. MEASURED 2026-08-20: asking for 12,345,678,901
            # here, the struct actually holds 12,345,678,848 afterwards (confirmed against a
            # plain IEEE 754 single-precision round-trip outside the game). Read back what the
            # field really holds rather than trusting the number handed in, so the check that
            # follows asks for what the hook actually saw, not what this file wished it saw.
            stored = float(a.DamageEventData.TotalDamageForDamageType)
            td.on_damage_shown.__wrapped__(None, a, None, None)
            return stored

        td.enabled.value = True
        td.where.value = td.TO_LOG
        td.smallest.value = 7
        td.show_target.value = False

        td_log.infos.clear()
        stored_big = fire(BIG, P)
        check(
            "a huge hit is written down in full, not cut short",
            any(f"{stored_big:,.0f}" in line for line in td_log.infos),
            f"asked for {BIG:,.0f}; the field is a 32-bit float and only holds "
            f"{stored_big:,.0f} - the log got {td_log.infos}",
        )

        td_log.infos.clear()
        fire(SMALL, P)
        check(
            "a small hit is left out when the size limit is set high",
            not td_log.infos,
            f"the log got {td_log.infos}",
        )

        td_log.infos.clear()
        td.smallest.value = 1
        fire(SMALL, P)
        check(
            "turning the size limit down lets small hits through",
            any("500" in line for line in td_log.infos),
            f"the log got {td_log.infos}",
        )

        td_log.infos.clear()
        td.smallest.value = 7
        fire(BIG, None)
        check(
            "a damage number being drawn for somebody else is ignored",
            not td_log.infos,
            f"the log got {td_log.infos}",
        )

        td_log.infos.clear()
        td.enabled.value = False
        fire(BIG, P)
        check(
            "switching the damage readout off stops it writing anything",
            not td_log.infos,
            f"the log got {td_log.infos}",
        )

        td.enabled.value = True
        if real_hud is not None:
            hud_said.clear()
            td_log.infos.clear()
            td.where.value = td.TO_SCREEN
            fire(BIG, P)
            check(
                "choosing on screen puts the number on screen and not in the log",
                bool(hud_said) and not td_log.infos,
                f"screen got {hud_said}, log got {td_log.infos}",
            )

            hud_said.clear()
            td_log.infos.clear()
            td.where.value = td.TO_BOTH
            fire(BIG, P)
            check(
                "choosing both puts the number in both places",
                bool(hud_said) and bool(td_log.infos),
                f"screen got {hud_said}, log got {td_log.infos}",
            )

        if pawn is not None:
            td.where.value = td.TO_LOG
            td.show_target.value = True
            td_log.infos.clear()
            fire(BIG, P)
            named = td._describe(pawn, P)
            check(
                "the line says what was hit, by name",
                bool(named) and any(named in line for line in td_log.infos),
                f"called it {named!r}",
            )
            check(
                "the enemy's name is not just the object's class name",
                named and not named.startswith("WillowAIPawn"),
                f"called it {named!r}",
            )
    finally:
        td.logging = real_td_log
        if real_hud is not None:
            ui_utils.show_hud_message = real_hud

    # ---------------------------------------------------------------------------------
    # 3. A MARKER WHEN SOMETHING GOOD DROPS
    # ---------------------------------------------------------------------------------

    # The rarity numbers this feature uses are the measured ones from BL2-LOOT-POOLS.md, not
    # the ones the pool names suggest. If these ever disagree, the feature is marking the wrong
    # things and nobody would notice from looking at the screen.
    check(
        "the rarity rules use the measured numbers, not the pool names",
        lm.RARITY_FLOOR[lm.FROM_PURPLE] == 4
        and lm.RARITY_FLOOR[lm.FROM_ETECH] == 6
        and lm.RARITY_FLOOR[lm.FROM_LEGENDARY] == 7
        and lm.RARITY_FLOOR[lm.PEARL_ONLY] == 10,
        str(lm.RARITY_FLOOR),
    )

    try:
        icons = unrealsdk.find_enum("ERadarIconType")
        have_enum = True
    except Exception as ex:
        icons = None
        have_enum = False
    check(
        "the game will hand over its own list of map icon shapes",
        have_enum,
        "if this fails the feature falls back to written-down numbers, which may be wrong",
    )
    if have_enum:
        wrong = {
            name: (int(getattr(icons, name)), number)
            for name, number in lm.ICON_NUMBERS.items()
            if int(getattr(icons, name, -1)) != number
        }
        check(
            "the written-down icon numbers match the game's own",
            not wrong,
            f"disagreements (game, written down): {wrong}" if wrong else "all seven agree",
        )
        missing = [m for m in lm.ICONS.values() if not hasattr(icons, m)]
        check(
            "every icon shape offered in the menu exists in the game",
            not missing,
            f"missing: {missing}" if missing else f"all {len(lm.ICONS)} exist",
        )

    lm.shape.value = "Customisation station"
    number = lm._icon_number()
    check(
        "the chosen icon shape resolves to a number",
        isinstance(number, int) and number > 0,
        f"got {number}",
    )

    io_def = lm._def()
    check(
        "a marker definition can be built at all",
        io_def is not None,
        "this is the whole trick; if it fails there can be no markers",
    )
    if io_def is not None:
        check(
            "the marker definition carries the class the population system needs",
            getattr(io_def, "InteractiveObjectClass", None) is not None,
            f"InteractiveObjectClass is {getattr(io_def, 'InteractiveObjectClass', None)}",
        )

    masters = list(unrealsdk.find_all("WillowPopulationMaster"))
    check(
        "there is a population system to spawn a marker through",
        bool(masters) and hasattr(masters[-1], "SpawnPopulationControlledActor"),
        f"{len(masters)} population masters",
    )

    # The real spawn. This is the single most likely thing in the whole assignment to fail.
    marker = lm._spawn_marker(P.Pawn.Location)
    check(
        "a marker can actually be placed in the world",
        marker is not None,
        "see the log for the reason if this failed",
    )
    if marker is not None:
        made_markers.append(marker)
        check(
            "the marker knows how to wear a compass icon",
            hasattr(marker, "SetCompassIcon"),
            f"spawned a {marker.Class.Name}",
        )

    # The decision about what deserves a marker, driven with real guns out of real pools.
    manager = P.GetPawnInventoryManager()
    legendaries = give(LEGENDARY_POOL, level(P), 1)
    commons = give(COMMON_POOL, level(P), 1)
    spawned.extend(legendaries)
    spawned.extend(commons)
    check(
        "a legendary and a common gun could be rolled to test against",
        bool(legendaries) and bool(commons),
        f"{len(legendaries)} legendary, {len(commons)} common",
    )

    if legendaries and commons:
        good, dull = legendaries[0], commons[0]
        check(
            "the rarity of a real gun can be read",
            lm._rarity_of(FakePickup(good, P.Pawn.Location)) is not None,
            f"legendary reads {lm._rarity_of(FakePickup(good, P.Pawn.Location))}, "
            f"common reads {lm._rarity_of(FakePickup(dull, P.Pawn.Location))}",
        )

        lm.enabled.value = True
        lm.ding.value = False
        lm.floor.value = lm.FROM_LEGENDARY
        lm.most_at_once.value = 10

        lm._clear_all()
        lm.on_landed.__wrapped__(FakePickup(dull, P.Pawn.Location), None, None, None)
        check(
            "a white gun on the floor gets no marker",
            not lm._markers,
            f"{len(lm._markers)} markers",
        )

        lm.on_landed.__wrapped__(FakePickup(good, P.Pawn.Location), None, None, None)
        check(
            "a legendary on the floor gets a marker",
            len(lm._markers) == 1,
            f"{len(lm._markers)} markers",
        )

        lm._clear_all()
        lm.on_landed.__wrapped__(FakePickup(good, P.Pawn.Location, mission=True), None, None, None)
        check(
            "a mission item never gets a marker, however good it is",
            not lm._markers,
            f"{len(lm._markers)} markers",
        )

        lm._clear_all()
        lm.floor.value = lm.PEARL_ONLY
        lm.on_landed.__wrapped__(FakePickup(good, P.Pawn.Location), None, None, None)
        check(
            "asking for pearlescent only leaves ordinary legendaries unmarked",
            not lm._markers,
            f"{len(lm._markers)} markers",
        )

        lm._clear_all()
        lm.floor.value = lm.FROM_LEGENDARY
        lm.enabled.value = False
        lm.on_landed.__wrapped__(FakePickup(good, P.Pawn.Location), None, None, None)
        check(
            "switching markers off stops them appearing",
            not lm._markers,
            f"{len(lm._markers)} markers",
        )
        lm.enabled.value = True

        # One drop, marked once. This hook can fire more than once for the same item, and a
        # second marker on top of the first is an actor nothing would ever clean up.
        lm._clear_all()
        lm.most_at_once.value = 10
        twice = FakePickup(good, P.Pawn.Location)
        lm.on_landed.__wrapped__(twice, None, None, None)
        lm.on_landed.__wrapped__(twice, None, None, None)
        lm.on_landed.__wrapped__(twice, None, None, None)
        check(
            "the same drop is never marked twice over",
            len(lm._markers) == 1,
            f"{len(lm._markers)} markers after the same drop landed three times",
        )

        # The ceiling. A marker is a real actor, so an unbounded list is an actor leak.
        lm._clear_all()
        lm.most_at_once.value = 2
        for _ in range(5):
            lm.on_landed.__wrapped__(FakePickup(good, P.Pawn.Location), None, None, None)
        check(
            "the number of markers never goes past the ceiling",
            len(lm._markers) <= 2,
            f"{len(lm._markers)} markers with the ceiling set to 2",
        )

        # The second way in exists because the first one is unverified. If both fire for one
        # drop, exactly one marker must result.
        lm._clear_all()
        both = FakePickup(good, P.Pawn.Location)
        lm.on_landed.__wrapped__(both, None, None, None)
        lm.on_dropped.__wrapped__(both, None, None, None)
        check(
            "the two ways a drop is noticed do not produce two markers",
            len(lm._markers) == 1,
            f"{len(lm._markers)} markers",
        )

        # Cleanup on a map change, which is the other half of not leaking actors.
        lm.on_map_change.__wrapped__(P, None, None, None)
        check(
            "loading a new map clears every marker",
            not lm._markers,
            f"{len(lm._markers)} markers left",
        )

        # And the tick that drops a marker whose item has gone.
        lm._clear_all()
        lm.most_at_once.value = 10
        gone = FakePickup(good, P.Pawn.Location)
        lm.on_landed.__wrapped__(gone, None, None, None)
        had = len(lm._markers)
        gone.bDeleteMe = True
        lm._ticks = 29
        lm.on_tick.__wrapped__(P, None, None, None)
        check(
            "picking the item up takes its marker away",
            had == 1 and not lm._markers,
            f"had {had}, now {len(lm._markers)}",
        )

    # ---------------------------------------------------------------------------------
    # 4. THIS GUN'S HISTORY
    # ---------------------------------------------------------------------------------

    check(
        "the history is stored on this character rather than on the machine",
        gh.PER_CHARACTER,
        "if this fails, two characters share one list and the counts will be nonsense",
    )

    # Tidying map names is pure arithmetic and can be settled here outright.
    tidied = {name: gh._tidy(name) for name in ("SouthernShelf_P", "Sanctuary_P", "IceCanyon_P")}
    check(
        "an internal map name is turned into something a person would say",
        tidied["SouthernShelf_P"] == "Southern Shelf" and tidied["Sanctuary_P"] == "Sanctuary",
        str(tidied),
    )
    check(
        "this map's name comes out as something rather than nothing",
        bool(gh._here()),
        f"{where()} reads as {gh._here()!r}",
    )

    gh.enabled.value = True
    gh.show_kills.value = True
    gh.show_place.value = True
    gh.remember.value = 20
    gh.history.value = {}

    held = P.Pawn.Weapon
    check(
        "the gun in your hands can be read",
        held is not None,
        f"holding {held}",
    )
    if held is not None:
        uid = gh._uid_of(held)
        check(
            "the gun in your hands has an id to remember it by",
            uid is not None,
            f"id {uid}",
        )

        kill_args = params_for("WillowGameInfo", "AwardCombatExperience")
        check(
            "the experience function says who got the kill",
            "KillerWPC" in dir(kill_args),
            f"it offers {[n for n in dir(kill_args) if not n.startswith('_')]}",
        )

        kill_args.KillerWPC = P
        gh.on_kill.__wrapped__(None, kill_args, None, None)
        gh.on_kill.__wrapped__(None, kill_args, None, None)
        check(
            "a kill is credited to the gun that got it",
            gh._entry(uid)[0] == 2,
            f"the gun has {gh._entry(uid)[0]} kills after two kills",
        )

        other = params_for("WillowGameInfo", "AwardCombatExperience")
        other.KillerWPC = None
        gh.on_kill.__wrapped__(None, other, None, None)
        check(
            "somebody else's kill is not credited to your gun",
            gh._entry(uid)[0] == 2,
            f"the gun has {gh._entry(uid)[0]} kills",
        )

        gh.enabled.value = False
        gh.on_kill.__wrapped__(None, kill_args, None, None)
        check(
            "switching gun history off stops it counting",
            gh._entry(uid)[0] == 2,
            f"the gun has {gh._entry(uid)[0]} kills",
        )
        gh.enabled.value = True

        line = gh._line_for(held)
        check(
            "the card line says the kill count in plain words",
            "2 kills" in line,
            f"line is {line!r}",
        )
        gh.show_kills.value = False
        check(
            "turning the kill count off takes it off the card",
            "kills" not in gh._line_for(held),
            f"line is {gh._line_for(held)!r}",
        )
        gh.show_kills.value = True

    # Where a gun was found, driven through the real pickup path.
    if spawned:
        found_me = spawned[0]
        found_uid = gh._uid_of(found_me)
        gh.on_picked_up.__wrapped__(FakePickup(found_me, P.Pawn.Location), None, None, None)
        check(
            "picking a gun up remembers where you were",
            found_uid is not None and gh._entry(found_uid)[1] == gh._here(),
            f"remembered {gh._entry(found_uid)[1]!r}",
        )
        first_place = gh._entry(found_uid)[1]
        gh._store(found_uid, [gh._entry(found_uid)[0], first_place])
        gh.on_picked_up.__wrapped__(FakePickup(found_me, P.Pawn.Location), None, None, None)
        check(
            "dropping a gun and picking it up again keeps where you first found it",
            gh._entry(found_uid)[1] == first_place,
            f"still {gh._entry(found_uid)[1]!r}",
        )

    # The list must not grow without limit, and the gun you actually use must survive.
    gh.history.value = {}
    gh.remember.value = 20
    for n in range(25):
        gh._store(900000 + n, [n, "nowhere"])
    kept = gh._all()
    check(
        "the remembered list never grows past its limit",
        len(kept) <= 20,
        f"{len(kept)} guns remembered with the limit set to 20",
    )
    check(
        "the guns with the most kills are the ones kept",
        "900024" in kept and "900000" not in kept,
        f"kept ids {sorted(kept)[:3]} ... {sorted(kept)[-3:]}",
    )

    # The item card. The argument names could not be settled from disk, so this is the check
    # that says whether the probe in the feature actually finds them.
    stats_args = params_for("ItemCardGFxObject", "SetFunStats")
    field = gh._text_field(stats_args)
    check(
        "the block of text on an item card can be found by name",
        field is not None,
        f"SetFunStats offers {[n for n in dir(stats_args) if not n.startswith('_')]}, "
        f"the text was found in {field!r}",
    )

    if field is not None and held is not None:
        gh.history.value = {str(gh._uid_of(held)): [7, "Sanctuary"]}
        gh._card_item = held
        stats_args = params_for("ItemCardGFxObject", "SetFunStats")
        setattr(stats_args, field, "existing card text")
        gh.on_card_text.__wrapped__(None, stats_args, None, None)
        after = str(getattr(stats_args, field))
        check(
            "the history is added to the card without throwing away what was already there",
            "existing card text" in after and "7 kills" in after,
            f"the card text became {after!r}",
        )

        # Nothing must be added twice, and nothing must be added to a card whose item was
        # never seen - that would print the last gun's history on this gun.
        gh._card_item = None
        stats_args2 = params_for("ItemCardGFxObject", "SetFunStats")
        setattr(stats_args2, field, "another card")
        gh.on_card_text.__wrapped__(None, stats_args2, None, None)
        check(
            "a card whose gun was never seen gets no history at all",
            str(getattr(stats_args2, field)) == "another card",
            f"the card text became {getattr(stats_args2, field)!r}",
        )

    card_args = params_for("ItemCardGFxObject", "SetItemCardEx")
    check(
        "the item card function says which item it is drawing",
        "InventoryItem" in dir(card_args),
        f"it offers {[n for n in dir(card_args) if not n.startswith('_')]}",
    )

finally:
    for marker in made_markers:
        try:
            lm._drop_marker(marker)
        except Exception:
            pass
    try:
        lm._clear_all()
    except Exception:
        pass
    lm._failures = 0
    # The "said once" sets are cleared so a later run reports its probe results again rather
    # than staying silent because this run already logged them.
    for module in (bb, td, lm, gh):
        module._said.clear()

    inventory = P.GetPawnInventoryManager()
    for item in spawned:
        try:
            inventory.RemoveInventoryFromBackpack(item)
        except Exception:
            pass

    gh.history.value = saved_history
    gh._card_item = None
    bb._owner = saved_owner
    try:
        bb._hide()
    except Exception:
        pass
    for option, value in saved_options:
        option.value = value

summary()
