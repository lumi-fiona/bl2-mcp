# Small things fly to you - checks for features/vacuum.py
# Run: bash bl2-mcp/tools/ask.sh bl2-mcp/tools/checks/small-things-vacuum.py
#
# The important half of this file is the gear exclusion, and it is checked against REAL items
# spawned for the purpose - a gun, a shield, a grenade mod, a class mod and a relic - each of
# which must be refused. They are taken back in the finally. Nothing you own is touched: the
# cleanup only ever removes ids this script spawned and that were not already on the character.
#
# The sweep itself is driven against stand-in pickups, so no real item on the floor moves.
reset()

import unrealsdk
from bl2_modern.features import vacuum as W

p = pc()
manager = p.GetPawnInventoryManager() if p is not None else None
lvl = level(p) if p is not None else 1

was_enabled = W.enabled.value
was_distance = W.distance.value
was_guest = W.on_guest.value
was_diagnose = W.diagnose.value
was_switches = {name: option.value for name, option in W.switches.items()}
_ticks_before = W._ticks
real_sweep = W.sweep

pre_uids = set()
for _item in backpack():
    try:
        pre_uids.add(int(_item.DefinitionData.UniqueId))
    except Exception:
        pass
mine = set()


def _uid(item):
    try:
        return int(item.DefinitionData.UniqueId)
    except Exception:
        return None


# --- stand-ins for the world -------------------------------------------------------------


class _Vec(object):
    def __init__(self, x=0.0, y=0.0, z=0.0):
        self.X = float(x)
        self.Y = float(y)
        self.Z = float(z)


class _Cls(object):
    def __init__(self, name):
        self.Name = name


class _Def(object):
    def __init__(self, path, cls="UsableItemDefinition"):
        self._path = path
        self.Class = _Cls(cls)

    def _path_name(self):
        return self._path


class _Data(object):
    def __init__(self, definition):
        self.ItemDefinition = definition


class _Inv(object):
    """Stands in for the inventory object hanging off a pickup."""

    def __init__(self, path, cls="WillowUsableItem", item_name="", def_cls="UsableItemDefinition"):
        self.Class = _Cls(cls)
        self.DefinitionData = _Data(_Def(path, def_cls))
        self.ItemName = item_name


class _Pickup(object):
    def __init__(self, inventory, x=0.0, mission=False, pickupable=True):
        self.Inventory = inventory
        self.Location = _Vec(x, 0.0, 0.0)
        self.bIsMissionItem = mission
        self.bPickupable = pickupable


class _World(object):
    def __init__(self, pickups):
        self.PickupList = list(pickups)


class _PC(object):
    """A controller that records what it was asked to pick up, and removes it."""

    def __init__(self, world, at=0.0, net_mode=0, takes=1):
        self._world = world
        self.Pawn = type("Pawn", (), {"Location": _Vec(at, 0.0, 0.0)})()
        self.WorldInfo = type("WorldInfo", (), {"NetMode": net_mode})()
        self.asked = []
        self.takes = takes

    def GetWillowGlobals(self):
        return self._world

    def PickupPickupable(self, pickup, ready):
        self.asked.append(pickup)
        for _ in range(self.takes):
            if self._world.PickupList:
                self._world.PickupList.pop(0)


AMMO = "GD_Ammodrops.Pickups.AmmoDrop_Assault_Rifle_Bullets"
MONEY = "GD_Currency.A_Item.Currency"
ERIDIUM = "GD_Currency.A_Item.EridiumStick"
VIAL = "GD_BuffDrinks.A_Item.BuffDrink_HealingInstant"

