# Skill build slots - can the tree be read, does a build survive a save and load, and does an
# unaffordable build refuse to respec? Run:
#   bash bl2-mcp/tools/ask.sh bl2-mcp/tools/checks/skill-build-slots.py
#
# NOTHING HERE RESPECS YOUR CHARACTER. Every path that would spend or refund a real skill point is
# driven through a stand-in controller that records the calls instead of making them, so the tree
# you are running is read many times and written never. The one real respec is in
# skill-build-slots-needs-travel.py, which says so at the top and tells you to save first.
reset()

import unrealsdk
from bl2_modern.features import skillbuilds as S

p = pc()

builds_before = dict(S._saved())
waiting_before = dict(S._waiting_for)
ticks_before = S._waiting_ticks
enabled_before = S.enabled.value


class _RecordingPC(object):
    """
    The real controller for everything except the two calls that change a skill tree.

    Those two are recorded and swallowed. That is what makes it safe to drive the whole load path
    against the character you are actually playing.
    """

    def __init__(self, real):
        object.__setattr__(self, "_real", real)
        object.__setattr__(self, "resets", 0)
        object.__setattr__(self, "upgrades", [])

    def __getattr__(self, name):
        return getattr(object.__getattribute__(self, "_real"), name)

    def ServerPurchaseSkillTreeReset(self):
        object.__setattr__(self, "resets", object.__getattribute__(self, "resets") + 1)

    def ServerUpgradeSkill(self, skill):
        object.__getattribute__(self, "upgrades").append(str(skill.Name))


fake = _RecordingPC(p) if p is not None else None

