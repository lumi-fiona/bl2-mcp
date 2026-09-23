"""
Test scaffolding, exec'd into the bridge's scope so later requests can use it.

    bash bl2-mcp/tools/ask.sh bl2-mcp/tools/harness.py

It lives here rather than inside the mod on purpose: it monkey-patches the game's dialog class,
which is a thing a test does and a thing a shipped feature must never do.

THE ONE CONTRACT, and breaking it hangs the game:

    A bridge request must return within one frame.

The bridge runs `exec` inside `WillowGame.WillowPlayerController:PlayerTick` (bridge.py:111-138),
which is the game's own frame loop. A `time.sleep(2)` in a request does not wait two seconds while
the game carries on - it FREEZES the game for two seconds, so anything you then measure is a
photograph of a stopped world. A "wait until the map changes" loop is worse: the map change needs
the very thread the loop is holding, so the game deadlocks and only a taskkill ends it.

Anything that needs time to pass is therefore several separate requests from outside, with the
waiting done by the shell. `poll.sh` exists for that.
"""

# No `from __future__ import annotations` here, deliberately: this file is sent to the bridge as
# text and executed there, and anything the sender prepends would push a future-import off the top
# and break compilation of the whole request.

# --- recording what the game says --------------------------------------------------------

RESULTS: list = []


def check(name, ok, detail=""):
    """Record one claim. The point is that it can come back False."""
    ok = bool(ok)
    RESULTS.append({"name": name, "ok": ok, "detail": str(detail)})
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f"   {detail}" if detail else ""))
    return ok


def summary():
    good = sum(1 for r in RESULTS if r["ok"])
    print(f"\n{good}/{len(RESULTS)} passed")
    for r in RESULTS:
        if not r["ok"]:
            print(f"   FAILED: {r['name']}  {r['detail']}")
    return good, len(RESULTS)


def reset():
    RESULTS.clear()


# --- driving dialogs without a screen or a keyboard --------------------------------------


class RecordedBox:
    """Stands in for ui_utils.OptionBox and remembers what it was asked to draw."""

    def __init__(self, **kw):
        self.kw = kw
        self.shown = False
        _BOXES.append(self)

    def show(self, button=None):
        self.shown = True

    def hide(self):
        pass

    # conveniences, so checks read like sentences
    @property
    def title(self):
        return self.kw.get("title", "")

    @property
    def buttons(self):
        return list(self.kw.get("buttons", []) or [])

    def names(self):
        return [b.name for b in self.buttons]

    def button(self, name):
        """The real button object, matched by name.

        Matched by NAME and never used as a dict key: OptionBoxButton is an unhashable
        dataclass, and the grinder compares buttons by identity (`button is forever`,
        grinder.py:222-231), so the object handed back to on_select must be the one the
        feature built - not a copy.
        """
        for b in self.buttons:
            if b.name == name:
                return b
        raise KeyError(f"no button named {name!r} among {self.names()}")


_BOXES: list = []
_PATCHED: dict = {}


def record(*modules):
    """
    Swap OptionBox for the recorder in each module. Returns the list boxes land in.

    Always pair with restore(), including when a check raises - see the note there about
    what a leaked patch does to the rest of the session.
    """
    _BOXES.clear()
    for m in modules:
        if m not in _PATCHED:
            _PATCHED[m] = m.OptionBox
        m.OptionBox = RecordedBox
    return _BOXES


def restore():
    """
    Put the real dialog class back, and clear the flags a real dialog would have cleared.

    THE FLAGS MATTER MORE THAN THE CLASS. `grinder._busy` is set True the moment a menu opens
    (grinder.py:194) and is only cleared inside on_select or on_cancel (grinder.py:219, :237).
    A recorded box never runs either unless a check asks it to - so a check that merely opens a
    menu and looks at it leaves _busy True, and every chest hook afterwards refuses to fire
    (grinder.py:1069, :1148). That is a silent, session-long disabling of the feature under test,
    and it would make every later chest check pass by not running.
    """
    for m, real in list(_PATCHED.items()):
        m.OptionBox = real
        for flag, value in (("_busy", False), ("_skip_once", False)):
            if hasattr(m, flag):
                setattr(m, flag, value)
    _PATCHED.clear()
    _BOXES.clear()


