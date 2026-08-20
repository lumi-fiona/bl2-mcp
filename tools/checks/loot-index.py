# Where does this drop - checks for features/lootindex.py
# Run: bash bl2-mcp/tools/ask.sh bl2-mcp/tools/checks/loot-index.py
#
# SAFETY: this feature is a read from beginning to end. It makes nothing, moves nothing and
# charges nothing, and there is a check below that the backpack does not move. The only file
# it writes is its own index, which this moves aside and puts back.
#
# The two checks worth reading are "the odds add up to one whole pool" and "a pool whose odds
# the game works out at run time is marked as varying rather than given a number". A drop
# guide that invents a percentage is worse than no drop guide.

reset()
import json
import unrealsdk
from bl2_modern import reportjob
from bl2_modern.features import lootindex as LI

P = pc()
KEEP = {str(i) for i in backpack(P)}
SAVED = (LI.enabled.value, LI.include_empty.value, LI.work_per_frame.value)
SAID = []
REAL_SAY = reportjob.say
reportjob.say = lambda title, message, seconds=6: SAID.append(message)

reportjob.REPORTS.mkdir(parents=True, exist_ok=True)
INDEX = reportjob.REPORTS / LI.INDEX_FILE
BACKUP = INDEX.with_suffix(".json.checkbackup")
if INDEX.is_file():
    INDEX.replace(BACKUP)


class Chance:
    """Stands in for the game's odds struct, so the maths can be checked without the game."""

    def __init__(self, constant, scale=1.0, attribute=None, initializer=None):
        self.BaseValueConstant = constant
        self.BaseValueScaleConstant = scale
        self.BaseValueAttribute = attribute
        self.InitializationDefinition = initializer


