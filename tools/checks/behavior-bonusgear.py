# New characters start without the DLC bonus guns - behavior checks for features/bonusgear.py
# Run: bash bl2-mcp/tools/ask.sh bl2-mcp/tools/checks/behavior-bonusgear.py   (after harness.py)
#
# Needs a character in the world, and runs the game's real grant on it: for one request the
# character's codes 2 and 3 are taken out of its list so the game treats it as new, and whatever the
# grant hands over is caught at the backpack door and never added. The codes, the notices and the
# switch are put back before the request ends, so no save can happen in between. Run it on a
# throwaway anyway. What a real new character gets was seen in the game (ticket 43): with the switch
# off the relic, three Gearbox guns and the Sky Rocket, with it on none of them.
reset()

import unrealsdk
from unrealsdk.hooks import Block, Type, add_hook, has_hook, remove_hook

from bl2_modern import core
from bl2_modern.features import bonusgear as BG

GEAR = {2: ["A_VaultHunter", "AR_Dahl_1_GBX", "SMG_Gearbox_1", "Sniper_Gearbox_1"], 3: ["GM_SkyRocket"]}
POOLS = {2: [], 3: ["DigitalEdHeads", "DigitalEdSkins"]}
ALL_GEAR = sorted(n for names in GEAR.values() for n in names)
GRANT = "WillowGame.WillowPlayerController:GrantNewMarketingCodeBonuses"
ADD = "WillowGame.WillowInventoryManager:AddClientSideInventoryToBackpackInventory"


def unlock(code):
    return unrealsdk.find_object("MarketingUnlockInventoryDefinition", BG.UNLOCKS[code - 2])


def lists():
    return {c: ([x.Name for d in unlock(c).UnlockItems for x in d.UnlockItems],
                [x.Name for d in unlock(c).UnlockItems for x in d.UnlockItemPools]) for c in GEAR}


FULL = {c: (GEAR[c], POOLS[c]) for c in GEAR}
caught = []


def catch(_obj, args, _ret, _func):
    caught.append(args.Inv)
    return Block


def block_grant(_obj, _args, _ret, _func):
    return Block


def grant_as_new(p, codes):
    """The real grant, on this character pretending it has never had codes 2 and 3."""
    p.UsedMarketingCodes = [c for c in codes if c not in (2, 3)]
    caught.clear()
    p.GrantNewMarketingCodeBonuses()
    names = sorted(i.DefinitionData.BalanceDefinition.Name for i in caught)
    for item in caught:
        item.LifeSpan = 0.1  # Destroy() from Python leaves inventory behind (ticket 47)
    return names


feature = next((f for f in core.all_features() if f.name == "New characters start without the DLC bonus guns"), None)
check("the feature loaded", feature is not None and feature.failed is None, feature and feature.failed)
check("its switch is in the menu and on by default",
      feature is not None and BG.enabled in feature.options and BG.enabled.default_value is True)
check("both hooks sit on the game's grant",
      BG.on_grant.hook_funcs == [(GRANT, Type.PRE)] and BG.on_granted.hook_funcs == [(GRANT, Type.POST_UNCONDITIONAL)],
      (BG.on_grant.hook_funcs, BG.on_granted.hook_funcs))
check("the two unlocks hold the gear and cosmetic pools this was built against", lists() == FULL, lists())

p = pc()
was = BG.enabled.value
codes0, notes0 = list(p.UsedMarketingCodes), list(p.MarketingCodesNeedingNotification)
check("the character in front of us already has codes 2 and 3, like every save here",
      {2, 3} <= set(codes0), codes0)
unlocked = {c: bool(p.IsMarketingCodeUnlocked(c)) for c in GEAR}

add_hook(ADD, Type.PRE, "check43", catch)
try:
    if check("this install owns both packs, so the grant has something to give", all(unlocked.values()), unlocked):
        BG.enabled.value = False
        off = grant_as_new(p, codes0)
        check("switch off: the grant hands over the relic, the three guns and the Sky Rocket", off == ALL_GEAR, off)

        BG.enabled.value = True
        on = grant_as_new(p, codes0)
        check("switch on: the same grant hands over none of that gear", not set(on) & set(ALL_GEAR), on)
        check("switch on: codes 2 and 3 are recorded all the same, so it lasts",
              {2, 3} <= set(p.UsedMarketingCodes), list(p.UsedMarketingCodes))
        check("switch on: the lists are back in full straight after", lists() == FULL, lists())

        # Another mod blocking the grant must not leave the lists empty - why the restore is
        # POST_UNCONDITIONAL. First the same restore as a plain POST hook, which must lose them
        # (so the blocked case really empties the lists); then the real one, which must not.
        add_hook(GRANT, Type.PRE, "check43-block", block_grant)
        try:
            BG.on_granted.disable()
            add_hook(GRANT, Type.POST, "check43-post", BG.on_granted.__wrapped__)
            try:
                grant_as_new(p, codes0)
                emptied = lists()
            finally:
                remove_hook(GRANT, Type.POST, "check43-post")
                BG.on_granted.enable()
                BG.on_granted.__wrapped__(p, None, None, None)  # puts back what that left held
            check("a grant another mod blocks: restored by a plain POST hook, the lists stay empty",
                  all(not gear for gear, _pools in emptied.values()), emptied)
            grant_as_new(p, codes0)
        finally:
            remove_hook(GRANT, Type.PRE, "check43-block")
        check("a grant another mod blocks: the real restore puts the lists back", lists() == FULL, lists())

        # A character that already has the codes: nothing is given, the switch either way.
        for state in (True, False):
            BG.enabled.value = state
            p.UsedMarketingCodes = codes0
            caught.clear()
            p.GrantNewMarketingCodeBonuses()
            check(f"switch {'on' if state else 'off'}: a character that has the codes is given nothing",
                  not caught and list(p.UsedMarketingCodes) == codes0, [i.Name for i in caught])
finally:
    remove_hook(ADD, Type.PRE, "check43")
    BG.enabled.value = was
    p.UsedMarketingCodes = codes0
    p.MarketingCodesNeedingNotification = notes0
    check("the codes, the notices, the switch, the lists and the restore hook are left as found",
          list(p.UsedMarketingCodes) == codes0 and list(p.MarketingCodesNeedingNotification) == notes0
          and BG.enabled.value == was and lists() == FULL and not BG._held
          and has_hook(GRANT, Type.POST_UNCONDITIONAL, BG.on_granted.hook_identifier),
          (list(p.UsedMarketingCodes), list(p.MarketingCodesNeedingNotification), BG.enabled.value, len(BG._held)))

summary()