try:
    # --- the whitelist against the game's own object paths --------------------------------
    #
    # These five paths are copied out of AutoPickupTweaks, which is installed and working. If the
    # game does not have an object at one of them, the whole category is dead and this says so.
    for label, path, wanted in (
        ("assault rifle ammo", AMMO, "ammo"),
        ("boss ammo", "GD_Ammodrops.Pickups_BossOnly.AmmoDropBoss_Shotgun_Shells", "ammo"),
        ("a money bag", MONEY, "money"),
        ("a big money bag", "GD_Currency.A_Item.Currency_Big", "money"),
        ("an eridium stick", ERIDIUM, "eridium"),
        ("an eridium bar", "GD_Currency.A_Item.EridiumBar", "eridium"),
        ("a health vial", VIAL, "vials"),
    ):
        try:
            real = unrealsdk.find_object("UsableItemDefinition", path)
            real_path = str(real._path_name())
        except Exception as ex:
            check(
                "the game really has %s where the list says it does" % (label,),
                False,
                "find_object('UsableItemDefinition', %r) raised %r" % (path, ex),
            )
            continue

        kind, why = W._category(_Inv(real_path))
        check(
            "%s is collected, and lands in the right category" % (label,),
            kind == wanted,
            "the game's own path %s was read as %r (%s), expected %r"
            % (real_path, kind, why, wanted),
        )

    # --- gear, using real gear -------------------------------------------------------------
    ready = manager is not None and lvl > 1
    for kind_name, pool_key in (
        ("gun", ("weapon", 4)),
        ("shield", ("shield", 3)),
        ("grenade mod", ("grenade", 3)),
        ("class mod", ("classmod", 3)),
        ("relic", ("relic", 3)),
    ):
        path = POOLS.get(pool_key)
        made = give(path, lvl, 1) if (ready and path) else []
        if not made:
            check(
                "a real %s could be spawned to test the gear exclusion against" % (kind_name,),
                False,
                "pool %r produced nothing" % (path,),
            )
            continue
        thing = made[0]
        uid = _uid(thing)
        if uid is not None:
            mine.add(uid)
        kind, why = W._category(thing)
        check(
            "a real %s is left on the floor, never collected" % (kind_name,),
            kind == "",
            "%s is a %s and was read as %r (%s). The class test is the only thing standing "
            "between the backpack and every gun in the game"
            % (kind_name, thing.Class.Name, kind, why),
        )
        # Take it back straight away rather than piling five spawned items into the backpack.
        for item in backpack():
            if _uid(item) == uid and uid not in pre_uids:
                try:
                    manager.RemoveInventoryFromBackpack(item)
                except Exception as ex:
                    print("could not take back the test %s: %r" % (kind_name, ex))

    # --- things that look collectable and are not ------------------------------------------
    kind, _ = W._category(_Inv(AMMO, def_cls="MissionItemDefinition"))
    check(
        "a mission item is never collected, even when it sits in a collected category",
        kind == "",
        "a MissionItemDefinition at an ammo path was read as %r" % (kind,),
    )

    kind, _ = W._category(_Inv("GD_Something.New.Thing_Nobody_Has_Seen"))
    check(
        "a kind of pickup nobody has thought about is left on the floor",
        kind == "",
        "an unknown usable item was read as %r; a blacklist would have collected this" % (kind,),
    )

    kind, _ = W._category(_Inv(AMMO, cls="WillowWeapon"))
    check(
        "a gun is refused on its class alone, whatever its definition says",
        kind == "",
        "a WillowWeapon carrying an ammo path was read as %r" % (kind,),
    )

    # --- shield boosters, the one guess in the whitelist ------------------------------------
    by_name, why_name = W._category(_Inv("GD_Whatever.Unknown.Thing", item_name="Shield Booster"))
    check(
        "a shield booster is recognised by its name, which is the rule copied from a working mod",
        by_name == "boosters",
        "read as %r (%s)" % (by_name, why_name),
    )

    booster_paths = []
    try:
        for obj in unrealsdk.find_all("UsableItemDefinition"):
            name = str(obj.Name)
            if name.startswith("Default__"):
                continue
            path = str(obj._path_name())
            if "booster" in path.lower():
                booster_paths.append(path)
    except Exception as ex:
        print("could not walk the usable item definitions: %r" % (ex,))
    check(
        "the guess that booster definitions have 'booster' in their path holds up",
        bool(booster_paths),
        "found %d loaded definitions with 'booster' in the path: %s. A failure here does NOT "
        "break the feature - the name rule above still catches them - it means the path rule in "
        "CATEGORIES is dead weight and the comment calling it a guess was right"
        % (len(booster_paths), booster_paths[:5]),
    )

    # --- the sweep itself -------------------------------------------------------------------
    W.enabled.value = True
    W.distance.value = 1000
    for option in W.switches.values():
        option.value = True

    close_ammo = _Pickup(_Inv(AMMO), x=100.0)
    far_ammo = _Pickup(_Inv(AMMO), x=5000.0)
    close_gun = _Pickup(_Inv(AMMO, cls="WillowWeapon"), x=100.0)
    close_money = _Pickup(_Inv(MONEY), x=200.0)
    quest = _Pickup(_Inv(AMMO), x=100.0, mission=True)
    gone = _Pickup(_Inv(AMMO), x=100.0, pickupable=False)

    world = _World([close_ammo, far_ammo, close_gun, close_money, quest, gone])
    fake = _PC(world)
    took = W.sweep(fake)
    check(
        "the vacuum takes the ammo and the money that are near you",
        close_ammo in fake.asked and close_money in fake.asked,
        "it asked for %d things" % (len(fake.asked),),
    )
    check(
        "the vacuum leaves guns on the floor",
        close_gun not in fake.asked,
        "it asked for the gun: %r" % (close_gun in fake.asked,),
    )
    check(
        "the vacuum does not reach past the distance you set",
        far_ammo not in fake.asked,
        "ammo at 5000 units with a reach of 1000 was asked for: %r"
        % (far_ammo in fake.asked,),
    )
    check(
        "the vacuum never touches a mission item",
        quest not in fake.asked,
        "asked for the quest item: %r" % (quest in fake.asked,),
    )
    check(
        "the vacuum ignores something the game has already marked as not pickupable",
        gone not in fake.asked,
        "asked for it: %r" % (gone in fake.asked,),
    )
    check(
        "it reports how many actually arrived, counted off the list rather than off the item",
        took == len(fake.asked),
        "asked for %d, reported %d" % (len(fake.asked), took),
    )

    # One category off.
    W.switches["money"].value = False
    world = _World([_Pickup(_Inv(AMMO), x=100.0), _Pickup(_Inv(MONEY), x=100.0)])
    fake = _PC(world)
    W.sweep(fake)
    check(
        "turning off just the money switch leaves ammo still flying to you",
        len(fake.asked) == 1,
        "with money off it still asked for %d things" % (len(fake.asked),),
    )
    W.switches["money"].value = True

    # The stale-snapshot guard: a controller whose pickup takes two items at once.
    world = _World([_Pickup(_Inv(AMMO), x=100.0) for _ in range(6)])
    greedy = _PC(world, takes=2)
    W.sweep(greedy)
    check(
        "the sweep stops the moment more vanishes than it asked for, rather than walking on "
        "through a list of things that no longer exist",
        len(greedy.asked) == 1,
        "it asked for %d things after the first call removed two; walking on is how this "
        "feature would crash the game rather than merely not work" % (len(greedy.asked),),
    )

    # A guest.
    world = _World([_Pickup(_Inv(AMMO), x=100.0)])
    guest = _PC(world, net_mode=3)
    W.on_guest.value = False
    W._ticks = W.EVERY - 1
    W.on_tick(guest, None, None, None)
    check(
        "a guest's game does not sweep unless it is told it may",
        not guest.asked,
        "the guest asked for %d things" % (len(guest.asked),),
    )
    W.on_guest.value = True
    W._ticks = W.EVERY - 1
    W.on_tick(guest, None, None, None)
    check(
        "and it does sweep when it is told it may",
        len(guest.asked) == 1,
        "the guest asked for %d things with the switch on" % (len(guest.asked),),
    )
    W.on_guest.value = False

    # The throttle.
    sweeps = []
    real_sweep = W.sweep
    W.sweep = lambda controller: sweeps.append(controller)
    try:
        W._ticks = 0
        quiet = _PC(_World([]))
        for _ in range(600):
            W.on_tick(quiet, None, None, None)
    finally:
        W.sweep = real_sweep
    check(
        "the floor is swept about thirteen times a second, not 264",
        len(sweeps) == 600 // W.EVERY,
        "%d sweeps over 600 frames, expected %d" % (len(sweeps), 600 // W.EVERY),
    )

    # Off means off.
    W.enabled.value = False
    sweeps = []
    W.sweep = lambda controller: sweeps.append(controller)
    try:
        W._ticks = 0
        for _ in range(600):
            W.on_tick(_PC(_World([])), None, None, None)
    finally:
        W.sweep = real_sweep
    check(
        "turning the vacuum off in the menu really stops it looking at the floor",
        not sweeps,
        "it still swept %d times with the switch off" % (len(sweeps),),
    )

finally:
    W.sweep = real_sweep
    W.enabled.value = was_enabled
    W.distance.value = was_distance
    W.on_guest.value = was_guest
    W.diagnose.value = was_diagnose
    for name, value in was_switches.items():
        W.switches[name].value = value
    W._ticks = _ticks_before

    taken_back = 0
    if manager is not None:
        for item in backpack():
            u = _uid(item)
            if u is None or u not in mine or u in pre_uids:
                continue
            try:
                manager.RemoveInventoryFromBackpack(item)
                taken_back += 1
            except Exception as ex:
                print("could not take back a spawned item (%s): %r" % (u, ex))
    print("cleanup: took back %d spawned items; every setting restored" % (taken_back,))

summary()
