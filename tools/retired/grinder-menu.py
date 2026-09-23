# Grinder, the menu and the chest hooks - checks for the claims in AUDIT-RAW/grinder.md
# Run: bash bl2-mcp/tools/ask.sh bl2-mcp/tools/checks/grinder-menu.py
#
# Covers grinder.md claims 1, 2, 3, 4, 5, 7, 8, 9, 10, 23, 26, 35, 36, 37 and 39.
#
# SAFETY: the only item this feeds to a live grinder path is one it spawned itself, picked
# out of the level-less menu by rebuilding that menu's exact label for it. The finally block
# removes every backpack item that was not there at the start, restores the level-less list,
# the mod options and the money.

reset()
import unrealsdk
from pathlib import Path
from bl2_modern.core import all_hooks
from bl2_modern.features import grinder as G
from bl2_modern.features import levelless as L

P = pc()
GOLDEN = "InteractiveObj_TreasureChest_Golden"
NOTES = []
FIRED = []
KEEP = {str(i) for i in G._backpack(P)}
SAVED_HOW, SAVED_COST, SAVED_ENABLED, SAVED_MONEY = (
    G.how_many.value, G.cost_per_level.value, G.enabled.value, money(P),
)
SAVED_MARKS = list(L.marked.value or [])

REAL_NOTE = G._note
REAL_CHOOSE, REAL_REPORT, REAL_NORMAL = G._choose_items, G._report, G._open_chest_normally
REAL_MARK = L.mark
G._note = lambda message: NOTES.append(message)

MENU = [
    "Perfect an item",
    "Grind for something better",
    "Make an item level-less",
    "Open the chest normally",
    "Report what the grinder sees",
]
WANT_ROUTE = {
    "Perfect an item": [("_choose_items", "perfect")],
    "Grind for something better": [("_choose_items", "grind")],
    "Make an item level-less": [("_choose_items", "levelless")],
    "Open the chest normally": [("_open_chest_normally",)],
    "Report what the grinder sees": [("_report",)],
}


def keys():
    """The golden key count, by whichever of the game's own accessors this build has.

    All three names come out of the shipped binary's name tables (.tmpstr/names_willow.txt
    and names_GearboxFramework.txt), not out of a guess.
    """
    for owner, attr in (
        (P, "GetNumGoldenKeysAvailable"),
        (P, "GetNumGoldenKeysAcquired"),
        (P.PlayerReplicationInfo, "GetGoldenKeyCount"),
    ):
        try:
            return int(getattr(owner, attr)()), attr
        except Exception:  # noqa: BLE001, PERF203
            continue
    return None, "none of GetNumGoldenKeysAvailable / GetNumGoldenKeysAcquired / GetGoldenKeyCount"


def levelless_button(uid):
    """The exact label _choose_one_to_free builds for one item, so the click lands on OURS.

    grinder.py:373-382 builds it from the item's position in the usable list, so the same
    filter has to be rebuilt here rather than guessing an index.
    """
    usable = [i for i in G._backpack(P) if G._kind(i) not in G.NOT_GRINDABLE]
    for index, item in enumerate(usable):
        try:
            if int(item.DefinitionData.UniqueId) != uid:
                continue
        except Exception:  # noqa: BLE001, PERF203
            continue
        star = "* " if L.is_marked(item) else ""
        return f"{star}{G._label(item)}  lvl {G._level(item)}  ({index + 1})"
    return None


