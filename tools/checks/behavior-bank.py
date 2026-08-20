# Unlimited bank (bank.py) - behavior checks
# Run: bash bl2-mcp/tools/ask.sh bl2-mcp/tools/checks/behavior-bank.py
#
# THE SWAP/GETINTERNAL MECHANISM IS NEVER DRIVEN AGAINST THE REAL BANK HERE. The module
# docstring's own risk paragraph is the reason: nobody has confirmed what an over-stuffed slot
# does to a save, so this file does not try to find out on a real character's bank. Instead it
# drives the two hooks directly with a fake storage stand-in - the same idiom
# one-key-refill.py uses for vending machines it must not actually charge - which proves the
# flag-set/flag-consume logic works without ever touching real inventory.
#
# The shop-hide half (Crazy Earl's listing) is a shop-side DEFINITION, not save data, and is
# written and restored live, the same as revive.py's and economy.py's own checks do for their
# definitions.
#
# NOTHING HERE PATCHES THE REAL unrealsdk MODULE. The one stub this file needs - a lookup that
# refuses - is installed as bank.py's OWN `unrealsdk` name (B.unrealsdk) and nowhere else, so a
# check that dies partway through cannot leave a booby-trapped find_object behind for the rest
# of the pack, or for whatever check runs next in the same session.
reset()

import unrealsdk
from bl2_modern import core
from bl2_modern.features import bank as B

was_enabled = B.enabled.value
real_sdk = B.unrealsdk
snap_remembered = B._remembered
snap_vanilla_balance_def = B._vanilla_balance_def

sdu_obj = None
sdu_before = "not read"


class _FakeStorage:
    """Stands in for a WillowInventoryStorage. No real bank or equip slot is touched."""

    def __init__(self, max_size, angry: bool = False):
        self._max_size = max_size
        self._angry = angry

    def GetMaxSize(self):
        if self._angry:
            raise RuntimeError("simulated: this storage cannot report its size")
        return self._max_size


