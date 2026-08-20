# Reward reroll - does the mechanism exist, and does the feature refuse to charge when it cannot
# deliver? Run: bash bl2-mcp/tools/ask.sh bl2-mcp/tools/checks/reward-reroll.py
#
# Nothing here needs a mission turn-in screen and nothing here turns a mission in. The parts that
# genuinely need a live reward screen are in reward-reroll-needs-travel.py.
#
# The one thing this file changes on your character is eridium, and only to prove the charge takes
# exactly the advertised amount. It is put back in the finally, and the amount put back is printed.
reset()

import unrealsdk
from bl2_modern.features import rewardreroll as R

# --- what we must be able to put back -----------------------------------------------------

p = pc()
enabled_before = R.enabled.value
cost_before = R.cost.value
key_before = R._reroll_key.key
pending_before = (R._pending_mission, R._pending_data)
last_at_before = R._last_reroll_at

ERIDIUM = unrealsdk.find_enum("ECurrencyType").CURRENCY_Eridium


def eridium():
    try:
        return int(p.PlayerReplicationInfo.GetCurrencyOnHand(ERIDIUM))
    except Exception:
        return -1


eridium_before = eridium()


class _FakeArgs(object):
    """Stands in for the argument struct a hook is handed. Plain attributes, nothing unreal."""

    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)