boxes = record(G)
try:
    add_money(200_000)
    G.enabled.value = True
    G.how_many.value = 3
    G.cost_per_level.value = 100

    # --- the five choices ----------------------------------------------------------------
    G._busy = False
    boxes.clear()
    G._open_menu(P)
    check("opening the grinder shows one menu", len(boxes) == 1, f"{len(boxes)} dialogs")
    check(
        "the grinder offers exactly the five choices, in the order the menu builds them",
        bool(boxes) and boxes[-1].names() == MENU,
        boxes[-1].names() if boxes else "no dialog",
    )
    check(
        "the grinder's menu is titled Grinder and says what you can spend",
        bool(boxes) and boxes[-1].title == "Grinder" and "$" in boxes[-1].kw.get("message", ""),
        f"{boxes[-1].title!r} / {boxes[-1].kw.get('message')!r}" if boxes else "no dialog",
    )

    # --- where each button goes, with the real actions stubbed out -----------------------
    G._choose_items = lambda controller, recipe: FIRED.append(("_choose_items", recipe))
    G._report = lambda controller: FIRED.append(("_report",))
    G._open_chest_normally = lambda controller: FIRED.append(("_open_chest_normally",))

    routes = {}
    for name in MENU:
        boxes.clear()
        FIRED.clear()
        G._busy = False
        G._open_menu(P)
        pick(boxes[-1], name)
        routes[name] = list(FIRED)
    check(
        "each of the five choices reaches its own action and no other",
        routes == WANT_ROUTE,
        {k: v for k, v in routes.items() if v != WANT_ROUTE[k]} or "all five matched",
    )

    # grinder.py:230-231 ends the dispatch on a bare else, so anything that fails the
    # identity comparison grinds instead of being refused.
    boxes.clear()
    FIRED.clear()
    G._busy = False
    G._open_menu(P)
    boxes[-1].kw["on_select"](boxes[-1], G.OptionBoxButton("Not a real choice", ""))
    check(
        "a button the menu never built is refused rather than silently grinding",
        FIRED == [],
        FIRED or "nothing fired",
    )

    # --- the busy flag, which is what stands the chest hooks down ------------------------
    G._busy = False
    boxes.clear()
    G._open_menu(P)
    check("opening the grinder marks it busy", G._busy is True, G._busy)
    cancel(boxes[-1])
    check("backing out of the grinder clears the busy flag", G._busy is False, G._busy)

    G._busy = False
    G._open_menu(P)
    pick(boxes[-1], "Report what the grinder sees")
    check("choosing something clears the busy flag", G._busy is False, G._busy)

    class Boom(G.OptionBox):
        def show(self, button=None):
            raise RuntimeError("the dialog refused to open")

    G._busy = False
    NOTES.clear()
    kept_box, G.OptionBox = G.OptionBox, Boom
    G._open_menu(P)
    G.OptionBox = kept_box
    check(
        "a menu that will not open clears the busy flag instead of locking the chest out",
        G._busy is False,
        G._busy,
    )
    check(
        "a menu that will not open says so",
        any("could not show the menu" in n for n in NOTES),
        NOTES or "said nothing",
    )

    # --- the keybind ----------------------------------------------------------------------
    # _open_grinder is a KeybindType, not a function: mods_base/keybinds.py turns the
    # decorated function into a dataclass with no __call__. The audit's `g._open_grinder()`
    # would raise TypeError; the callback is what the key press runs.
    check(
        "the H bind is registered as a keybind object with a callback",
        hasattr(G._open_grinder, "callback") and callable(G._open_grinder.callback),
        type(G._open_grinder).__name__,
    )
    G.enabled.value = False
    boxes.clear()
    G._busy = False
    press = getattr(G._open_grinder, "callback", G._open_grinder)
    press()
    check(
        "the H key respects the 'Enable the grinder' switch",
        len(boxes) == 0,
        f"{len(boxes)} menus opened with the feature switched off",
    )
    G.enabled.value = True
    G._busy = False

    # --- the four chest hooks --------------------------------------------------------------
    HOOKS = (G.on_used_definition, G.on_used_object, G.on_golden_key_prompt, G.on_cannot_afford)
    unbound = [
        h.hook_identifier for h in HOOKS if h.get_active_count() != len(h.hook_funcs)
    ]
    check(
        "all four chest hooks are actually bound to the game right now",
        not unbound,
        unbound or f"{len(HOOKS)} hooks bound",
    )
    ids = {h.hook_identifier for h in all_hooks()}
    missing = [h.hook_identifier for h in HOOKS if h.hook_identifier not in ids]
    check(
        "the mod menu can see the chest hooks, so turning Second Wind off stops them",
        not missing,
        f"{len(missing)} of 4 hooks are invisible to core.all_hooks(): "
        f"{[m.rsplit('.', 1)[-1] for m in missing]}",
    )

    # --- what may and may not take the chest over -------------------------------------------
    boxes.clear()
    for name in (
        "InteractiveObj_Ammo_Machine",
        "InteractiveObj_Vending_Machine",
        "InteractiveObj_TreasureChest_Red",
        "Door_Sanctuary",
    ):
        G._busy = False
        G._skip_until = 0.0
        G._try_take_over(P, "definition", name, None)
    check(
        "using anything that is not the Golden Chest never opens the grinder",
        len(boxes) == 0,
        f"{len(boxes)} menus opened, titled {[b.title for b in boxes]}",
    )

    # ObjectGrade_TreasureChest_Golden IS the chest - measured 2026-08-20 standing in front of
    # it in Sanctuary, the actor's own balance points at exactly that object, and the object
    # hook reads it when the definition is not to hand. So it was the wrong stand-in for "a
    # name that merely contains the chest's". A name no object in the game has is the right one.
    boxes.clear()
    G._busy = False
    G._skip_until = 0.0
    G._try_take_over(P, "definition", "SomeOtherMod_TreasureChest_Golden_Thing", None)
    check(
        "an object whose name merely contains TreasureChest_Golden does not open the grinder",
        len(boxes) == 0,
        f"{len(boxes)} menus opened for the chest's loot GRADE object",
    )

    # --- nothing is ever blocked --------------------------------------------------------------
    chest_def = None
    try:
        chest_def = unrealsdk.find_object(
            "InteractiveObjectDefinition",
            "GD_Balance_Treasure.InteractiveObjects.InteractiveObj_TreasureChest_Golden",
        )
    except Exception:  # noqa: BLE001
        chest_def = None
    # This map may honestly not have the chest's package loaded - InteractiveObj_TreasureChest_
    # Golden's data lives in GD_Balance_Treasure, and nothing guarantees that package is resident
    # outside a map that actually references it. That is an empty map, not a broken feature, so
    # it is reported as a skip rather than a fail - see grinder-needs-travel.py, which travels to
    # the real chest and drives it directly.
    if chest_def is None:
        print(
            "[SKIP] the Golden Chest's own definition object can be reached from wherever we are"
            "   not loaded in this map - travel to Sanctuary and run grinder-needs-travel.py, "
            "which finds the real chest and drives it directly"
        )
    else:
        check(
            "the Golden Chest's own definition object can be reached from wherever we are",
            chest_def is not None,
            str(chest_def),
        )

    boxes.clear()
    returns = []
    for how in ("definition", "object", "could not afford"):
        G._busy = False
        G._skip_until = 0.0
        returns.append(G._try_take_over(P, how, GOLDEN, None))
    G._busy = False
    G._skip_until = 0.0
    returns.append(G.on_golden_key_prompt(P, None, None, None))
    if chest_def is not None:
        G._busy = False
        G._skip_until = 0.0
        returns.append(G.on_cannot_afford(chest_def, None, None, None))
    check(
        "no grinder hook ever blocks the chest's own bookkeeping",
        all(r is None for r in returns),
        f"{len(returns)} calls returned {sorted({str(r) for r in returns})}",
    )
    check(
        "each of those hook calls really did open the grinder, so the test went down the live path",
        len(boxes) == len(returns),
        f"{len(boxes)} menus for {len(returns)} hook calls",
    )

    # --- 'Open the chest normally' -------------------------------------------------------------
    # One chest press fires more than one hook (the findings file records both an [object] and
    # a [definition] line for one press), and _skip_once is a single global.
    # A WINDOW, not a one-shot. `_skip_once` is gone: one chest press fires more than one hook,
    # so a single flag was eaten by the first of them and the second re-opened the grinder
    # anyway. `_skip_until` is a moment in the future, and every hook before it stands down.
    G._busy = False
    G._skip_until = 0.0
    boxes.clear()
    REAL_NORMAL(P)
    check(
        "'Open the chest normally' holds every hook off, not just the next one",
        G._skip_until > G._now(P),
        f"the window closes in {G._skip_until - G._now(P):.2f}s "
        f"(SECONDS_TO_IGNORE is {G.SECONDS_TO_IGNORE})",
    )
    check(
        "and the grinder really does stand down inside that window",
        G._try_take_over(P, "definition", "InteractiveObj_TreasureChest_Golden", None) is None
        and not boxes,
        f"{len(boxes)} menus opened while the chest was meant to be opening normally",
    )
    G._try_take_over(P, "definition", GOLDEN, None)
    G._try_take_over(P, "could not afford", GOLDEN, None)
    check(
        "'Open the chest normally' survives both hooks of one chest press",
        len(boxes) == 0,
        f"{len(boxes)} menus opened after the skip was armed",
    )
    G._skip_until = 0.0
    G._busy = False

    # the real handlers back, everything below drives live code
    G._choose_items, G._report, G._open_chest_normally = REAL_CHOOSE, REAL_REPORT, REAL_NORMAL

    # --- golden keys ------------------------------------------------------------------------------
    before_keys, how_read = keys()
    boxes.clear()
    G._busy = False
    G._open_menu(P)
    pick(boxes[-1], "Grind for something better")
    after_keys, _ = keys()
    check(
        "opening the grinder and choosing a recipe never spends a Golden Key",
        before_keys is not None and after_keys == before_keys,
        f"read via {how_read}: {before_keys} -> {after_keys}",
    )

    # --- skins and heads --------------------------------------------------------------------------
    skins = [i for i in G._backpack(P) if G._kind(i) == "skin"]
    check(
        "the backpack holds a skin to test the skin exclusion against",
        bool(skins),
        f"{len(skins)} skins in the backpack",
    )
    if skins:
        skin = skins[0]
        skin_label = G._label(skin)
        before = {str(i) for i in G._backpack(P)}
        P.GetPawnInventoryManager().ClientAddItemToBackpack(skin.DefinitionData, 1, 0, False, 0, 0)
        made_copy = [i for i in G._backpack(P) if str(i) not in before]
        G.how_many.value = 2
        check(
            "a second copy of the skin could be made, so a group of two exists to be offered",
            len(made_copy) == 1 and bool(skin_label),
            f"{len(made_copy)} copies of {skin_label!r}",
        )
        for recipe in ("grind", "perfect"):
            boxes.clear()
            G._choose_items(P, recipe)
            labels = " | ".join(boxes[-1].names()) if boxes else ""
            check(
                f"skins are never offered by the {recipe} recipe",
                bool(skin_label) and skin_label not in labels,
                f"menu offered: {labels[:200]}",
            )
        G.how_many.value = 3

    # --- perfecting with an impossible count -------------------------------------------------------
    G.how_many.value = 1
    boxes.clear()
    NOTES.clear()
    G._choose_items(P, "perfect")
    check(
        "perfecting at 'items per grind' = 1 builds no menu at all",
        len(boxes) == 0,
        f"{len(boxes)} menus for a recipe that cannot work",
    )
    check(
        "perfecting at 'items per grind' = 1 says why",
        any("at least 2" in n for n in NOTES),
        NOTES or "said nothing",
    )
    G.how_many.value = 3

    # --- the level-less path, through the grinder's own menu -----------------------------------------
    mine = give(G.POOLS[("weapon", 3)], 40, 1)
    check("a gun could be spawned to make level-less", len(mine) == 1, f"{len(mine)} spawned")
    if mine:
        uid = int(mine[0].DefinitionData.UniqueId)

        # grinder.py:396-399 charges and only then calls mark, with no refund when it fails.
        L.mark = lambda item: False
        boxes.clear()
        G._choose_items(P, "levelless")
        label = levelless_button(uid)
        if boxes and label and label in boxes[-1].names():
            m = money(P)
            pick(boxes[-1], label)
            check(
                "making an item level-less charges nothing when the mark fails",
                money(P) == m,
                f"${m - money(P):,} taken for a mark that returned False",
            )
        else:
            check(
                "the level-less menu offers the gun this script spawned",
                False,
                f"wanted {label!r} among {boxes[-1].names()[:4] if boxes else 'no menu'}",
            )
        L.mark = REAL_MARK

        # and the toggle back off, which grinder.py:391-393 does free
        L.mark(mine[0])
        boxes.clear()
        G._choose_items(P, "levelless")
        label = levelless_button(uid)
        check(
            "an item that has been made level-less shows up starred in the menu",
            bool(label) and label.startswith("* "),
            label,
        )
        if boxes and label and label in boxes[-1].names():
            m, n = money(P), len(G._backpack(P))
            pick(boxes[-1], label)
            check(
                "picking a starred item again turns level-less off, free, and takes nothing",
                money(P) == m and len(G._backpack(P)) == n and uid not in L._ids(),
                f"money {money(P) - m}, backpack {len(G._backpack(P)) - n}, "
                f"still remembered: {uid in L._ids()}",
            )

    # --- the report -----------------------------------------------------------------------------------
    findings = Path(G.__file__).parent.parent / "data" / "grinder-findings.txt"
    was = findings.stat().st_size if findings.exists() else 0
    n, m = len(G._backpack(P)), money(P)
    G._report(P)
    text = findings.read_text(encoding="utf-8", errors="replace") if findings.exists() else ""
    check(
        "'Report what the grinder sees' writes a report to the findings file",
        findings.exists() and findings.stat().st_size > was and "=== grinder report ===" in text,
        f"{was} -> {findings.stat().st_size if findings.exists() else 'missing'} bytes",
    )
    check(
        "the report writes down what the game's own spawn function looks like",
        "--- the game's own spawn function ---" in text,
        "marker present" if "--- the game's own spawn function ---" in text else "marker missing",
    )
    check(
        "writing the report takes no items and no money",
        len(G._backpack(P)) == n and money(P) == m,
        f"backpack {len(G._backpack(P)) - n}, money {money(P) - m}",
    )

