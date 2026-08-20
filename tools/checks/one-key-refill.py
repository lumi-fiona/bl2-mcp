# One key refills everything - checks for features/vendorrefill.py
# Run: bash bl2-mcp/tools/ask.sh bl2-mcp/tools/checks/one-key-refill.py
#
# NOTHING HERE BUYS ANYTHING REAL. The one end-to-end run is driven through a stand-in for Alt Use
# Vendors' shop maths and a stand-in purse, so no ammo pool, no health and no real money moves.
# The single exception is one deliberate round trip of $1 through the real wallet, to prove the
# payment call works at all, and it is handed straight back.
reset()

import unrealsdk
from bl2_modern.features import vendorrefill as V

p = pc()

# --- everything we are about to change, so the finally can put it back --------------------

real_machines = V._machines
real_shop_info = V._shop_info
real_charge = V._charge
real_wallet = V._wallet
real_is_client = V._is_client
real_say = V._say

was = {
    "enabled": V.enabled.value,
    "junk": V.do_junk.value,
    "health": V.do_health.value,
    "ammo": V.do_ammo.value,
    "reach": V.reach.value,
    "price": V.price.value,
    "far": V.far_prices.value,
}

# --- stand-ins ---------------------------------------------------------------------------


class _Machine(object):
    def __init__(self, name, shop_type):
        self.Name = name
        self.ShopType = shop_type


class _Info(object):
    """The same shape as alt_use_vendors.shop_info.ShopInfo, minus the icon fields."""

    def __init__(self, cost, manual, done):
        self._cost = cost
        self.requires_manual_payment = manual
        self._done = done

    def cost_function(self, controller, vendor):
        return self._cost

    def purchase_function(self, controller, vendor):
        self._done.append(vendor.Name)


class _Shop(object):
    def __init__(self, shop_map):
        self.SHOP_INFO_MAP = shop_map


try:
    shop_types = unrealsdk.find_enum("EShopType")
    currency = unrealsdk.find_enum("ECurrencyType")
    enums_ok = True
except Exception as ex:
    shop_types = currency = None
    enums_ok = False
    print("could not read the game's enums: %r" % (ex,))

