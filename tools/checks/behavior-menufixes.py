# Menu fixes - behavior checks for features/menufixes.py
# Run: bash bl2-mcp/tools/ask.sh bl2-mcp/tools/checks/behavior-menufixes.py
#
# THE REAL PAUSE HOOK IS CALLED FOR REAL, SAFELY - calling on_try_pause.__wrapped__(...)
# directly only runs this file's own Python body (which is nothing but `return None or Block`).
# It does NOT go through the engine's actual hook dispatch, so it never actually triggers the
# real vanilla TryFakePauseInSinglePlayer - nothing here can freeze the game or the bridge.
#
# THE REAL AIRBORNE-MENU BRANCH IS NOT CALLED FOR REAL. When the switch is on, that hook body
# makes real calls that would actually pop the status menu open on screen, with no clean way for
# an unattended script to close it again. That branch is exercised against a fake controller
# that records what was called instead - the off branch (which is exactly today's vanilla
# behavior, refuse-if-airborne) is still run for real.
reset()

import unrealsdk

from bl2_modern import core
from bl2_modern.features import menufixes as MF
from unrealsdk.hooks import Block
from unrealsdk.unreal import WrappedStruct


def params_for(class_name, function_name):
    """A real, empty argument struct for one of the game's own functions."""
    return WrappedStruct(unrealsdk.find_class(class_name)._find(function_name))


class FakeViewportUI:
    def __init__(self):
        self.ran_for = None

    def RunStatusMenu(self, controller):
        self.ran_for = controller


class FakeViewportClient:
    def __init__(self):
        self.ViewportUI = FakeViewportUI()


class FakeTradeManager:
    def __init__(self):
        self.cancelled = False

    def CancelTrade(self):
        self.cancelled = True


class FakeAirborneController:
    """Records what the airborne branch calls, without ever touching the real UI."""

    def __init__(self, can_show=True, has_viewport=True, has_trade=True):
        self.calls = []
        self._viewport = FakeViewportClient() if has_viewport else None
        self._can_show = can_show
        self.TradeManager = FakeTradeManager() if has_trade else None
        self.status_menu_open = None

    def GetPlayerViewportClient(self):
        self.calls.append("GetPlayerViewportClient")
        return self._viewport

    def CanShowModalMenu(self):
        self.calls.append("CanShowModalMenu")
        return self._can_show

    def ForceUnzoom(self):
        self.calls.append("ForceUnzoom")

    def SetStatusMenuOpen(self, value):
        self.calls.append(f"SetStatusMenuOpen({value})")
        self.status_menu_open = value

    def ClearContextualPromptScreen(self):
        self.calls.append("ClearContextualPromptScreen")


class AngryController(FakeAirborneController):
    """A controller whose viewport lookup blows up partway through."""

    def GetPlayerViewportClient(self):
        self.calls.append("GetPlayerViewportClient")
        raise RuntimeError("pretend the viewport is gone")


p = pc()
was = {"pause": MF.menu_pause.value, "air": MF.menu_in_air.value}