except Exception:  # noqa: BLE001
    # One raise must not cost the whole scoreboard, which is what regress.py does today.
    import traceback
    print("\n--- this file raised; the checks below this point never ran ---")
    traceback.print_exc()

finally:
    G._note = REAL_NOTE
    G._choose_items, G._report, G._open_chest_normally = REAL_CHOOSE, REAL_REPORT, REAL_NORMAL
    L.mark = REAL_MARK
    L.marked.value = SAVED_MARKS
    G.how_many.value = SAVED_HOW
    G.cost_per_level.value = SAVED_COST
    G.enabled.value = SAVED_ENABLED
    G._busy = False
    G._skip_until = 0.0
    manager = P.GetPawnInventoryManager()
    left = [i for i in G._backpack(P) if str(i) not in KEEP]
    for item in left:
        try:
            manager.RemoveInventoryFromBackpack(item)
        except Exception as ex:  # noqa: BLE001
            print(f"could not remove {item}: {ex!r}")
    add_money(SAVED_MONEY - money(P))
    restore()
    print(f"\ncleaned up {len(left)} spawned items, money back to ${money(P):,} "
          f"(started at ${SAVED_MONEY:,}), level-less list back to {SAVED_MARKS}")
    if NOTES:
        print("the grinder said: " + " | ".join(NOTES))

summary()