try:
    # --- what the feature rests on ------------------------------------------------------
    check(
        "the game gives us the shop and money lists the feature asks for by name",
        enums_ok,
        "EShopType and ECurrencyType",
    )

    import sys

    shop_info = sys.modules.get("alt_use_vendors.shop_info")
    check(
        "Alt Use Vendors' shop maths is already loaded, so nothing has to import it",
        shop_info is not None,
        "sys.modules has %d alt_use_vendors entries; the feature refuses to import it itself "
        "because that would run build_mod() a second time"
        % len([k for k in sys.modules if k.startswith("alt_use_vendors")]),
    )
    check(
        "the feature finds that shop maths through its own lookup",
        V._shop_info() is not None,
        "V._shop_info() returned %r" % (V._shop_info(),),
    )

    if shop_info is not None and enums_ok:
        have = {}
        for shop_type in ("SType_Weapons", "SType_Items", "SType_Health"):
            key = getattr(shop_types, shop_type)
            have[shop_type] = shop_info.SHOP_INFO_MAP.get(key)
        check(
            "all three machine kinds still have a price and a purchase in Alt Use Vendors",
            all(
                info is not None
                and callable(info.cost_function)
                and callable(info.purchase_function)
                for info in have.values()
            ),
            "%s" % ({k: (v is not None) for k, v in have.items()},),
        )
        check(
            "the gun machine is still the one that pays you rather than charges you",
            have["SType_Weapons"] is not None
            and have["SType_Weapons"].requires_manual_payment is False,
            "requires_manual_payment for the gun machine is %r - the feature relies on this to "
            "know not to hand over money for a sale"
            % (
                have["SType_Weapons"].requires_manual_payment
                if have["SType_Weapons"] is not None
                else "missing",
            ),
        )

    # --- the price dial -----------------------------------------------------------------
    V.price.value = 100
    at_full = V._scaled(1000)
    V.price.value = 50
    at_half = V._scaled(1000)
    V.price.value = 0
    at_free = V._scaled(1000)
    V.price.value = 1
    at_tiny = V._scaled(3)
    check(
        "the price dial at 100 charges exactly what the machine would",
        at_full == 1000,
        "1000 became %r" % (at_full,),
    )
    check(
        "the price dial at 50 halves the bill",
        at_half == 500,
        "1000 became %r" % (at_half,),
    )
    check(
        "the price dial at 0 really is free, rather than a pound short of free",
        at_free == 0,
        "1000 became %r" % (at_free,),
    )
    check(
        "a tiny percentage of a tiny price still costs something, rather than rounding to free",
        at_tiny == 1,
        "1 percent of 3 became %r" % (at_tiny,),
    )
    V.price.value = 100

    # --- which machine gets used --------------------------------------------------------
    if enums_ok:
        near = _Machine("near ammo", shop_types.SType_Items)
        far = _Machine("far health", shop_types.SType_Health)
        pretend = [(100.0, near), (4000.0, far)]

        V.far_prices.value = False
        check(
            "a machine within reach is used",
            V._pick(pretend, shop_types.SType_Items, 1200.0) is near,
            "picked %r" % (V._pick(pretend, shop_types.SType_Items, 1200.0),),
        )
        check(
            "a machine on the other side of the level is left alone",
            V._pick(pretend, shop_types.SType_Health, 1200.0) is None,
            "picked %r at 4000 units with a reach of 1200"
            % (V._pick(pretend, shop_types.SType_Health, 1200.0),),
        )
        V.far_prices.value = True
        check(
            "turning on borrowed prices reaches the far machine, which is the whole point of it",
            V._pick(pretend, shop_types.SType_Health, 1200.0) is far,
            "picked %r" % (V._pick(pretend, shop_types.SType_Health, 1200.0),),
        )
        V.far_prices.value = False
        check(
            "asking for a kind of machine that is not here gives nothing rather than the wrong one",
            V._pick(pretend, shop_types.SType_Weapons, 99999.0) is None,
            "picked %r" % (V._pick(pretend, shop_types.SType_Weapons, 99999.0),),
        )

    # --- are there real machines to find at all? -----------------------------------------
    # This map may honestly have none - Sanctuary is the one place all three kinds stand
    # together, and nowhere else is guaranteed to. That is an empty map, not a broken feature,
    # so it is reported as a skip rather than a fail - see one-key-refill-needs-travel.py, which
    # travels there and does the real thing.
    real_found = V._machines(p) if p is not None else []
    if not real_found:
        reason = "no player controller" if p is None else "found 0 in %s" % (where(p),)
        print(
            "[SKIP] there are vending machines in this level for the real finder to see   "
            "%s - travel to Sanctuary and run one-key-refill-needs-travel.py, which does the "
            "real thing there" % (reason,)
        )
    else:
        check(
            "there are vending machines in this level for the real finder to see",
            len(real_found) > 0,
            "found %d" % (len(real_found),),
        )
        if len(real_found) > 1:
            gaps = [round(pair[0]) for pair in real_found]
            check(
                "the machines come back nearest first",
                gaps == sorted(gaps),
                "distances %s" % (gaps[:8],),
            )

    # --- the real wallet, one pound, there and back ---------------------------------------
    if p is not None and enums_ok:
        before_money = money(p)
        took = V._charge(p, currency, 1)
        during = money(p)
        gave_back = V._charge(p, currency, -1)
        after_money = money(p)
        check(
            "taking payment really moves money, so a refill can actually be paid for",
            took and during == before_money - 1,
            "$%s -> $%s after being charged $1" % (before_money, during),
        )
        check(
            "and the money this check borrowed is back where it started",
            gave_back and after_money == before_money,
            "$%s -> $%s" % (before_money, after_money),
        )

    # --- one whole press, with nothing real attached --------------------------------------
    if enums_ok:
        said = []
        purse = {"credits": 10_000}

        V._say = lambda did, could_not, spent, earned: said.append(
            (list(did), list(could_not), spent, earned)
        )
        V._wallet = lambda controller, cur: purse["credits"]

        def _fake_charge(controller, cur, amount):
            purse["credits"] -= int(amount)
            return True

        V._charge = _fake_charge
        V._is_client = lambda: False

        junk_machine = _Machine("guns", shop_types.SType_Weapons)
        health_machine = _Machine("health", shop_types.SType_Health)
        ammo_machine = _Machine("ammo", shop_types.SType_Items)
        V._machines = lambda controller: [
            (10.0, junk_machine),
            (20.0, health_machine),
            (30.0, ammo_machine),
        ]

        def _load(junk_value, heal_cost, ammo_cost):
            done = []
            V._shop_info = lambda: _Shop(
                {
                    shop_types.SType_Weapons: _Info(-junk_value, False, done),
                    shop_types.SType_Health: _Info(heal_cost, True, done),
                    shop_types.SType_Items: _Info(ammo_cost, True, done),
                }
            )
            return done

        # Everything affordable.
        said[:] = []
        purse["credits"] = 10_000
        order = _load(500, 300, 700)
        V.enabled.value = True
        V.do_junk.value = V.do_health.value = V.do_ammo.value = True
        V._refill()
        check(
            "one press does all three jobs at three machines standing together",
            order == ["guns", "health", "ammo"],
            "the machines used, in order, were %s" % (order,),
        )
        check(
            "the junk is sold first, so its money is there to pay for the rest",
            order[:1] == ["guns"],
            "order was %s" % (order,),
        )
        check(
            "only the two jobs that charge take money, and the sale is not charged for",
            purse["credits"] == 10_000 - 300 - 700,
            "$10,000 became $%s; a sale being charged for would show 500 less"
            % (purse["credits"],),
        )
        check(
            "what happened is reported back to the player",
            said and set(said[-1][0]) == {"junk", "health", "ammo"} and said[-1][2] == 1000,
            "reported %r" % (said[-1] if said else None,),
        )

        # Not enough money for both. Health is meant to win.
        said[:] = []
        purse["credits"] = 350
        order = _load(0, 300, 700)
        V._refill()
        check(
            "when you cannot afford everything, being healed wins over being rearmed",
            order == ["health"],
            "with $350, a $300 heal and a $700 refill, it did %s" % (order,),
        )
        check(
            "and the one it could not do is said out loud rather than silently skipped",
            said and said[-1][1] == ["ammo"],
            "reported %r" % (said[-1] if said else None,),
        )

        # The grammar of that message, which the first draft got wrong.
        spoken = []
        V._say = real_say
        real_show = V.show_hud_message
        V.show_hud_message = lambda title, text, seconds=4: spoken.append(text)
        try:
            V._say(["health"], ["ammo"], 300, 0)
            V._say([], ["health", "ammo"], 0, 0)
        finally:
            V.show_hud_message = real_show
        V._say = lambda did, could_not, spent, earned: said.append(
            (list(did), list(could_not), spent, earned)
        )
        check(
            "the message about what it could not afford is written in English",
            len(spoken) == 2
            and "afford to fill your ammo" in spoken[0]
            and "afford to heal you and fill your ammo" in spoken[1],
            "said %r" % (spoken,),
        )

        # Nothing needed.
        said[:] = []
        purse["credits"] = 10_000
        order = _load(0, 0, 0)
        V._refill()
        check(
            "a press with full health, full ammo and no junk buys nothing at all",
            order == [] and purse["credits"] == 10_000,
            "did %s, money %s" % (order, purse["credits"]),
        )

        # Switched off in the menu.
        said[:] = []
        order = _load(500, 300, 700)
        V.enabled.value = False
        V._refill()
        check(
            "turning the feature off in the menu really stops the key doing anything",
            order == [],
            "with the switch off it still did %s" % (order,),
        )
        V.enabled.value = True

        # One category switched off.
        said[:] = []
        order = _load(500, 300, 700)
        V.do_ammo.value = False
        V._refill()
        check(
            "turning off just the ammo half leaves the other two working",
            order == ["guns", "health"],
            "did %s" % (order,),
        )
        V.do_ammo.value = True

        # A guest.
        said[:] = []
        order = _load(500, 300, 700)
        V._is_client = lambda: True
        V._refill()
        check(
            "a guest's machine buys nothing, because ammo and money are the host's to change",
            order == [],
            "on a guest it did %s" % (order,),
        )
        V._is_client = lambda: False

        # A machine that refuses to be priced must not stop the others.
        said[:] = []
        done = []

        class _Angry(_Info):
            def cost_function(self, controller, vendor):
                raise RuntimeError("this machine has no shelf")

        V._shop_info = lambda: _Shop(
            {
                shop_types.SType_Weapons: _Angry(0, False, done),
                shop_types.SType_Health: _Info(300, True, done),
                shop_types.SType_Items: _Info(700, True, done),
            }
        )
        purse["credits"] = 10_000
        V._refill()
        check(
            "one machine throwing an error does not stop the other two being used",
            done == ["health", "ammo"],
            "did %s" % (done,),
        )

        # A purchase that fails after payment must hand the money back.
        said[:] = []
        refunded = []

        class _Broken(_Info):
            def purchase_function(self, controller, vendor):
                raise RuntimeError("the pump is empty")

        V._shop_info = lambda: _Shop(
            {shop_types.SType_Health: _Broken(300, True, refunded)},
        )
        V._machines = lambda controller: [(20.0, health_machine)]
        purse["credits"] = 1000
        V._refill()
        check(
            "money is handed back when the purchase fails after it was paid for",
            purse["credits"] == 1000,
            "$1000 became $%s after a heal that raised halfway through" % (purse["credits"],),
        )
        check(
            "and the failed job is reported as one you could not have",
            said and said[-1][1] == ["health"],
            "reported %r" % (said[-1] if said else None,),
        )

finally:
    V._machines = real_machines
    V._shop_info = real_shop_info
    V._charge = real_charge
    V._wallet = real_wallet
    V._is_client = real_is_client
    V._say = real_say
    V.enabled.value = was["enabled"]
    V.do_junk.value = was["junk"]
    V.do_health.value = was["health"]
    V.do_ammo.value = was["ammo"]
    V.reach.value = was["reach"]
    V.price.value = was["price"]
    V.far_prices.value = was["far"]
    print("restored every stub and every setting; money %s" % (money(p) if p else "n/a",))

summary()