try:
    # --- reading one entry's weight --------------------------------------------------------
    check(
        "a plain weight is read as the number it is",
        LI._weight(Chance(3.0)) == 3.0 and LI._weight(Chance(2.0, 0.5)) == 1.0,
        f"{LI._weight(Chance(3.0))}, {LI._weight(Chance(2.0, 0.5))}",
    )
    check(
        "a weight the game works out at run time is not turned into a number",
        LI._weight(Chance(1.0, 1.0, attribute=object())) is None
        and LI._weight(Chance(1.0, 1.0, initializer=object())) is None,
        "an attribute-driven weight must come back as unknown, never as its constant",
    )
    check(
        "no weight at all is unknown rather than zero",
        LI._weight(None) is None,
        LI._weight(None),
    )

    # --- turning weights into odds -----------------------------------------------------------
    check(
        "the odds inside a pool add up to that whole pool",
        LI._odds([1.0, 1.0, 2.0]) == ["25.0%", "25.0%", "50.0%"],
        LI._odds([1.0, 1.0, 2.0]),
    )
    check(
        "one unknown weight makes the whole pool's odds unknown rather than wrong",
        LI._odds([1.0, None]) == ["weight 1", "varies"],
        LI._odds([1.0, None]),
    )
    check(
        "a pool where nothing has any weight says nothing ever drops",
        LI._odds([0.0, 0.0]) == ["never", "never"],
        LI._odds([0.0, 0.0]),
    )

    # --- the game's own data, by the field names this reads --------------------------------
    pools = [
        p for p in unrealsdk.find_all("ItemPoolDefinition", exact=False)
        if not str(p.Name).startswith("Default__")
    ]
    check(
        "the game has loot pools loaded to read",
        len(pools) > 50,
        f"{len(pools)} pools loaded right now",
    )

    with_items = 0
    entries_seen = 0
    named = 0
    for pool in pools[:400]:
        try:
            entries = list(pool.BalancedItems or [])
        except Exception:
            continue
        if entries:
            with_items += 1
        for entry in entries:
            entries_seen += 1
            if entry.InvBalanceDefinition is not None or entry.ItmPoolDefinition is not None:
                named += 1
    check(
        "a pool's contents can be read off the field this feature reads",
        with_items > 5 and entries_seen > 10,
        f"{with_items} of the first 400 pools hold something, {entries_seen} entries in all",
    )
    check(
        "every entry in a pool names either an item or another pool",
        entries_seen > 0 and named == entries_seen,
        f"{named} of {entries_seen} entries named something",
    )

    lists = [
        o for o in unrealsdk.find_all("ItemPoolListDefinition", exact=False)
        if not str(o.Name).startswith("Default__")
    ]
    reached = 0
    for holder in lists[:200]:
        try:
            for entry in list(holder.ItemPools or []):
                if LI._entry_pool(entry) is not None:
                    reached += 1
        except Exception:
            continue
    check(
        "the lists that point at pools can be followed to their pools",
        bool(lists) and reached > 0,
        f"{reached} pool references found across {min(len(lists), 200)} lists",
    )

    enemies = [
        o for o in unrealsdk.find_all("AIPawnBalanceDefinition", exact=False)
        if not str(o.Name).startswith("Default__")
    ]
    from_enemies = 0
    for enemy in enemies[:200]:
        try:
            for entry in list(enemy.DefaultItemPoolList or []):
                if LI._entry_pool(entry) is not None:
                    from_enemies += 1
        except Exception:
            continue
    check(
        "an enemy can be asked which pools it drops from",
        bool(enemies) and from_enemies > 0,
        f"{from_enemies} pool references across {min(len(enemies), 200)} enemies "
        f"(if this is zero the index can name pools but never enemies)",
    )

    # --- running it, a slice at a time --------------------------------------------------------
    n_before = len(backpack(P))
    LI.enabled.value = True
    started = reportjob.start(LI.OWNER, LI.NAME, LI._work, 3)
    check("the index starts", started and reportjob.busy() == LI.NAME, reportjob.busy())
    if started:
        for _ in range(300):
            if reportjob.busy() != LI.NAME:
                break
            reportjob.pump(LI.OWNER)
        written = reportjob.REPORTS / "loot-index.txt"
        check(
            "the index writes its report as it goes",
            written.is_file() and written.stat().st_size > 0,
            f"{written.stat().st_size if written.is_file() else 'missing'} bytes",
        )
        text = written.read_text(encoding="utf-8", errors="replace") if written.is_file() else ""
        check(
            "the report says how many pools it could see, so a short run is visible",
            "loot pools are loaded right now" in text,
            text[:200],
        )
        reportjob.cancel(LI.OWNER)
    check(
        "building the index never touches your backpack",
        len(backpack(P)) == n_before,
        f"the backpack moved by {len(backpack(P)) - n_before}",
    )

    # --- looking one thing up ------------------------------------------------------------------
    SAID.clear()
    INDEX.unlink(missing_ok=True)
    LI._look_up()
    check(
        "looking something up before the index exists says so plainly",
        bool(SAID) and "index" in SAID[-1].lower(),
        SAID[-1] if SAID else "it said nothing at all",
    )

    held = LI._held_name(P)
    check(
        "the thing in your hands has a name the index can be keyed on",
        bool(held),
        f"it is called {held!r}",
    )
    if held:
        INDEX.write_text(json.dumps({
            "pools_loaded": 1,
            "items": {held: [["Some.Pool.Path", "12.5%", "enemy PawnBalance_Nomad"]]},
        }), encoding="utf-8")
        SAID.clear()
        LI._look_up()
        check(
            "the gun in your hands is looked up and its source named",
            bool(SAID) and "PawnBalance_Nomad" in SAID[-1] and "12.5%" in SAID[-1],
            SAID[-1] if SAID else "it said nothing at all",
        )
        SAID.clear()
        INDEX.write_text(json.dumps({"pools_loaded": 1, "items": {}}), encoding="utf-8")
        LI._look_up()
        check(
            "a gun that is in no loaded pool is said to be in none, not guessed at",
            bool(SAID) and "not in the index" in SAID[-1],
            SAID[-1] if SAID else "it said nothing at all",
        )

except Exception:
    import traceback
    print("\n--- this file raised; the checks below this point never ran ---")
    traceback.print_exc()

finally:
    reportjob.cancel(LI.OWNER)
    reportjob.say = REAL_SAY
    LI.enabled.value, LI.include_empty.value, LI.work_per_frame.value = SAVED
    INDEX.unlink(missing_ok=True)
    if BACKUP.is_file():
        BACKUP.replace(INDEX)
    manager = P.GetPawnInventoryManager()
    left = [i for i in backpack(P) if str(i) not in KEEP]
    for item in left:
        try:
            manager.RemoveInventoryFromBackpack(item)
        except Exception as ex:
            print(f"could not remove {item}: {ex!r}")
    print(f"\nput the real index back, removed {len(left)} strays")
    if SAID:
        print("it said: " + " | ".join(SAID[-6:]))

summary()