def pick(box, name):
    """Choose a button, exactly as a person clicking it would."""
    box.kw["on_select"](box, box.button(name))


def cancel(box):
    """Back out, exactly as pressing escape would."""
    handler = box.kw.get("on_cancel")
    if handler:
        handler(box)


# --- looking at the world ----------------------------------------------------------------


def pc():
    import unrealsdk

    live = [o for o in unrealsdk.find_all("WillowPlayerController")
            if not o.Name.startswith("Default__")]
    return live[-1] if live else None


def backpack(controller=None):
    controller = controller or pc()
    try:
        return list(controller.GetPawnInventoryManager().Backpack)
    except Exception:
        return []


def equipped(controller=None):
    """
    Everything worn or held, which is NOT in the backpack.

    Measured 2026-08-19: four WillowWeapons hang off InventoryChain and three items off
    ItemChain, and none of the seven appears in Backpack. Any feature that walks only the
    backpack silently ignores the gear actually in use - which is exactly the level-less bug.
    """
    controller = controller or pc()
    out = []
    for chain in ("InventoryChain", "ItemChain"):
        try:
            item = getattr(controller.GetPawnInventoryManager(), chain)
        except Exception:
            continue
        while item is not None:
            out.append(item)
            item = item.Inventory
    return out


def money(controller=None):
    import unrealsdk

    controller = controller or pc()
    cur = unrealsdk.find_enum("ECurrencyType")
    return controller.PlayerReplicationInfo.GetCurrencyOnHand(cur.CURRENCY_Credits)


def level(controller=None):
    controller = controller or pc()
    return int(controller.PlayerReplicationInfo.ExpLevel)


def where(controller=None):
    controller = controller or pc()
    return str(controller.WorldInfo.GetMapName(False))


# --- moving around the world -------------------------------------------------------------
#
# None of this lives in a mod file on purpose. A mod file is read once at load, so iterating on
# one costs a restart every time; this is text sent over the bridge, so a change costs nothing.
# It also means the shipped pack never carries a teleport function it does not need.


def move_to(x, y, z):
    """Put the pawn somewhere in the current map."""
    import unrealsdk

    p = pc()
    p.Pawn.Location = unrealsdk.make_struct("Vector", X=float(x), Y=float(y), Z=float(z))
    p.Pawn.Velocity = unrealsdk.make_struct("Vector")
    return p.Pawn.Location


def move_to_actor(actor, back=250.0, up=90.0):
    """Stand just behind and above something, so it is in reach and you are not inside it."""
    loc = actor.Location
    return move_to(loc.X - back, loc.Y, loc.Z + up)


def stations():
    import unrealsdk

    return {o.Name: o for o in unrealsdk.find_all("FastTravelStationDefinition")
            if not o.Name.startswith("Default__")}


def travel_to(name):
    """
    Fast travel to another map, with no station and no menu.

    Uses ServerTeleportPlayerToStation, NOT TeleportPlayerToStation. BL2-LEVERS.md:396 records
    why, from a disassembly: the latter walks `foreach AllActors(class'TravelStation')` over the
    *currently loaded* level, so for a station on another map it finds nothing and silently does
    nothing at all. The Server one reaches WillowGameInfo.InitiateTravel and is the real thing.

    Returns immediately. The map change takes seconds and cannot be waited for inside a request -
    poll `where()` from outside instead.
    """
    found = stations()
    if name not in found:
        near = [n for n in found if name.lower() in n.lower()]
        raise KeyError(f"no station {name!r}. Did you mean: {near[:8]}")
    pc().ServerTeleportPlayerToStation(found[name])
    return name


def find_actor(class_name, contains=""):
    import unrealsdk

    out = []
    for o in unrealsdk.find_all(class_name):
        if o.Name.startswith("Default__"):
            continue
        if contains and contains.lower() not in str(o).lower():
            continue
        out.append(o)
    return out


