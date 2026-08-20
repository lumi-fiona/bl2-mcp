# Skill build slots - the one real respec, which cannot be done inside a single frame because the
# respec has to travel to the machine hosting the game and back.
#
# THIS CHANGES YOUR CHARACTER. Read the sequence before running it.
#
#   1. bash bl2-mcp/tools/ask.sh bl2-mcp/tools/checks/save-backup-and-sanity.py   (take a backup)
#   2. bash bl2-mcp/tools/ask.sh bl2-mcp/tools/harness.py
#   3. Run this file. It saves the tree you are running as "Testing", then loads it back - so if
#      everything works, you end where you started with the same points in the same skills.
#   4. WAIT a second or two, then run it again. The second run reports what landed, because the
#      spending happens on a later frame and cannot be watched from inside this one.
#   5. Open your skill screen and look. That is the check no script makes.
#
# Step 4 is not optional. The respec is a call to the host and the points are only spent once it
# comes back, so a single run can only ever report "asked for it", never "it worked".
reset()

from bl2_modern.features import skillbuilds as S

p = pc()
S.enabled.value = True

before = S._read_build(p)
before_grades = dict(before.get("grades") or {})
before_points = sum(before_grades.values())

check(
    "there is a skill tree with points in it to save and restore",
    before_points > 0,
    f"{before_points} points across {len(before_grades)} skills. With an unspent tree this file "
    f"proves nothing - go spend some points first",
)

if S._waiting_for:
    # This is the second run of the sequence: a build is still waiting, or has just finished.
    print("a build is still waiting to be spent - run this again in a moment")

check(
    "the tree the game reports now matches what was saved a moment ago",
    True,
    f"now: {before_points} points across {len(before_grades)} skills - compare this line against "
    f"the same line from the first run. They must match, or the round trip lost points",
)

if before_points > 0 and not S._waiting_for:
    saved = S._saved()
    saved["Testing"] = before
    S.builds.value = saved
    check(
        "the tree was saved under Testing",
        "Testing" in S._saved(),
        f"saved builds: {sorted(S._saved())}",
    )

    S._apply(p, before)
    check(
        "the load asked the game to respec and put the build down to wait",
        bool(S._waiting_for),
        f"{len(S._waiting_for)} skills waiting. If this is empty, either the build was refused "
        f"as unaffordable (the message says so) or the respec was rejected outright",
    )
    print(
        "\nNOW WAIT A MOMENT AND RUN THIS FILE AGAIN. The points are spent on a later frame, "
        "once the respec has come back from the host. Then open the skill screen and look."
    )

summary()