try:
    check(
        "there is a live character with a skill tree to read",
        p is not None and S._tree(p) is not None,
        f"controller={p}, tree={S._tree(p) if p is not None else None}",
    )

    from bl2_modern import core

    mine = [f for f in core.all_features() if f.name == "Skill build slots"]
    check(
        "the skill build feature loaded",
        len(mine) == 1 and mine[0].failed is None,
        f"found {len(mine)}; failure={mine[0].failed if mine else 'n/a'}",
    )
    check(
        "it ships switched off, because loading a build respecs your character",
        S.enabled.default_value is False,
        f"default is {S.enabled.default_value!r}",
    )
    check(
        "builds are stored on the character rather than once for the machine",
        S.PER_CHARACTER,
        f"PER_CHARACTER={S.PER_CHARACTER}; on the fallback path both characters would share a list",
    )
    if mine:
        check(
            "the tick hook that finishes a load was handed to the mod menu",
            len(mine[0].hooks) == 1,
            f"{len(mine[0].hooks)} hooks registered",
        )

    # --- reading the tree ------------------------------------------------------------------
    tree = S._tree(p) if p is not None else None
    walked = S._walk(p) if p is not None else []
    check(
        "every skill in the tree can be walked, branch by branch and tier by tier",
        len(walked) > 20,
        f"walked {len(walked)} skills across "
        f"{len({b for b, _ in walked})} branches. A Borderlands 2 character has three branches of "
        f"about a dozen skills, so anything under 20 means the walk is missing tiers",
    )
    # A branch must appear as one unbroken run. Interleaving them would spend a point in branch
    # two's tier three before branch one's tier three was paid for, and the game would refuse it.
    order = [b for b, _ in walked]
    runs = [b for i, b in enumerate(order) if i == 0 or order[i - 1] != b]
    check(
        "the walk finishes one branch before starting the next, which is a legal spend order",
        len(runs) == len(set(runs)),
        f"branches appear in this order: {runs} - a repeat means the walk jumps between them",
    )

    build_now = S._read_build(p) if p is not None else {}
    grades = build_now.get("grades") or {}
    check(
        "the grade of each skill can be read",
        S._grade_source != "",
        f"_grade_source={S._grade_source!r} - this names WHICH way of asking worked, and empty "
        f"means neither GetSkillState nor the flat Skills list answered",
    )

    # The cross-check that can actually come back wrong: what we counted, against what the game
    # says it has spent. These are two independent routes to the same number.
    game_says = -1
    if tree is not None:
        try:
            game_says = int(tree.GetSkillPointsSpentInTree())
        except Exception as ex:
            print(f"GetSkillPointsSpentInTree unavailable: {ex!r}")
    counted = sum(grades.values())
    check(
        "the points we counted match the number the game says are spent",
        game_says < 0 or abs(game_says - counted) <= 1,
        f"walked and counted {counted}, the game says {game_says}. One apart is the action skill, "
        f"which the game may or may not count; anything further means the walk is missing skills",
    )

    available = S._points_available(p) if p is not None else -1
    check(
        "the points available after a respec is at least what is already spent",
        available >= counted,
        f"available={available}, already spent={counted} - a respec hands the spent ones back, "
        f"so this can never be smaller",
    )

    # --- saving, renaming and deleting, through the real menu --------------------------------
    boxes = record(S)
    try:
        S.enabled.value = True
        S.builds.value = {}
        S._busy = False
        S._open_menu(p)
        check(
            "the menu opens and offers to save what you are running",
            len(boxes) == 1 and "Save what I am running now" in boxes[0].names(),
            f"boxes={len(boxes)}, buttons={boxes[0].names() if boxes else []}",
        )
        check(
            "with nothing saved, there is nothing to load, rename or delete",
            len(boxes) == 1 and len(boxes[0].names()) == 1,
            f"buttons offered with an empty list: {boxes[0].names() if boxes else []}",
        )

        pick(boxes[0], "Save what I am running now")
        check(
            "picking save asks what to call it",
            len(boxes) == 2 and len(boxes[1].names()) > 3,
            f"name choices: {boxes[1].names() if len(boxes) > 1 else []}",
        )
        if len(boxes) > 1:
            first_name = boxes[1].names()[0]
            pick(boxes[1], first_name)
            saved = S._saved()
            check(
                "saving stores the build under the chosen name",
                first_name in saved,
                f"stored names: {sorted(saved)}",
            )
            check(
                "the stored build holds the same points the tree does",
                sum((saved.get(first_name, {}).get("grades") or {}).values()) == counted,
                f"stored {sum((saved.get(first_name, {}).get('grades') or {}).values())} points, "
                f"the tree has {counted}",
            )
            check(
                "skills are stored by name, so a patch that moves one between branches cannot "
                "turn a saved build into a different build",
                all(isinstance(k, str) and not k.isdigit()
                    for k in (saved.get(first_name, {}).get("grades") or {})),
                f"keys look like {list((saved.get(first_name, {}).get('grades') or {}))[:3]}",
            )

            # rename
            del boxes[:]
            S._choose_build(p, "rename")
            pick(boxes[0], first_name)
            new_name = boxes[1].names()[0]
            pick(boxes[1], new_name)
            saved = S._saved()
            check(
                "renaming moves the build and leaves no copy behind",
                new_name in saved and first_name not in saved and len(saved) == 1,
                f"names are now {sorted(saved)}",
            )

            # delete
            del boxes[:]
            S._choose_build(p, "delete")
            pick(boxes[0], new_name)
            check(
                "deleting a build forgets it",
                new_name not in S._saved(),
                f"names are now {sorted(S._saved())}",
            )
            check(
                "deleting a build did not touch the character's actual skill tree",
                sum((S._read_build(p).get("grades") or {}).values()) == counted,
                f"the tree holds {sum((S._read_build(p).get('grades') or {}).values())} points, "
                f"it held {counted} before",
            )
    finally:
        restore()

    # --- the refusal that protects the character ---------------------------------------------
    # A build nobody could afford must be turned away BEFORE the respec, or the player is left
    # with an emptied tree and a build that will not fit in it.
    if fake is not None and walked:
        too_much = {str(skill.Name): 5 for _b, skill in walked}
        S._waiting_for = {}
        S._apply(fake, {"grades": too_much})
        check(
            "a build that costs more points than the character has is refused",
            fake.resets == 0,
            f"the respec was called {fake.resets} times for a build costing "
            f"{sum(too_much.values())} points against {available} available",
        )
        check(
            "a refused build leaves nothing waiting to be spent",
            not S._waiting_for,
            f"_waiting_for holds {len(S._waiting_for)} skills after a refusal",
        )
        check(
            "a refused build spends nothing",
            not fake.upgrades,
            f"{len(fake.upgrades)} skill upgrades were fired for a build that was refused",
        )

    # --- the load path, end to end, against the recorder --------------------------------------
    if fake is not None and walked and grades:
        S._waiting_for = {}
        S._waiting_ticks = 0
        S._apply(fake, {"grades": dict(grades)})
        check(
            "an affordable build asks the game to respec",
            fake.resets == 1,
            f"the respec was called {fake.resets} times",
        )
        check(
            "the points are not spent in the same breath as the respec",
            not fake.upgrades and bool(S._waiting_for),
            f"{len(fake.upgrades)} upgrades fired immediately, {len(S._waiting_for)} skills "
            f"waiting. Spending before the respec has come back is exactly what breaks this on "
            f"the machine that is not hosting",
        )

        # The tree still has points in it, because nothing really respecced. So the waiting build
        # must keep waiting rather than spend into a full tree.
        S._spend_if_the_tree_is_empty(fake)
        check(
            "the waiting build refuses to spend while the old tree is still full",
            not fake.upgrades and bool(S._waiting_for),
            f"{len(fake.upgrades)} upgrades fired while {counted} points were still spent",
        )

        # Now pretend the respec landed, by making the reader report an empty tree.
        real_read = S._read_build
        S._read_build = lambda _pc: {"grades": {}, "points": 0}
        try:
            S._spend_if_the_tree_is_empty(fake)
        finally:
            S._read_build = real_read
        asked = sum(grades.values())
        # One extra for the action skill, which takes the first point back.
        check(
            "once the tree is empty the whole build is spent back in, one call per point",
            len(fake.upgrades) in (asked, asked + 1),
            f"{len(fake.upgrades)} upgrade calls for {asked} points (plus one for the action "
            f"skill). Too few means points were dropped; too many means points were double spent",
        )
        check(
            "the build stops waiting once it has been spent",
            not S._waiting_for,
            f"_waiting_for still holds {len(S._waiting_for)} skills",
        )

        # And the give-up path, so a respec that never comes back does not wait forever.
        fake.upgrades[:] = []
        S._waiting_for = dict(grades)
        S._waiting_ticks = S.GIVE_UP_AFTER + 1
        S._spend_if_the_tree_is_empty(fake)
        check(
            "a respec that never arrives is given up on rather than waited for forever",
            not S._waiting_for and not fake.upgrades,
            f"_waiting_for holds {len(S._waiting_for)}, {len(fake.upgrades)} upgrades fired",
        )

    # --- the tick hook costs nothing when there is nothing to do -------------------------------
    S._waiting_for = {}
    looks = []
    real_spend = S._spend_if_the_tree_is_empty
    S._spend_if_the_tree_is_empty = lambda controller: looks.append(controller)
    try:
        for _ in range(600):
            S.on_tick(p, None, None, None)
    finally:
        S._spend_if_the_tree_is_empty = real_spend
    check(
        "the tick hook does nothing at all when no build is being loaded",
        not looks,
        f"it looked at the tree {looks and len(looks) or 0} times over 600 frames with nothing "
        f"waiting; this hook runs on every single frame of the game",
    )

finally:
    S._waiting_for = waiting_before
    S._waiting_ticks = ticks_before
    S.enabled.value = enabled_before
    S.builds.value = builds_before
    S._busy = False
    restore()
    print(
        f"cleanup: saved builds restored to {sorted(builds_before)}; the skill tree was never "
        f"written to - it holds "
        f"{sum((S._read_build(p).get('grades') or {}).values()) if p is not None else '?'} points"
    )

summary()
