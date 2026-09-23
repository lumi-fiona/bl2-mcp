# Reading a per-character option - what it can write back onto the character (ticket 23)
# Run: bash bl2-mcp/tools/ask.sh bl2-mcp/tools/checks/behavior-option-reads.py   (after harness.py)
#
# Every read of a save_options option runs can_save() -> pc.GetCachedSaveGame(), which runs the
# native ExtractExpansionSavedataFromUnloadableItemData (RVA 0xD78260) on a copy of the cached save.
# It handles five tags. Tags 1, 2, 4 and 5 (eridium above 99, playthroughs above 1, OP levels
# unlocked, OP level chosen) land on the copy. Tag 3 writes the controller:
# PlayerHasPlayedInPlaythroughThree, and only while it reads 0. So a read can raise that flag to
# the save's value and can touch nothing else. These claims are the no-loss properties, not the
# mechanism: a read path that stops calling GetCachedSaveGame still passes.
#
# Each claim changes one live value, does one real option read, looks, and puts the value back,
# all inside this one request, so no save can happen in between. Needs a character in the world.
# Run it on a throwaway anyway: the changes are undone, but they are made on whoever is loaded.
reset()

import unrealsdk
from bl2_modern.features import difficulty as D

p = pc()
pri = p.PlayerReplicationInfo
ERIDIUM = unrealsdk.find_enum("ECurrencyType").CURRENCY_Eridium


def read():
    """One real per-character option read, the pack's own path."""
    return D.mode_chosen.value


def saved_flag():
    """Tag 3 in the save manager's own cached copy: the flag as the file last had it."""
    mgr = p.GetWillowGlobals().GetWillowSaveGameManager()
    save = mgr.GetCachedPlayerSaveGame(p.GetMyControllerId())
    tags = [(-e.Quantity) >> 8 for e in save.UnloadableDlcItemData if e.Quantity < 0 and (-e.Quantity) & 0xFF == 3]
    return tags[0] if tags else None


found = dict(
    eridium=pri.GetCurrencyOnHand(ERIDIUM),
    completed=pri.HighestCompletedPlayThrough,
    op=pri.NumOverpowerLevelsUnlocked,
    choice=p.OverpowerChoiceValue,
    pending=p.OverpowerChoiceValuePendingSave,
    flag=p.PlayerHasPlayedInPlaythroughThree,
    pt=p.GetCurrentPlaythrough(),
)

try:
    check("a character is in the world", p.Pawn is not None)

    first, second = p.GetCachedSaveGame(), p.GetCachedSaveGame()
    check(
        "each GetCachedSaveGame hands back a new copy, so what Extract writes onto it goes nowhere",
        first._get_address() != second._get_address(),
        f"{first.Name} / {second.Name}",
    )

    # ponytail: +150 assumes the character is 150 or more below the eridium cap; within 150 of it
    # the game clamps the add and this claim goes red for the wrong reason.
    pri.AddCurrencyOnHand(ERIDIUM, 150)
    read()
    got = pri.GetCurrencyOnHand(ERIDIUM)
    check("eridium earned since the last save survives a read (tag 1)", got == found["eridium"] + 150, got)
    pri.AddCurrencyOnHand(ERIDIUM, -150)

    pri.HighestCompletedPlayThrough = found["completed"] + 1
    read()
    got = pri.HighestCompletedPlayThrough
    check("a playthrough completed since the last save survives a read (tag 2)", got == found["completed"] + 1, got)
    pri.HighestCompletedPlayThrough = found["completed"]

    pri.NumOverpowerLevelsUnlocked = found["op"] + 1
    read()
    got = pri.NumOverpowerLevelsUnlocked
    check("an OP level unlocked since the last save survives a read (tag 4)", got == found["op"] + 1, got)
    pri.NumOverpowerLevelsUnlocked = found["op"]

    p.OverpowerChoiceValue = found["choice"] + 1
    p.OverpowerChoiceValuePendingSave = True
    read()
    got = (p.OverpowerChoiceValue, p.OverpowerChoiceValuePendingSave)
    check("a newly chosen OP level survives a read (tag 5)", got == (found["choice"] + 1, True), got)
    p.OverpowerChoiceValue = found["choice"]
    p.OverpowerChoiceValuePendingSave = found["pending"]

    p.PlayerHasPlayedInPlaythroughThree = 1
    read()
    got = p.PlayerHasPlayedInPlaythroughThree
    check("the UVHM welcome flag, once set, is never lowered by a read (tag 3)", got == 1, got)

    p.PlayerHasPlayedInPlaythroughThree = 0
    read()
    got, file_value = p.PlayerHasPlayedInPlaythroughThree, saved_flag()
    check(
        "a read moves a lowered welcome flag, if at all, only up to the save's own value (tag 3)",
        got in (0, file_value or 0),
        f"flag {got}, save {file_value}, {'raised by the read' if got else 'left at 0'}",
    )

    check("the playthrough is untouched by all of this", p.GetCurrentPlaythrough() == found["pt"], p.GetCurrentPlaythrough())
finally:
    pri.AddCurrencyOnHand(ERIDIUM, found["eridium"] - pri.GetCurrencyOnHand(ERIDIUM))
    pri.HighestCompletedPlayThrough = found["completed"]
    pri.NumOverpowerLevelsUnlocked = found["op"]
    p.OverpowerChoiceValue = found["choice"]
    p.OverpowerChoiceValuePendingSave = found["pending"]
    p.PlayerHasPlayedInPlaythroughThree = found["flag"]
    left = dict(
        eridium=pri.GetCurrencyOnHand(ERIDIUM),
        completed=pri.HighestCompletedPlayThrough,
        op=pri.NumOverpowerLevelsUnlocked,
        choice=p.OverpowerChoiceValue,
        pending=p.OverpowerChoiceValuePendingSave,
        flag=p.PlayerHasPlayedInPlaythroughThree,
        pt=p.GetCurrentPlaythrough(),
    )
    check("every value is left as found", left == found, {k: (found[k], left[k]) for k in found if found[k] != left[k]})

summary()
