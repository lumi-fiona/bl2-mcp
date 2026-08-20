# The gun census - checks for features/guncensus.py
# Run: bash bl2-mcp/tools/ask.sh bl2-mcp/tools/checks/gun-census.py
#
# SAFETY: the census makes item objects and never puts them in anybody's inventory, so the
# backpack should not move at all - and there is a check below that says so. The census file
# itself is a real file the feature writes, so this one moves it aside and puts it back.
#
# The check that decides the feature is "the game will make one particular gun on demand".
# Neither of the two routes has ever been run. If both FAIL the feature cannot work as
# written and the fix is a third route, not a tweak.

reset()
import json
import unrealsdk
from bl2_modern import reportjob
from bl2_modern.features import guncensus as GC

P = pc()
KEEP = {str(i) for i in backpack(P)}
SAVED = (GC.enabled.value, GC.census_level.value, GC.work_per_frame.value)
SAID = []
REAL_SAY = reportjob.say
reportjob.say = lambda title, message, seconds=6: SAID.append(message)

reportjob.REPORTS.mkdir(parents=True, exist_ok=True)
CENSUS = reportjob.REPORTS / GC.CENSUS_FILE
BACKUP = CENSUS.with_suffix(".json.checkbackup")
if CENSUS.is_file():
    CENSUS.replace(BACKUP)

try:
    # --- can the game be made to produce one named gun? -------------------------------------
    balances = [
        b for b in unrealsdk.find_all("WeaponBalanceDefinition", exact=False)
        if not str(b.Name).startswith("Default__")
    ]
    check(
        "the game will list the guns it knows about",
        len(balances) > 50,
        f"{len(balances)} weapon balances loaded",
    )

    spawner = GC._Spawner(P)
    check(
        "the game's own item pool class can be reached",
        spawner.item_pool is not None,
        spawner.item_pool,
    )

    n_before = len(backpack(P))
    made = []
    tried = []
    for balance in balances[:6]:
        items, why = spawner.make(balance, 40)
        tried.append((str(balance.Name), len(items), why))
        made.extend(items)
    for name, count, why in tried:
        print(f"   {name[:48]:<50} made {count}   {why[:60]}")

    check(
        "the game will make one particular gun on demand",
        bool(made),
        f"six balances tried, {len(made)} guns made. Routes reported: "
        + "; ".join(sorted({w for _n, _c, w in tried if w})[:2]),
    )
    check(
        "which way of making a gun worked is recorded",
        bool(spawner.route) if made else True,
        f"route: {spawner.route!r}",
    )
    check(
        "making guns for the census never puts anything in your backpack",
        len(backpack(P)) == n_before,
        f"the backpack moved by {len(backpack(P)) - n_before}",
    )

    # --- what gets recorded about each one ----------------------------------------------------
    if made:
        weapon = made[0]
        kind = GC._kind_of(weapon)
        numbers = reportjob.read_numbers(weapon)
        check(
            "each gun is filed under a kind of gun rather than under nothing",
            bool(kind) and kind != "unknown",
            f"the first one came back as {kind!r}",
        )
        check(
            "a gun made this way reports numbers, and not all zeroes",
            bool(numbers) and any(numbers.values()),
            f"{numbers}",
        )
        kinds = sorted({GC._kind_of(w) for w in made})
        print(f"   kinds seen across {len(made)} guns: {kinds}")
        check(
            "the rarity of a made gun can be read",
            GC._rarity(weapon) >= 0,
            GC._rarity(weapon),
        )

    # --- running it, a slice at a time ----------------------------------------------------------
    GC.enabled.value = True
    GC.census_level.value = 40
    started = reportjob.start(GC.OWNER, GC.NAME, GC._work, 3)
    check("the census starts", started and reportjob.busy() == GC.NAME, reportjob.busy())
    if started:
        for _ in range(200):
            if reportjob.busy() != GC.NAME:
                break
            reportjob.pump(GC.OWNER)
        written = reportjob.REPORTS / "gun-census.txt"
        check(
            "the census writes its report as it goes rather than at the end",
            written.is_file() and written.stat().st_size > 0,
            f"{written.stat().st_size if written.is_file() else 'missing'} bytes",
        )
        reportjob.cancel(GC.OWNER)
        check(
            "the backpack is untouched by a census run",
            len(backpack(P)) == n_before,
            f"the backpack moved by {len(backpack(P)) - n_before}",
        )

    # --- the readout, against a table we control -------------------------------------------------
    SAID.clear()
    CENSUS.unlink(missing_ok=True)
    GC._judge()
    check(
        "asking how good a gun is before the census has run says so plainly",
        bool(SAID) and "census" in SAID[-1].lower(),
        SAID[-1] if SAID else "it said nothing at all",
    )

    held = GC._held_weapon(P)
    check("the gun in your hands can be found", held is not None, held)
    if held is not None:
        kind = GC._kind_of(held)
        mine = reportjob.read_numbers(held)
        main = sorted(mine)[0] if mine else "InstantHitDamage"
        main = "InstantHitDamage" if "InstantHitDamage" in mine else main
        ours = mine.get(main, 0.0)
        # A made-up table: three guns of this kind, two of them worse than yours and one
        # better. The readout must therefore say it beats two of three.
        CENSUS.write_text(json.dumps({
            "level": int(GC.census_level.value),
            "made_by": "a made-up table written by the check file",
            "numbers": [main],
            "guns": [
                {"gun": "worse_one", "kind": kind, "rarity": 3, "numbers": {main: ours - 100}},
                {"gun": "worse_two", "kind": kind, "rarity": 3, "numbers": {main: ours - 50}},
                {"gun": "better_one", "kind": kind, "rarity": 5, "numbers": {main: ours + 100}},
            ],
        }), encoding="utf-8")
        SAID.clear()
        GC._judge()
        check(
            "the readout counts how many guns of its own kind yours beats",
            bool(SAID) and "beats 2 of 3" in SAID[-1].lower(),
            SAID[-1] if SAID else "it said nothing at all",
        )
        check(
            "the readout never says a gun is simply better",
            bool(SAID) and "better" not in SAID[-1].lower(),
            SAID[-1] if SAID else "",
        )

except Exception:
    import traceback
    print("\n--- this file raised; the checks below this point never ran ---")
    traceback.print_exc()

finally:
    reportjob.cancel(GC.OWNER)
    reportjob.say = REAL_SAY
    GC.enabled.value, GC.census_level.value, GC.work_per_frame.value = SAVED
    CENSUS.unlink(missing_ok=True)
    if BACKUP.is_file():
        BACKUP.replace(CENSUS)
    manager = P.GetPawnInventoryManager()
    left = [i for i in backpack(P) if str(i) not in KEEP]
    for item in left:
        try:
            manager.RemoveInventoryFromBackpack(item)
        except Exception as ex:
            print(f"could not remove {item}: {ex!r}")
    print(f"\nput the real census file back, removed {len(left)} strays")
    if SAID:
        print("it said: " + " | ".join(SAID[-6:]))

summary()
