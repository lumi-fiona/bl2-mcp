# Reward reroll - the parts that need a real mission turn-in screen, which cannot be reached from
# inside one frame. THE SEQUENCE, run by a person, one request per step:
#
#   1. bash bl2-mcp/tools/ask.sh bl2-mcp/tools/harness.py
#   2. Turn the feature on in the mod menu and note how much eridium you have.
#   3. Walk up to an NPC with a mission ready to hand in and open the turn-in screen, so the two
#      reward choices are on the screen in front of you.
#   4. WITHOUT closing that screen, run this file.
#   5. Look at the screen. The two items should have changed. Then run it again to see it charge
#      a second time.
#   6. Accept one of the rewards by hand and check the item you were handed is the one you saw.
#
# Step 6 is the one that cannot be automated and is also the one that matters most: it is the only
# way to find out whether the game grants from the pair the screen was showing, or from a copy it
# kept somewhere else. The feature substitutes at grant time precisely because that is unknown.
#
# Nothing here turns a mission in. It rerolls what is already on the screen and stops.
reset()

import unrealsdk
from bl2_modern.features import rewardreroll as R

p = pc()
ERIDIUM = unrealsdk.find_enum("ECurrencyType").CURRENCY_Eridium
enabled_before = R.enabled.value


def eridium():
    return int(p.PlayerReplicationInfo.GetCurrencyOnHand(ERIDIUM))


def names(data):
    """What the two weapon choices are, as far as they can be read out of the pair struct."""
    out = []
    for slot in ("WeaponRewards", "ItemRewards"):
        try:
            for entry in list(getattr(data, slot)):
                try:
                    out.append(str(entry.BalanceDefinition))
                except Exception:
                    out.append("?")
        except Exception:
            out.append("unreadable")
    return out


try:
    R.enabled.value = True

    movie, reward = R._reward_screen(p)
    check(
        "a mission reward screen is open right now",
        reward is not None,
        f"movie={movie}, reward object={reward}. If this fails, go back to step 3 - everything "
        f"below it is meaningless without a reward screen up",
    )

    showing = R._showing_pair(reward) if reward is not None else None
    check(
        "the open screen is showing a pair of reward choices",
        showing is not None,
        f"RewardData reads as {showing!r}",
    )

    if showing is not None:
        before_names = names(showing)
        before_eridium = eridium()
        cost_now = int(R.cost.value)

        check(
            "there is enough eridium to pay for a reroll",
            before_eridium >= cost_now,
            f"{before_eridium} eridium, a reroll costs {cost_now}",
        )

        did = R._try_reroll("needs-travel check")
        check(
            "the reroll went through",
            did is True,
            f"_try_reroll returned {did!r}; the log line above says which step refused",
        )

        after = R._showing_pair(reward)
        after_names = names(after) if after is not None else []
        check(
            "the pair the screen is holding actually changed",
            did and after_names != before_names,
            f"before {before_names}\n          after  {after_names}. Identical lists can also mean "
            f"the roll genuinely came up the same - roll again before believing a failure here",
        )
        check(
            "the reroll cost exactly what the setting says",
            eridium() == before_eridium - cost_now,
            f"{before_eridium} -> {eridium()}, expected -{cost_now}",
        )
        check(
            "the rerolled pair is armed for the grant",
            R._pending_data is not None,
            f"_pending_data is {R._pending_data!r}; without it the game grants its own pair",
        )
        print(
            "\nNOW LOOK AT THE SCREEN. The two offered items should be different from what they "
            "were. Accept one by hand and confirm the item you receive is the one you were "
            "looking at - that is the one claim no script here can make."
        )

finally:
    R.enabled.value = enabled_before
    print(f"cleanup: switch back to {R.enabled.value!r}. Eridium was NOT refunded - a reroll that "
          f"worked is meant to cost.")

summary()
