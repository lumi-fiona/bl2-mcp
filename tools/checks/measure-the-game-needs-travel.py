# The four measuring features, run to completion - patchproof, bestpart, guncensus, lootindex
#
# WHY THIS IS A SEPARATE FILE. All four are deliberately spread across frames: they do a few
# milliseconds of work per tick and hand the game back. Running one to the end inside a single
# bridge request would mean holding the frame open for minutes, which is the one thing a
# request may never do (harness.py:9-21). So the waiting is done OUT HERE, by the shell,
# between requests.
#
# THE SEQUENCE. Each numbered block is one request, and the poll between them is the shell's
# job, not this file's. Nothing below sleeps or loops waiting for anything.
#
#   0. Load the harness once:
#        bash bl2-mcp/tools/ask.sh bl2-mcp/tools/harness.py
#
#   1. Start whichever job you are proving. Copy ONE of these into a request:
#
#        from bl2_modern import reportjob
#        from bl2_modern.features import patchproof as F; reportjob.start(F.OWNER, F.NAME, F._work, 6)
#        from bl2_modern.features import lootindex as F;  reportjob.start(F.OWNER, F.NAME, F._work, 6)
#        from bl2_modern.features import guncensus as F;  reportjob.start(F.OWNER, F.NAME, F._work, 6)
#
#      The part bench needs a gun chosen first, so it is:
#        from bl2_modern.features import bestpart as F
#        gun = next(i for i in F._carried(pc()) if F._is_weapon(i))
#        reportjob.start(F.OWNER, F.NAME, lambda: F._work_for(gun), 6)
#
#   2. Wait, from the shell, and watch it move. Poll this every ten seconds or so:
#
#        from bl2_modern import reportjob; print(reportjob.busy())
#
#      It prints the job's name while it runs and None when it is done. The proof-read should
#      take under a minute; the census depends on how many guns are loaded. If it prints None
#      immediately, read the report file - the job stopped early and wrote why.
#
#   3. When busy() is None, run this file to check what came out.
#
# WHAT NEEDS A MAP CHANGE. The proof-read's "not loaded" count is the honest measure of how
# much of the patch cannot be seen from where you are standing. Run step 1 in Sanctuary, note
# the count, then travel_to("Frostburn Canyon") - wait for where() to change from outside -
# and run it again. The two runs should show a different "not loaded" count and different
# lines under it. If they are identical, the map-specific half of the patch is not being read
# at all, which is the same silent failure that cost this pack 479 commands once already
# (core.py:401-408).
#
# The loot index has the same property for a different reason: it can only see pools the game
# has loaded, so its pool count should go UP after visiting more of the world. Two runs an
# hour apart with the same count means it is not seeing map loot at all.

reset()
from bl2_modern import reportjob

check(
    "nothing is still running, so these reports are finished ones",
    reportjob.busy() is None,
    f"still running: {reportjob.busy()}",
)

REPORTS = reportjob.REPORTS
print(f"reports live in {REPORTS}")

for name, wanted in (
    ("patch-proof-read.txt", "the count"),
    ("loot-index.txt", "where each thing comes from"),
    ("gun-census.txt", "guns measured"),
):
    path = REPORTS / name
    if not path.is_file():
        print(f"   {name}: not written yet, skipped")
        continue
    text = path.read_text(encoding="utf-8", errors="replace")
    check(
        f"{name} was written all the way to the end",
        wanted in text,
        f"{len(text.splitlines())} lines, {path.stat().st_size} bytes",
    )
    print(f"--- the last 12 lines of {name} ---")
    for line in text.splitlines()[-12:]:
        print("   " + line)

proof = REPORTS / "patch-proof-read.txt"
if proof.is_file():
    text = proof.read_text(encoding="utf-8", errors="replace")
    numbers = {}
    for line in text.splitlines():
        pieces = line.strip().split(None, 1)
        if len(pieces) == 2 and pieces[0].isdigit():
            numbers[pieces[1]] = int(pieces[0])
    print(f"   the proof-read counted: {numbers}")
    total = sum(numbers.get(k, 0) for k in ("landed", "did nothing", "not loaded", "cannot tell"))
    check(
        "the proof-read could judge most of the lines it read",
        total > 0 and numbers.get("cannot tell", 0) / total <= 0.05,
        f"{numbers.get('cannot tell', 0)} of {total} could not be judged - over one in "
        "twenty means the lookup is the bug, not the patch",
    )
    check(
        "the proof-read found lines that really landed",
        numbers.get("landed", 0) > 0,
        f"{numbers.get('landed', 0)} landed - zero would mean nothing is being read at all",
    )
    print(f"   'not loaded' from where you are standing: {numbers.get('not loaded', 0)}")
    print("   run this again from a different map and compare that number")

summary()