try:
    # --- how the feature is wired into the core --------------------------------------------

    feature = next((f for f in core.all_features() if f.name == "Menu fixes"), None)
    check(
        "the menu fixes feature loaded",
        feature is not None and feature.failed is None,
        feature.failed if feature else "no feature by that name",
    )
    if feature is not None:
        # Membership by identity, not by set: hook objects are unhashable (measured
        # 2026-08-20, "cannot use 'mods_base.hook.HookType' as a set element" killed this
        # whole file on its first live run).
        check(
            "both hooks are carried to the core",
            all(any(h is want for h in feature.hooks) for want in (MF.on_try_pause, MF.on_show_status_menu)),
            f"feature.hooks has {len(feature.hooks)} entries",
        )
        check(
            "both switches are carried to the menu",
            all(any(o is want for o in feature.options) for want in (MF.menu_pause, MF.menu_in_air)),
            f"feature.options has {len(feature.options)} entries",
        )

    # --- menu pause in single player, called for real (see the file header for why this is
    # safe): the whole hook body is `return None or Block`, nothing else --------------------

    hud = next(
        (h for h in unrealsdk.find_all("WillowHUD") if not h.Name.startswith("Default__")),
        None,
    )
    if hud is None:
        print(
            "[SKIP] a live WillowHUD to call the real pause hook against   "
            "none found - load a character and run this again",
        )
    else:
        pause_args = params_for("WillowHUD", "TryFakePauseInSinglePlayer")

        MF.menu_pause.value = True
        result_on = MF.on_try_pause.__wrapped__(hud, pause_args, None, None)
        check(
            "with the switch on, the pause hook lets the vanilla function run",
            result_on is None,
            f"returned {result_on!r}",
        )

        MF.menu_pause.value = False
        result_off = MF.on_try_pause.__wrapped__(hud, pause_args, None, None)
        check(
            "with the switch off, the pause hook blocks the vanilla function",
            result_off is Block,
            f"returned {result_off!r}",
        )

    # --- menu usable while airborne: the OFF branch is real, the ON branch is faked ---------

    status_args = params_for("WillowPlayerController", "ShowStatusMenu")

    MF.menu_in_air.value = False
    real_off_result = MF.on_show_status_menu.__wrapped__(p, status_args, None, None)
    check(
        "with the switch off, the airborne hook lets the vanilla function run (and it refuses "
        "on its own if you are actually airborne)",
        real_off_result is None,
        f"returned {real_off_result!r}",
    )

    MF.menu_in_air.value = True
    fake = FakeAirborneController()
    fake_result = MF.on_show_status_menu.__wrapped__(fake, status_args, None, None)
    check(
        "with the switch on, the hook always blocks the vanilla function",
        fake_result is Block,
        f"returned {fake_result!r}",
    )
    check(
        "and it opens the menu itself, in the order the legacy mechanism does",
        fake.calls == [
            "GetPlayerViewportClient",
            "CanShowModalMenu",
            "ForceUnzoom",
            "SetStatusMenuOpen(True)",
            "ClearContextualPromptScreen",
        ],
        f"calls were {fake.calls}",
    )
    check(
        "and it cancels a trade in progress along the way",
        fake.TradeManager.cancelled,
        f"TradeManager.cancelled = {fake.TradeManager.cancelled}",
    )
    check(
        "and the viewport was actually handed the menu",
        fake._viewport.ViewportUI.ran_for is fake,
        f"ran_for = {fake._viewport.ViewportUI.ran_for!r}",
    )

    # CanShowModalMenu() saying no must still block the vanilla function (matching the legacy
    # mechanism, which always returns False once the switch is on) - but must do none of the
    # rest of the work.
    refused = FakeAirborneController(can_show=False)
    refused_result = MF.on_show_status_menu.__wrapped__(refused, status_args, None, None)
    check(
        "when the game says no other menu can show right now, the hook still blocks the "
        "vanilla function rather than letting it refuse a second time",
        refused_result is Block,
        f"returned {refused_result!r}",
    )
    check(
        "but does none of the actual menu-opening work in that case",
        refused.calls == ["GetPlayerViewportClient", "CanShowModalMenu"],
        f"calls were {refused.calls}",
    )

    # No trade manager at all must not raise.
    no_trade = FakeAirborneController(has_trade=False)
    no_trade_result = MF.on_show_status_menu.__wrapped__(no_trade, status_args, None, None)
    check(
        "having no trade manager at all does not stop the menu opening",
        no_trade_result is Block and no_trade.status_menu_open is True,
        f"returned {no_trade_result!r}, status_menu_open={no_trade.status_menu_open!r}",
    )

    # No viewport at all: CanShowModalMenu() must never even be asked, matching the legacy
    # `if viewportClient and caller.CanShowModalMenu():` short-circuit order.
    no_viewport = FakeAirborneController(has_viewport=False)
    no_viewport_result = MF.on_show_status_menu.__wrapped__(no_viewport, status_args, None, None)
    check(
        "with no viewport at all, the menu-opening work is skipped without being asked whether "
        "a modal menu can show",
        no_viewport_result is Block and no_viewport.calls == ["GetPlayerViewportClient"],
        f"returned {no_viewport_result!r}, calls were {no_viewport.calls}",
    )

    # A viewport lookup that raises must be swallowed, not crash the pack.
    angry = AngryController()
    angry_result = MF.on_show_status_menu.__wrapped__(angry, status_args, None, None)
    check(
        "a viewport lookup that raises is contained, so one bad frame cannot take the pack down",
        angry_result is Block,
        f"returned {angry_result!r}",
    )

finally:
    MF.menu_pause.value = was["pause"]
    MF.menu_in_air.value = was["air"]
    check(
        "both switches are back where they started",
        MF.menu_pause.value == was["pause"] and MF.menu_in_air.value == was["air"],
        f"pause={MF.menu_pause.value!r}, air={MF.menu_in_air.value!r}",
    )

summary()
