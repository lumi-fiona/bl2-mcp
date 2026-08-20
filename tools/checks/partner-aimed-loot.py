# Partner-aimed extra loot - checks for features/partnerloot.py
# Run: bash bl2-mcp/tools/ask.sh bl2-mcp/tools/checks/partner-aimed-loot.py
#
# The whole feature is about a second player, so the parts that genuinely need one - does the
# aimed gun reach them, is it actually the kind of gun their character wants - cannot be checked
# here and are not faked. What IS checked here, and was pure guesswork until it was:
#
#   * whether the per-character loot pools this feature is built on exist AT ALL. Every candidate
#     path in the module is a guess at a naming convention; this file looks each one up and says
#     which resolved. That check can fail, and if it does the feature falls back to the ordinary
#     all-characters pool, which is also checked.
#   * whether a player's character can be read off their replication info, and from which field.
#     This machine's own character stands in for the partner's, which is exactly the same read.
#   * that the hook does nothing at all except during the other feature's extra roll, and that
#     every failure path lets the blind roll stand rather than eating the enemy's loot.
#
# Nothing here drops an item. `_drop` is replaced with a recorder for every behaviour check, and
# put back in the finally block. The one thing that touches the world is in the -needs-travel file.
reset()

import unrealsdk
from unrealsdk.hooks import Block, Type as HookKind

from bl2_modern import core
from bl2_modern.features import extraloot as X
from bl2_modern.features import partnerloot as P

# Everything this file is allowed to change, remembered before it changes any of it.
was_enabled = P.enabled.value
was_what = P.what_drops.value
was_good = P.how_good.value
was_rolling = X._rolling
real_drop = P._drop
real_partners = P._partners
real_get_pc = P.get_pc
real_reported = P._field_reported

dropped = []


def recording_drop(pool_path, at):
    dropped.append((pool_path, at))
    return True


def refusing_drop(pool_path, at):
    dropped.append((pool_path, at))
    return False


class FakePartner:
    """Stands in for another player's replication info. Only the class field is ever read."""

    def __init__(self, text):
        self.PlayerClassDefinition = text


def fire(rolling=True, partner="CharClass_Assassin", func=None):
    """Run the hook body once. Returns what it gave back to the game."""
    del dropped[:]
    X._rolling = rolling
    if partner is not None:
        P._partners = lambda: [FakePartner(partner)]
    else:
        P._partners = lambda: []
    P._drop = func or recording_drop
    return P.on_extra_roll.__wrapped__("the dead enemy", None, None, None)