try:
    check(
        "there is a live character to test the reroll against",
        p is not None and eridium_before >= 0,
        f"controller={p}, eridium={eridium_before}",
    )

    # --- the feature is wired into the pack at all -----------------------------------------
    from bl2_modern import core

    mine = [f for f in core.all_features() if f.name == "Reward reroll"]
    check(
        "the reward reroll feature loaded",
        len(mine) == 1 and mine[0].failed is None,
        f"found {len(mine)} features called that; failure={mine[0].failed if mine else 'n/a'}",
    )
    if mine:
        check(
            "every hook the file declares was handed to the mod menu, so the off switch reaches them",
            len(mine[0].hooks) == 5,
            f"{len(mine[0].hooks)} hooks registered, the file declares 5",
        )
        check(
            "the reroll key was handed over so it can be rebound",
            len(mine[0].keybinds) == 1,
            f"{len(mine[0].keybinds)} keybinds registered",
        )
    check(
        "it ships switched off, because it changes how much gear a playthrough hands you",
        R.enabled.default_value is False,
        f"default is {R.enabled.default_value!r}",
    )

    # --- the mechanism this whole file rests on --------------------------------------------
    # The reward pair struct. If make_struct cannot build it, or WeaponRewards is not two long,
    # the class table was read wrong and everything downstream is wrong with it.
    blank = None
    try:
        blank = unrealsdk.make_struct("PendingMissionRewardData")
        made_err = ""
    except Exception as ex:
        made_err = repr(ex)
    check(
        "the game can build the reward pair struct the screens pass around",
        blank is not None,
        f"make_struct('PendingMissionRewardData') {made_err or 'worked'}",
    )
    if blank is not None:
        try:
            weapons = list(blank.WeaponRewards)
            items = list(blank.ItemRewards)
        except Exception as ex:
            weapons, items = [], []
            print(f"could not read the reward slots: {ex!r}")
        check(
            "the pair really is two weapons and two items, as the class table says",
            len(weapons) == 2 and len(items) == 2,
            f"WeaponRewards holds {len(weapons)}, ItemRewards holds {len(items)}",
        )

    # A real mission definition, so the game's own roller can be tried on something real.
    missions = [
        o for o in unrealsdk.find_all("MissionDefinition")
        if not o.Name.startswith("Default__")
    ]
    check(
        "there are mission definitions loaded to roll rewards from",
        len(missions) > 0,
        f"{len(missions)} MissionDefinition objects loaded",
    )

    rolled = None
    if missions and p is not None:
        # Prefer a mission that actually offers items - one with an empty reward list would roll
        # an empty pair and pass this check for the wrong reason.
        candidates = []
        for m in missions:
            try:
                if list(m.Reward.RewardItems) or list(m.Reward.RewardItemPools):
                    candidates.append(m)
            except Exception:
                continue
        check(
            "at least one loaded mission offers a choice of items",
            len(candidates) > 0,
            f"{len(candidates)} of {len(missions)} missions have RewardItems or RewardItemPools",
        )
        target = candidates[0] if candidates else missions[0]
        rolled = R._roll(target, p)
        check(
            "the game's own reward roller answers when asked to roll again",
            rolled is not None,
            f"MissionDefinition.GetItemRewardsForPlayer on {target.Name} gave {rolled!r}. "
            f"This is THE mechanism - if it fails, the feature cannot work at all and the "
            f"blocking approach in the backlog is the only route left",
        )

    if rolled is not None:
        # The mission and the alternate-reward flag must survive a reroll, or a player who earned
        # the better reward would quietly be handed the ordinary one.
        old = _FakeArgs(Mission=missions[0], bGrantAltReward=True)
        R._keep_the_parts_the_roll_should_not_decide(rolled, old)
        check(
            "a reroll cannot change which mission is being turned in",
            rolled.Mission is missions[0],
            f"Mission came back as {rolled.Mission}",
        )
        check(
            "a reroll cannot quietly take away the alternate reward you earned",
            bool(rolled.bGrantAltReward) is True,
            f"bGrantAltReward is {rolled.bGrantAltReward!r} after carrying True across",
        )

    # --- the refusals, which are the whole safety story ------------------------------------
    R.enabled.value = False
    R._last_reroll_at = -99.0
    spent = eridium()
    did = R._try_reroll("check")
    check(
        "switched off, the key does nothing and takes nothing",
        did is False and eridium() == spent,
        f"returned {did!r}, eridium {spent} -> {eridium()}",
    )

    R.enabled.value = True
    R._last_reroll_at = -99.0
    spent = eridium()
    did = R._try_reroll("check")
    check(
        "with no reward screen open, the key does nothing and takes nothing",
        did is False and eridium() == spent,
        f"returned {did!r}, eridium {spent} -> {eridium()}. There is no turn-in screen up, so "
        f"_reward_screen must come back empty and the function must stop before charging",
    )

    movie, reward = R._reward_screen(p)
    check(
        "the reroll can tell that no reward screen is showing",
        reward is None,
        f"_reward_screen found reward object {reward!r} while standing in the world",
    )

    # --- the charge takes exactly what it says ---------------------------------------------
    if p is not None and eridium_before >= 0:
        R.cost.value = 3
        before = eridium()
        took = R._charge(p, 3)
        after = eridium()
        check(
            "taking eridium takes exactly the advertised amount",
            took is True and after == before - 3,
            f"charged 3: {before} -> {after}",
        )
        # Straight back, so the rest of the file runs on the number the character started with.
        p.PlayerReplicationInfo.AddCurrencyOnHand(ERIDIUM, 3)

    # --- the debounce, so one press cannot cost two rerolls ---------------------------------
    R._last_reroll_at = R._now(p) if p is not None else 0.0
    spent = eridium()
    did = R._try_reroll("check")
    check(
        "a second trigger arriving in the same instant is ignored",
        did is False and eridium() == spent,
        f"returned {did!r} a fraction of a second after the last reroll",
    )

    # --- the substitution at grant time, and the bug it was written to avoid ----------------
    # This is the hook that makes a rerolled pair the one the game actually hands over. It must
    # never block, and it must never substitute a pair belonging to a different mission.
    if missions:
        this_mission = missions[0]
        other_mission = missions[1] if len(missions) > 1 else missions[0]
        marker = object()

        R._pending_mission = this_mission
        R._pending_data = marker
        args = _FakeArgs(Mission=this_mission, MissionReward="the game's own pair")
        ret = R.on_grant(None, args, None, None)
        check(
            "the rerolled pair is the one handed to the grant",
            args.MissionReward is marker,
            f"the grant was given {args.MissionReward!r}",
        )
        check(
            "the grant hook never blocks the grant",
            ret is None,
            f"on_grant returned {ret!r}; anything other than None risks stopping the reward",
        )
        check(
            "the pair is forgotten once it has been granted",
            R._pending_data is None,
            f"still holding {R._pending_data!r}",
        )

        if other_mission is not this_mission:
            R._pending_mission = this_mission
            R._pending_data = marker
            args = _FakeArgs(Mission=other_mission, MissionReward="the game's own pair")
            R.on_grant(None, args, None, None)
            check(
                "a pair rerolled for one mission is never substituted into another",
                args.MissionReward == "the game's own pair" and R._pending_data is None,
                f"the grant for a different mission was given {args.MissionReward!r}",
            )

        # The bug the CompleteMission hook was rewritten to avoid: clearing unconditionally there
        # would wipe the rerolled pair before the grant could use it.
        R._pending_mission = this_mission
        R._pending_data = marker
        R.on_mission_complete(None, _FakeArgs(InMission=this_mission), None, None)
        check(
            "turning in the mission you just rerolled does NOT throw the rerolled pair away",
            R._pending_data is marker,
            f"after CompleteMission for the same mission the pair is {R._pending_data!r}. If this "
            f"fails, a player pays eridium, watches the items change, and is handed the originals",
        )

        if other_mission is not this_mission:
            R._pending_mission = this_mission
            R._pending_data = marker
            R.on_mission_complete(None, _FakeArgs(InMission=other_mission), None, None)
            check(
                "turning in a different mission does throw a stale pair away",
                R._pending_data is None,
                f"the pair survived a different mission being completed: {R._pending_data!r}",
            )

    # --- the prompt line -------------------------------------------------------------------
    R.enabled.value = True
    R.cost.value = 7
    args = _FakeArgs(S="[A] Accept")
    R.on_tooltips(None, args, None, None)
    check(
        "the reroll prompt is added to the screen's own line rather than replacing it",
        "[A] Accept" in str(args.S) and "Reroll" in str(args.S) and "7" in str(args.S),
        f"the prompt line became {args.S!r}",
    )
    args = _FakeArgs(S=str(args.S))
    R.on_tooltips(None, args, None, None)
    check(
        "the prompt is not added twice when the screen redraws",
        str(args.S).count("Reroll") == 1,
        f"after a second redraw the line is {args.S!r}",
    )

    R.enabled.value = False
    args = _FakeArgs(S="[A] Accept")
    R.on_tooltips(None, args, None, None)
    check(
        "switched off, no reroll prompt appears",
        str(args.S) == "[A] Accept",
        f"the line became {args.S!r} with the feature off",
    )

    # --- the key match ---------------------------------------------------------------------
    R.enabled.value = True
    R._last_reroll_at = -99.0
    tries = []
    real_try = R._try_reroll
    R._try_reroll = lambda source: (tries.append(source), False)[1]
    try:
        R._key_from_screen(_FakeArgs(uevent=0, ukey=str(R._reroll_key.key or "R")))
        R._key_from_screen(_FakeArgs(uevent=1, ukey=str(R._reroll_key.key or "R")))
        R._key_from_screen(_FakeArgs(uevent=0, ukey="F13"))
    finally:
        R._try_reroll = real_try
    check(
        "the reward screen's key handler rerolls on the bound key going down, and nothing else",
        tries == ["reward screen"],
        f"it fired for {tries} - expected exactly one, from the key press. The release (uevent 1) "
        f"and an unrelated key must both be ignored, or one press costs two rerolls",
    )

finally:
    R.enabled.value = enabled_before
    R.cost.value = cost_before
    R._pending_mission, R._pending_data = pending_before
    R._last_reroll_at = last_at_before

    put_back = 0
    if p is not None and eridium_before >= 0:
        now = eridium()
        if now != eridium_before:
            p.PlayerReplicationInfo.AddCurrencyOnHand(ERIDIUM, eridium_before - now)
            put_back = eridium_before - now
    print(
        f"cleanup: eridium {eridium_before} -> {eridium()} (adjusted by {put_back}); "
        f"switch back to {R.enabled.value!r}, cost back to {R.cost.value}, key still {key_before!r}"
    )

summary()
