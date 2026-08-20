# Sharp textures - the half that only a pair of eyes can settle.
#
# There is no property anywhere that reports whether texture fading is on, which is the entire
# reason features/texturefade.py has to track it rather than read it. So the only honest test is
# to load a map, walk up to a wall, and look at it. This file does the moving and the flipping;
# the person watching does the judging and answers two questions at the end.
#
# THE SEQUENCE THE OPERATOR RUNS, from the game folder. Nothing here waits - waiting is the
# shell's job, because a wait inside a bridge request freezes the frame it is running in.
#
#   bash bl2-mcp/tools/cycle.sh                                  # fresh game, character in world
#   bash bl2-mcp/tools/ask.sh bl2-mcp/tools/harness.py           # harness into that same session
#   echo 'print(travel_to("Three Horns Divide"))' | bash bl2-mcp/tools/ask.sh
#   sleep 60
#   echo 'print(where())' | bash bl2-mcp/tools/ask.sh            # repeat until it is not "loader"
#   ASK_TIMEOUT=90 bash bl2-mcp/tools/ask.sh bl2-mcp/tools/checks/texturefade-needs-travel.py
#
# Any outdoor map with a long view will do. A big open one is the point: fading is easiest to see
# when a lot of texture is streaming in at once, which is why an indoor room is a bad test.
#
# WHAT THE WATCHER HAS TO DO, because this script cannot:
#
#   1. Before running it, spin the camera around once and watch a distant wall as it comes into
#      view. Note whether it arrives sharp or blurs in over about a second.
#   2. Run this file. It flips the fading ONCE and leaves it flipped.
#   3. Spin around again and watch the same wall. If step 1 was blurry and step 3 is sharp, the
#      pack's belief about the state was WRONG and this flip corrected it - leave it. If step 1
#      was sharp and step 3 blurs, the belief was RIGHT, so run the file a second time to put it
#      back where it was.
#
# The screenshots below are taken for the record. They are not the test: a still frame cannot show
# a fade, because the fade is a thing that happens over time. Only the moving picture settles it.
#
# What this leaves behind: the fading flipped an odd number of times, on purpose, and the tracked
# state moved with it. Nothing else is touched, nothing is spawned and no gear is involved.

from bl2_modern.features import texturefade as t

reset()

print(f"where: {where()}")
print(f"the pack believes texture fading is {'OFF' if t._fade_is_off else 'ON'} "
      f"(None means it has not worked it out yet: {t._fade_is_off})")
print(f"the separate {t.OTHER_MOD} mod is {'loaded' if t._other_mod_ran() else 'not loaded'}")

check(
    "there is a map loaded to look at, not the menu",
    where().lower() not in ("loader", ""),
    f"map is {where()!r} - in the menu there is no wall to watch",
)

screenshot()
print("screenshot 1 asked for: this is BEFORE the flip")

before = t._fade_is_off
t._flip_by_hand.callback()
check(
    "the flip went through and the pack now believes the opposite",
    t._fade_is_off is not None and t._fade_is_off != before,
    f"believed {before}, now believes {t._fade_is_off}",
)

screenshot()
print("screenshot 2 asked for: this is AFTER the flip")
print(
    "NOW LOOK AT THE GAME. Spin the camera and watch a far wall come into view. Sharp straight "
    "away means fading is off. A second of blur means it is on. Then answer, by hand:\n"
    "   was it fading BEFORE this ran, and is it fading now?\n"
    "If it is fading NOW, run this file once more to put it back.",
)

summary()