try:
    # --- is the feature wired in at all -----------------------------------------------------
    feature = next((f for f in core.all_features() if f.name == "Unlimited bank"), None)
    check(
        "the Unlimited bank feature loaded into the pack without failing",
        feature is not None and feature.failed is None,
        "not registered" if feature is None else (feature.failed or "registered, no failure"),
    )
    check(
        "it ships switched off, because it changes real economy and a real storage limit",
        B.enabled.default_value is False,
        f"default is {B.enabled.default_value!r}",
    )
    check(
        "the core will re-apply the shop-hide half at the main menu",
        feature is not None and feature.writes_game_data and feature.apply is B._apply_shop_hide,
        f"writes_game_data={getattr(feature, 'writes_game_data', None)}, "
        f"apply={getattr(feature, 'apply', None)}",
    )
    check(
        "both hooks are carried to the core, so the swap trick and the shop-hide both load",
        feature is not None
        and any(h is B.on_swap for h in feature.hooks)
        and any(h is B.on_get_internal for h in feature.hooks),
        getattr(feature, "hooks", None),
    )
    check(
        "flipping the switch applies it straight away",
        B.enabled.on_change_anytime is B._on_change,
        B.enabled.on_change_anytime,
    )

    # --- the shop-hide half: a real shop-side definition, written and restored live ----------
    try:
        sdu_obj = unrealsdk.find_object("BlackMarketUpgradeDefinition", B.BANK_SDU)
        sdu_before = sdu_obj.BalanceDefinition
    except Exception as ex:
        sdu_obj = None
        print(f"[SKIP] {B.BANK_SDU} is not loaded here ({ex!r}) - the shop-hide checks need it "
              f"loaded, which should be true anywhere Crazy Earl's shop data is loaded")

    if sdu_obj is not None:
        check(
            "the bank SDU's BalanceDefinition reads as something before this file touches it",
            True,  # any value, including None, is a legitimate reading - this just proves it reads
            f"BalanceDefinition = {sdu_before!r}",
        )

        B.enabled.value = True
        B._apply_shop_hide()
        check(
            "turning the switch on nulls the bank SDU's BalanceDefinition, so Earl stops "
            "offering it",
            sdu_obj.BalanceDefinition is None,
            f"BalanceDefinition = {sdu_obj.BalanceDefinition!r}",
        )

        B.enabled.value = False
        B._apply_shop_hide()
        # The value "off" is supposed to put back is the one the PACK remembered on its own first
        # touch, which is not always what this file read a moment ago: if the switch was already
        # ON when this file started, the pack had already nulled the field, so sdu_before reads
        # None and comparing to it would fail a restore that is actually correct. So the
        # expectation is the remembered arrival value, plus - only when the switch started off -
        # the stronger claim that the remembered value is exactly what this file saw itself.
        expected_off = B._vanilla_balance_def
        check(
            "turning the switch back off restores whatever the pack actually found there, not "
            "a guess",
            sdu_obj.BalanceDefinition is expected_off
            and (was_enabled or expected_off is sdu_before),
            f"BalanceDefinition = {sdu_obj.BalanceDefinition!r}, the pack remembered "
            f"{expected_off!r}, this file read {sdu_before!r} on arrival "
            f"(switch started {'on' if was_enabled else 'off'})",
        )

    # --- the swap trick, driven with a fake storage - never the real bank -------------------
    B.enabled.value = False
    B._pending_swap = False
    B.on_swap(_FakeStorage(6), None, None, None)
    check(
        "with the switch off, Swap on a big storage does not even set the one-shot flag",
        B._pending_swap is False,
        f"_pending_swap = {B._pending_swap!r}",
    )

    B.enabled.value = True
    B._pending_swap = False
    B.on_swap(_FakeStorage(4), None, None, None)
    check(
        "with the switch on, Swap on a storage no bigger than 4 (the equip slots' own size) "
        "does not set the flag - only something bigger than that counts as the bank",
        B._pending_swap is False,
        f"_pending_swap = {B._pending_swap!r}",
    )

    B.on_swap(_FakeStorage(6), None, None, None)
    check(
        "with the switch on, Swap on a storage bigger than 4 sets the flag",
        B._pending_swap is True,
        f"_pending_swap = {B._pending_swap!r}",
    )
    result = B.on_get_internal(_FakeStorage(6), None, None, None)
    check(
        "the very next GetInternal is blocked, which is the whole trick - it is the step that "
        "would otherwise hand back whatever was already in the slot",
        result is B.Block,
        f"on_get_internal returned {result!r}",
    )
    check(
        "and the one-shot flag is consumed by that one block, not left set",
        B._pending_swap is False,
        f"_pending_swap = {B._pending_swap!r}",
    )

    result2 = B.on_get_internal(_FakeStorage(6), None, None, None)
    check(
        "a SECOND GetInternal, with no Swap in between, is not blocked - the trick is one-shot, "
        "not 'block forever'",
        result2 is None,
        f"on_get_internal returned {result2!r} on the second call",
    )

    # The deliberate correction over BL2Fix's own code: the flag is consumed even if the switch
    # went off in between, so it can never linger to affect an unrelated later call.
    B.enabled.value = True
    B.on_swap(_FakeStorage(6), None, None, None)
    B.enabled.value = False
    result3 = B.on_get_internal(_FakeStorage(6), None, None, None)
    check(
        "if the switch goes off between Swap and GetInternal, GetInternal is not blocked",
        result3 is None,
        f"on_get_internal returned {result3!r}",
    )
    check(
        "and the flag is still cleared, rather than left set for whatever GetInternal comes next "
        "- the correction this port makes over BL2Fix's own code, see the module docstring",
        B._pending_swap is False,
        f"_pending_swap = {B._pending_swap!r}",
    )

    # A storage that cannot even report its own size must not crash the hook, and must not be
    # mistaken for the bank.
    B.enabled.value = True
    B._pending_swap = False
    escaped = None
    try:
        B.on_swap(_FakeStorage(0, angry=True), None, None, None)
    except Exception as ex:
        escaped = ex
    check(
        "a storage that cannot report GetMaxSize() does not crash the Swap hook",
        escaped is None and B._pending_swap is False,
        f"raised {escaped!r}, _pending_swap = {B._pending_swap!r}",
    )

    # --- nothing here may ever raise into the game -------------------------------------------
    # The stub goes on bank.py's own `unrealsdk` name, not on the real module - see the header.
    class _AngrySDK:
        def find_object(self, cls, path):
            raise RuntimeError(f"simulated: {cls} lookup refused")

    B.unrealsdk = _AngrySDK()
    escaped = None
    try:
        B._apply_shop_hide()
    except Exception as ex:
        escaped = ex
    B.unrealsdk = real_sdk
    check(
        "the real unrealsdk module was never patched - only bank.py's own name for it",
        unrealsdk.find_object is not None and B.unrealsdk is unrealsdk,
        f"B.unrealsdk is {B.unrealsdk!r}",
    )
    check(
        "a lookup that refuses cannot throw out of the shop-hide apply and into the game",
        escaped is None,
        f"{escaped!r}",
    )

finally:
    B.unrealsdk = real_sdk
    if sdu_obj is not None and sdu_before != "not read":
        try:
            sdu_obj.BalanceDefinition = sdu_before
        except Exception as ex:
            print(f"could not restore the bank SDU's BalanceDefinition: {ex!r}")
    B.enabled.value = was_enabled
    B._pending_swap = False
    B._remembered = snap_remembered
    B._vanilla_balance_def = snap_vanilla_balance_def

    check(
        "the switch, the one-shot flag, the remembered vanilla value and bank.py's own unrealsdk "
        "name are all back where this file found them",
        B.enabled.value == was_enabled
        and B._pending_swap is False
        and B._remembered == snap_remembered
        and B.unrealsdk is real_sdk,
        f"enabled={B.enabled.value}, _pending_swap={B._pending_swap}, "
        f"_remembered={B._remembered}, unrealsdk={B.unrealsdk!r}",
    )

summary()
