# One key refills everything - the half that needs to be somewhere with machines
# Run: bash bl2-mcp/tools/ask.sh bl2-mcp/tools/checks/one-key-refill-needs-travel.py
#
# THIS FILE IS TWO REQUESTS, NOT ONE. A map change cannot be waited for inside a bridge request -
# waiting freezes the game, see the note at the top of harness.py - so the travel is sent, the
# shell polls where() until it moves, and then this is sent again.
#
# THE SEQUENCE:
#
#   STEP 1  this file with STEP = 1     - travels to Sanctuary, where the three machines stand
#                                         side by side, and returns immediately
#           poll where() until it says Sanctuary
#   STEP 2  this file with STEP = 2     - stands at the machines and does the real thing, for
#                                         real money, then puts the money back
#
# STEP 2 SPENDS REAL MONEY AND REALLY REFILLS. That is the point of it: everything the other
# check file does is driven through stand-ins, so this is the only place the actual purchase
# functions are ever run. It reads the wallet before and after and hands the difference back, so
# the character ends where it started - but it cannot un-fire the ammo it just bought you.

reset()

from bl2_modern.features import vendorrefill as V

STEP = globals().get("STEP", 1)

if STEP == 1:
    print("in %s, travelling to Sanctuary" % (where(),))
    travel_to("Sanctuary")
    print("asked. Poll where() until it changes, then send this file again with STEP = 2.")

elif STEP == 2:
    p = pc()
    found = V._machines(p)
    kinds = []
    for gap, machine in found[:12]:
        try:
            kinds.append((round(gap), str(machine.ShopType)))
        except Exception:
            pass
    check(
        "there are machines here to stand at",
        bool(found),
        "nearest twelve: %s" % (kinds,),
    )
    near = [pair for pair in found if pair[0] <= float(V.reach.value)]
    check(
        "at least two different kinds of machine are within reach of one spot, which is the "
        "whole reason this feature exists",
        len({str(m.ShopType) for _, m in near}) >= 2,
        "within %s units: %s. If this fails, move to stand between the machines and run it "
        "again - or the reach setting is too small for this room"
        % (V.reach.value, [(round(g), str(m.ShopType)) for g, m in near]),
    )

    before = money(p)
    V.enabled.value = True
    # The @keybind decorator replaces the function with the bind object itself; the function
    # lives on .callback (measured 2026-08-20: calling the bare name raised "'KeybindType'
    # object is not callable").
    V._on_key.callback()
    after = money(p)
    check(
        "one press really moves money, so the purchase actually happened",
        after != before,
        "$%s -> $%s. Equal money can be honest - full health, full ammo and no junk - so "
        "fire a few shots and take some damage before running this" % (before, after),
    )

    if after != before:
        add_money(before - after)
    check(
        "the money this check spent has been handed back",
        money(p) == before,
        "$%s -> $%s -> $%s" % (before, after, money(p)),
    )

summary()