def screenshot():
    """
    Ask the game to photograph itself.

    Measured 2026-08-19: this writes nothing into the game folder or Documents - it hands the
    frame to Steam, which saves a JPG under
    Steam/userdata/<id>/760/remote/49520/screenshots/. Looking in the wrong place is why this
    was briefly written off as broken. Use `tiledshot 1`, never a higher number: `tiledshot 2`
    renders the interface once per tile, so a dialog appears four times in one picture.
    """
    pc().ConsoleCommand("shot")
    return "asked; the file appears in Steam's screenshot folder a moment later"


def give(pool_path, stage=None, count=1):
    """
    Spawn items from a named loot pool straight into the backpack.

    RETURNS THE MANAGER'S OWN OBJECTS, not the ones the pool handed over, and the difference
    was quietly wrong for a long time. MEASURED 2026-08-20: AddBackpackInventory does not store
    the object it is given - it stores its own, carrying the same UniqueId. So the item this
    used to return was a second object describing the same gun, and it was NOT in
    `manager.Backpack`. Anything that then tried to remove or equip it called the game with the
    wrong object, got no complaint, and measured no change.

    That is what "the backpack moved by 0" meant in every grinder, part-bench and level-less
    check that reported it: the feature was fine and the scaffolding was handing it a stranger.

    A spawn that cannot be found again afterwards is returned as-is rather than dropped, so a
    test that wanted three items still gets three and fails on what it was actually testing.
    """
    import unrealsdk

    p = pc()
    stage = int(stage if stage is not None else level(p))
    pool = unrealsdk.find_object("ItemPoolDefinition", pool_path)
    manager = p.GetPawnInventoryManager()

    def uid_of(item):
        try:
            return int(item.DefinitionData.UniqueId)
        except Exception:
            return None

    made = []
    for _ in range(int(count)):
        ok, items = unrealsdk.find_all("ItemPool")[-1].SpawnBalancedInventoryFromPool(
            pool, stage, stage, p, [], None, 1.0, False,
        )
        for item in items or []:
            manager.AddBackpackInventory(item)
            wanted = uid_of(item)
            held = next(
                (b for b in manager.Backpack if wanted is not None and uid_of(b) == wanted),
                None,
            )
            made.append(held if held is not None else item)
    return made


# The game's own loot pools by (kind, rarity), for checks that need an item to test with. These
# lived in the old grinder (retired by ticket 19), and four checks still borrow them.
POOLS = {
    ("weapon", 3): "GD_Itempools.WeaponPools.Pool_Weapons_All_04_Rare",
    ("weapon", 4): "GD_Itempools.WeaponPools.Pool_Weapons_All_05_VeryRare",
    ("shield", 3): "GD_Itempools.ShieldPools.Pool_Shields_All_04_Rare",
    ("grenade", 3): "GD_Itempools.GrenadeModPools.Pool_GrenadeMods_04_Rare",
    ("classmod", 3): "GD_Itempools.ClassModPools.Pool_ClassMod_04_Rare",
    ("relic", 3): "GD_Itempools.ArtifactPools.Pool_Artifacts_03_Rare",
}


def spawn_from_pool(pool, stage):
    """Items the game makes from one of its pools, NOT added to any backpack (the old
    grinder's _spawn_from_pool: eight arguments, measured 2026-08-19)."""
    import unrealsdk

    ok, items = unrealsdk.find_all("ItemPool")[-1].SpawnBalancedInventoryFromPool(
        pool, int(stage), 0, pc(), [], None, 1.0, False,
    )
    return list(items or [])


def add_money(amount):
    import unrealsdk

    cur = unrealsdk.find_enum("ECurrencyType")
    pc().PlayerReplicationInfo.AddCurrencyOnHand(cur.CURRENCY_Credits, int(amount))
    return money()


print("harness ready: check/summary/reset · record/restore/pick/cancel · "
      "pc/backpack/equipped/money/level/where · move_to/travel_to/stations/find_actor/"
      "screenshot/give/add_money")
