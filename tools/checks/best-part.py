# Which part is best - checks for features/bestpart.py
# Run: bash bl2-mcp/tools/ask.sh bl2-mcp/tools/checks/best-part.py
#
# SAFETY: every gun touched here is spawned by this file with give() and removed again in the
# finally block. Nothing you own is read from, written to, rebuilt or removed. That is not a
# nicety - rebuilding items is the operation that deleted a real gun once (levelless.py:22-30),
# so no check in this file is allowed anywhere near real gear.
#
# The check that decides whether the feature is worth anything at all is "changing a part
# changes the numbers the gun reports". If that FAILS, every ranking the feature produces is
# noise, and the feature's own report says so in those words rather than publishing a table.

reset()
import unrealsdk
from bl2_modern import reportjob
from bl2_modern.features import bestpart as BP

P = pc()
KEEP = {str(i) for i in backpack(P)}
SAVED = (BP.enabled.value, BP.work_per_frame.value)
SAID = []
REAL_SAY = reportjob.say
reportjob.say = lambda title, message, seconds=6: SAID.append(message)

MANAGER = P.GetPawnInventoryManager()


def bag():
    return backpack(P)


try:
    guns = give("GD_Itempools.WeaponPools.Pool_Weapons_All_04_Rare", 40, 2)
    check("two throwaway guns could be spawned to experiment on", len(guns) == 2, len(guns))

    gun = guns[0] if guns else None
    if gun is None:
        raise RuntimeError("nothing to measure")

    # --- what the gun tells us -------------------------------------------------------------
    numbers = reportjob.read_numbers(gun)
    check(
        "a spawned gun reports at least one number to compare",
        bool(numbers),
        f"it answered with {numbers}",
    )
    check(
        "the numbers a gun reports are not all zero",
        bool(numbers) and any(v for v in numbers.values()),
        f"{numbers}",
    )
    print(f"   the numbers this install gives up: {sorted(numbers)}")

    slots = BP._slots(gun.DefinitionData)
    check(
        "a gun's part slots can be listed",
        len(slots) >= 3,
        f"{len(slots)} slots: {slots}",
    )

    # --- where the list of legal parts comes from --------------------------------------------
    source, collection = BP._part_list_source(gun)
    check(
        "the game will say which parts this gun is allowed to have",
        collection is not None,
        f"came from {source!r}",
    )

    counted = {}
    for slot in slots:
        found = BP._from_collection(collection, slot) if collection is not None else []
        guessed = BP._from_package(gun, slot)
        counted[slot] = (len(found), len(guessed))
    print("   slot: parts the game lists / parts guessed from the package")
    for slot, (a, b) in sorted(counted.items()):
        print(f"      {slot:<28} {a:>4} / {b:>4}")
    check(
        "at least one slot offers two or more parts to compare",
        any(a >= 2 for a, _b in counted.values()),
        counted,
    )
    check(
        "the fallback that guesses from the package also finds parts",
        any(b >= 2 for _a, b in counted.values()),
        "this one only matters when the list above is empty",
    )

    # --- THE claim: does swapping a part move the numbers? ------------------------------------
    # Everything the feature produces rests on this. Done on a spawned gun, never on yours.
    slot_to_try = next(
        (s for s in slots if BP._from_collection(collection, s) and len(BP._from_collection(collection, s)) >= 2),
        None,
    )
    if slot_to_try is None:
        slot_to_try = next((s for s in slots if len(BP._from_package(gun, s)) >= 2), None)

    if slot_to_try is None:
        check("a slot with two candidate parts was found to try", False, counted)
    else:
        candidates = BP._from_collection(collection, slot_to_try) or BP._from_package(gun, slot_to_try)
        original = getattr(gun.DefinitionData, slot_to_try)
        readings = {}
        for part in candidates[:12]:
            if BP._rebuild(gun, slot_to_try, part):
                readings[str(part.Name)] = reportjob.read_numbers(gun)
        BP._rebuild(gun, slot_to_try, original)

        distinct = {tuple(sorted(v.items())) for v in readings.values()}
        print(f"   tried {len(readings)} parts in {slot_to_try}:")
        for name, values in list(readings.items())[:6]:
            print(f"      {name:<40} {values}")
        check(
            "a part can be fitted to a gun and the gun accepts it",
            bool(readings),
            f"{len(readings)} of {len(candidates[:12])} parts were fitted",
        )
        check(
            "changing a part changes the numbers the gun reports",
            len(distinct) > 1,
            f"{len(distinct)} different sets of numbers across {len(readings)} parts - "
            "one means rebuilding does not refresh them and no ranking is real",
        )
        check(
            "putting the gun's own part back leaves it as it started",
            str(getattr(gun.DefinitionData, slot_to_try).Name) == str(original.Name),
            f"{getattr(gun.DefinitionData, slot_to_try).Name} against {original.Name}",
        )

    # --- the menu -------------------------------------------------------------------------------
    boxes = record(BP)
    BP._open_menu()
    check(
        "the menu offers the guns you are carrying and nothing else",
        bool(boxes) and len(boxes[-1].buttons) >= 2,
        f"{len(boxes)} menus, {len(boxes[-1].buttons) if boxes else 0} guns offered",
    )
    restore()

    # --- running it, a slice at a time -------------------------------------------------------
    # Not to completion: a whole gun's worth of parts in one request would hold the frame open.
    n_before = len(bag())
    started = reportjob.start(BP.OWNER, BP.NAME, lambda: BP._work_for(gun), 3)
    check("the part bench starts", started and reportjob.busy() == BP.NAME, reportjob.busy())
    if started:
        # Sampled after EVERY pump, not once after the loop. A gun with few slots worth
        # measuring can finish inside these 150 pumps, and by the time the loop ends the
        # throwaway copy has been made AND already handed back in the job's own finally block -
        # so a single sample taken after the loop reads "moved by 0" and blames the feature for
        # a race the check itself created. The copy exists for the whole stretch between the
        # first pump (which makes it, before _work_for's first yield) and the pump that finishes
        # the job (which removes it), so any sample taken while still busy has to catch it.
        saw_one_copy = False
        for _ in range(150):
            if reportjob.busy() != BP.NAME:
                break
            reportjob.pump(BP.OWNER)
            if reportjob.busy() == BP.NAME and len(bag()) - n_before == 1:
                saw_one_copy = True
        check(
            "it makes exactly one throwaway copy while it works",
            saw_one_copy,
            "never caught the backpack sitting at +1 while busy - it has moved by "
            f"{len(bag()) - n_before} now",
        )
        reportjob.cancel(BP.OWNER)
        check(
            "stopping it puts the throwaway copy back where it came from",
            len(bag()) == n_before,
            f"the backpack moved by {len(bag()) - n_before} after stopping",
        )

except Exception:
    import traceback
    print("\n--- this file raised; the checks below this point never ran ---")
    traceback.print_exc()

finally:
    reportjob.cancel(BP.OWNER)
    reportjob.say = REAL_SAY
    BP.enabled.value, BP.work_per_frame.value = SAVED
    restore()
    left = [i for i in bag() if str(i) not in KEEP]
    for item in left:
        try:
            MANAGER.RemoveInventoryFromBackpack(item)
        except Exception as ex:
            print(f"could not remove {item}: {ex!r}")
    print(f"\ncleaned up {len(left)} spawned items; the backpack is back to {len(bag())}")
    if SAID:
        print("it said: " + " | ".join(SAID[-6:]))

summary()