try:
    # --- is the feature wired in at all --------------------------------------------------------
    feature = next((f for f in core.all_features() if f.name == "Partner-aimed extra loot"), None)
    check(
        "the partner-aimed loot feature loaded into the pack without failing",
        feature is not None and feature.failed is None,
        "not registered" if feature is None else (feature.failed or "registered, no failure"),
    )
    check(
        "it ships switched off, because it changes what drops",
        P.enabled.default_value is False,
        f"default is {P.enabled.default_value!r}",
    )
    check(
        "it found the extra-roll feature it steers",
        P.extraloot is X,
        f"partnerloot.extraloot = {P.extraloot!r}",
    )
    check(
        "its hook sits on the same function the extra roll uses, as a pre-hook",
        list(P.on_extra_roll.hook_funcs)
        == [("WillowGame.WillowPawn:DropLootOnDeath", HookKind.PRE)],
        f"{list(P.on_extra_roll.hook_funcs)}",
    )
    check(
        "that hook is live in this session, not merely defined",
        P.on_extra_roll.get_active_count() == 1,
        f"{P.on_extra_roll.get_active_count()} of 1 hooks active",
    )
    check(
        "all three of its dials are carried to the mod menu",
        feature is not None
        and list(feature.options) == [P.enabled, P.what_drops, P.how_good],
        [getattr(o, "identifier", o) for o in getattr(feature, "options", [])],
    )

    # --- do the pools this whole feature depends on actually exist ------------------------------
    # This is the part that was pure guesswork. Every candidate path is looked up here and the
    # answer is reported per character, so a failure names which one is missing.
    found_class_mod = {}
    found_gun = {}
    for token, (who, mod_word, gun) in P.CHARACTERS.items():
        if who in found_class_mod:
            continue
        for kind, table in (("classmod", found_class_mod), ("weapon", found_gun)):
            hits = []
            for template in P.CANDIDATES[kind]:
                path = template.format(who=mod_word, gun=gun, rarity="04_Rare")
                try:
                    obj = unrealsdk.find_object("ItemPoolDefinition", path)
                except Exception:
                    obj = None
                if obj is not None:
                    hits.append(path)
            table[who] = hits

    check(
        "a class-mod pool aimed at a particular character exists for every character in the game",
        all(
            any("Pool_ClassMod_04_Rare" not in path for path in hits) and hits
            for hits in found_class_mod.values()
        ),
        "\n      ".join(f"{who}: {hits or 'NOTHING - falls back to the all-characters pool'}"
                        for who, hits in sorted(found_class_mod.items())),
    )
    check(
        "a pool of one particular kind of gun exists for every character's favourite",
        all(
            any("Pool_Weapons_All_" not in path for path in hits) and hits
            for hits in found_gun.values()
        ),
        "\n      ".join(f"{who}: {hits or 'NOTHING - falls back to the all-guns pool'}"
                        for who, hits in sorted(found_gun.items())),
    )

    # The fallback is the part that must never fail, because it is what makes a wrong guess above
    # cost nothing. These two pool names are measured (BL2-LOOT-POOLS.md:49-55).
    P._known.clear()
    fallback_mod = P._pool_path("classmod", "NotARealCharacter", "NotARealGun")
    fallback_gun = P._pool_path("weapon", "NotARealCharacter", "NotARealGun")
    # Pool_ClassMod_04_Rare does not exist. MEASURED 2026-08-20 by listing every item pool in
    # the game: class mods number their rarities 01/02/03_Rare/04_VeryRare/05_Legendary, which
    # is not the set weapons use, and there is no all-character pool with a rarity in its name
    # at all. The one that does exist and holds every character's mods is Pool_ClassMod_All, and
    # that is what the fallback now names.
    check(
        "a character nobody has heard of still gets a real class-mod pool rather than nothing",
        fallback_mod == "GD_Itempools.ClassModPools.Pool_ClassMod_All",
        f"{fallback_mod!r}",
    )
    check(
        "and that fallback pool is really in the game, not just a plausible name",
        fallback_mod is not None
        and unrealsdk.find_object("ItemPoolDefinition", fallback_mod) is not None,
        f"{fallback_mod!r}",
    )
    check(
        "and a real gun pool",
        fallback_gun == "GD_Itempools.WeaponPools.Pool_Weapons_All_04_Rare",
        f"{fallback_gun!r}",
    )

    P._known.clear()
    P.how_good.value = "Legendary"
    legendary = P._pool_path("weapon", "NotARealCharacter", "NotARealGun")
    check(
        "moving the quality dial to Legendary really does pick a different pool",
        legendary is not None and legendary != fallback_gun and "Legendary" in legendary,
        f"{legendary!r}",
    )
    P.how_good.value = was_good
    P._known.clear()

    # --- can a player's character be read off their replication info at all ----------------------
    # This machine's own character is the same read the partner's needs.
    P._field_reported = False
    mine = None
    try:
        mine = pc().PlayerReplicationInfo
    except Exception as ex:
        mine = None
    check(
        "this machine has a replication info to read a character off",
        mine is not None,
        str(mine),
    )
    if mine is not None:
        which = None
        for field in P.CLASS_FIELDS:
            try:
                value = getattr(mine, field)
            except Exception:
                continue
            if value is not None:
                which = (field, str(value))
                break
        check(
            "one of the fields the module probes for really names the character",
            which is not None,
            f"tried {P.CLASS_FIELDS}, found {which!r}",
        )
        read_back = P._character_of(mine)
        check(
            "and the module turns that into a character it recognises",
            read_back is not None,
            f"{read_back!r} from {which!r} - a failure here means the aimed roll can never aim, "
            f"and the feature correctly does nothing at all rather than dropping something wrong",
        )

    # --- the hook does nothing unless it is the extra roll ----------------------------------------
    P.enabled.value = False
    returned = fire(rolling=True)
    check(
        "with the option off, nothing is dropped and the game's own drop is untouched",
        returned is None and not dropped,
        f"returned {returned!r}, dropped {dropped}",
    )

    P.enabled.value = True
    returned = fire(rolling=False)
    check(
        "an ordinary enemy death - the extra roll not running - is left completely alone",
        returned is None and not dropped,
        f"returned {returned!r}, dropped {dropped}. This is the check that stops the feature "
        f"eating the loot every enemy in the game was going to drop anyway",
    )

    returned = fire(rolling=True)
    check(
        "during the extra roll, something is dropped",
        len(dropped) == 1,
        f"dropped {dropped}",
    )
    check(
        "and the blind repeat it replaces is blocked, so the enemy does not drop twice over",
        returned is Block,
        f"returned {returned!r}",
    )
    check(
        "the loot is aimed at the dead enemy, so it lands where the fight was",
        dropped and dropped[0][1] == "the dead enemy",
        f"{dropped}",
    )

    P.what_drops.value = "Their class mod"
    fire(rolling=True, partner="CharClass_Assassin")
    aimed_mod = dropped[0][0] if dropped else None
    P.what_drops.value = "A gun their character likes"
    fire(rolling=True, partner="CharClass_Assassin")
    aimed_gun = dropped[0][0] if dropped else None
    check(
        "asking for a class mod and asking for a gun pick different pools",
        aimed_mod is not None and aimed_gun is not None and aimed_mod != aimed_gun,
        f"class mod pool {aimed_mod!r}, gun pool {aimed_gun!r}",
    )
    check(
        "the class mod pool is a class mod pool and the gun pool is a gun pool",
        aimed_mod is not None and "ClassMod" in aimed_mod
        and aimed_gun is not None and "Weapon" in aimed_gun,
        f"{aimed_mod!r} / {aimed_gun!r}",
    )

    P.what_drops.value = "Their class mod"
    fire(rolling=True, partner="CharClass_Siren")
    for_siren = dropped[0][0] if dropped else None
    fire(rolling=True, partner="CharClass_Soldier")
    for_soldier = dropped[0][0] if dropped else None
    check(
        "two different partners are aimed at differently - which is the entire feature",
        for_siren is not None and for_siren != for_soldier,
        f"Maya gets {for_siren!r}, Axton gets {for_soldier!r}. If these are equal, every "
        f"per-character pool guess in the module was wrong and everything falls back to one pool",
    )

    # --- every way this can go wrong lets the blind roll stand -------------------------------------
    returned = fire(rolling=True, partner=None)
    check(
        "playing alone, nothing is aimed anywhere and the blind roll is not blocked",
        returned is None and not dropped,
        f"returned {returned!r}, dropped {dropped}",
    )

    returned = fire(rolling=True, partner="CharClass_SomebodyElse")
    check(
        "a character the module does not recognise leaves the blind roll alone rather than "
        "guessing at a pool",
        returned is None and not dropped,
        f"returned {returned!r}, dropped {dropped}",
    )

    returned = fire(rolling=True, func=refusing_drop)
    check(
        "a drop the game refuses leaves the blind roll standing, so the enemy still drops "
        "something",
        returned is None and len(dropped) == 1,
        f"returned {returned!r}, dropped {dropped}",
    )

    def exploding_drop(pool_path, at):
        raise RuntimeError("pretend the behaviour object is gone")

    escaped = None
    try:
        returned = fire(rolling=True, func=exploding_drop)
    except Exception as ex:
        escaped, returned = ex, "raised"
    check(
        "an aimed drop that throws can never stop an enemy from dying",
        escaped is None and returned is None,
        f"{escaped!r}, returned {returned!r}",
    )

    # --- co-op: a machine that joined someone else's game must not drop -----------------------------
    class FakeClient:
        WorldInfo = type("W", (), {"NetMode": 3})()
        Pawn = None

    P.get_pc = lambda *_a, **_k: FakeClient()
    returned = fire(rolling=True)
    P.get_pc = real_get_pc
    check(
        "pretending to be a machine that joined someone else's game, nothing is dropped - loot "
        "invented on a client is loot nobody else can see",
        returned is None and not dropped,
        f"returned {returned!r}, dropped {dropped}",
    )

    # --- this session, for real ----------------------------------------------------------------------
    def as_int(value):
        try:
            return int(getattr(value, "value", value))
        except Exception:
            return -1

    try:
        net_mode = as_int(pc().WorldInfo.NetMode)
    except Exception:
        net_mode = -1
    check(
        "this session is the host, so anything this feature drops here would really exist",
        net_mode in (0, 1, 2),
        f"NetMode={net_mode} (3 would be a machine that joined someone else's game)",
    )

finally:
    P._drop = real_drop
    P._partners = real_partners
    P.get_pc = real_get_pc
    P.enabled.value = was_enabled
    P.what_drops.value = was_what
    P.how_good.value = was_good
    P._field_reported = real_reported
    P._known.clear()
    X._rolling = was_rolling
    check(
        "everything this file changed has been put back",
        P._drop is real_drop
        and P._partners is real_partners
        and P.get_pc is real_get_pc
        and P.enabled.value == was_enabled
        and P.what_drops.value == was_what
        and P.how_good.value == was_good
        and X._rolling == was_rolling,
        f"enabled={P.enabled.value} what={P.what_drops.value!r} good={P.how_good.value!r} "
        f"extraloot._rolling={X._rolling}",
    )

summary()
