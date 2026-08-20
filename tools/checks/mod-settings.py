# The two settings changed on other people's mods - checks for features/modsettings.py.
# Run: bash bl2-mcp/tools/ask.sh bl2-mcp/tools/checks/mod-settings.py
#
# Two different things are being checked and it is worth keeping them apart:
#
#   what is in the file on disk   which is what the mod will load next time the game starts
#   what the mod is holding now   which is what it is actually doing this session
#
# They can disagree, and when they do the file is the one that persists. Both are read.
#
# Read-only. It changes nothing on disk and nothing in the game, so there is nothing to put back.

import json

from mods_base.settings import SETTINGS_DIR

from bl2_modern.features import modsettings as ms

reset()


def from_file(module_name, identifier):
    """One setting's value as it is written on disk, digging through any nested pages."""
    path = SETTINGS_DIR / f"{module_name}.json"
    try:
        with path.open() as handle:
            data = json.load(handle)
    except Exception as ex:
        return None, repr(ex)

    def dig(section):
        for key, value in section.items():
            if key == identifier:
                return value, str(path)
            if isinstance(value, dict):
                found, where_found = dig(value)
                if found is not None:
                    return found, where_found
        return None, f"{identifier!r} is not in {path}"

    return dig(data.get("options", {}))


try:
    for module_name, identifier, expected, why in ms.WANTED:
        on_disk, where_found = from_file(module_name, identifier)
        check(
            f"{module_name}'s '{identifier}' is written to disk as {expected}",
            on_disk == expected,
            f"the file says {on_disk!r} ({where_found}) - {why}",
        )

        live, how = ms._find(module_name, identifier)
        check(
            f"{module_name} is running with '{identifier}' set to {expected} right now",
            live == expected,
            f"the running mod says {live!r} ({how})",
        )

    # A negative control. Without it, a lookup that silently returns nothing for everything would
    # make every check above pass by never finding a disagreement.
    nonsense, reason = ms._find("ItemLights", "There Is No Such Setting")
    check(
        "asking for a setting that does not exist comes back empty rather than pretending",
        nonsense is None and "There Is No Such Setting" in reason,
        f"got {nonsense!r} because {reason}",
    )

    missing, reason = ms._find("NoSuchModAtAll", "Anything")
    check(
        "asking about a mod that is not installed says so",
        missing is None and "not loaded" in reason,
        f"got {missing!r} because {reason}",
    )

    # --- the claim the Item Lights setting rests on --------------------------------------------
    # Turning on "Weapons and Gear Only" is only the right change if the mod's own list of what
    # counts as gear really is the five gear classes. This reads that list out of the loaded mod.
    try:
        import ItemLights

        whitelist = list(ItemLights.ClassWhitelist)
    except Exception as ex:
        whitelist = []
        print(f"could not read Item Lights' own list: {ex!r}")

    check(
        "Item Lights' idea of 'gear' is the five gear classes and nothing else",
        sorted(whitelist)
        == sorted(
            [
                "WillowWeapon",
                "WillowArtifact",
                "WillowGrenadeMod",
                "WillowShield",
                "WillowClassMod",
            ],
        ),
        f"its list is {whitelist} - if this changed upstream, the setting means something else "
        f"than it did when it was chosen",
    )
    check(
        "ammo, money and health vials are NOT on that list, which is the whole point",
        "WillowUsableItem" not in whitelist,
        f"WillowUsableItem is the class every ammo box, money bag and vial uses; list is "
        f"{whitelist}",
    )

    # --- the claim the reach setting rests on ---------------------------------------------------
    try:
        import AutoPickupTweaks

        slider = AutoPickupTweaks.oidPickupDistance
        stock_claim = "350 is the vanilla distance" in slider.description
        low, high = float(slider.min_value), float(slider.max_value)
    except Exception as ex:
        slider, stock_claim, low, high = None, False, 0.0, 0.0
        print(f"could not read Auto Pickup Tweaks' own slider: {ex!r}")

    check(
        "the reach we raised was sitting at the unmodded game's own distance",
        stock_claim,
        "the mod's own slider description is where '350 is the vanilla distance' comes from; "
        f"description reads: {getattr(slider, 'description', 'unreadable')!r}",
    )
    check(
        "900 is inside the range that slider will accept",
        low <= 900 <= high,
        f"the slider runs {low} to {high}. 900 IS A STARTING POINT, not a measured number - the "
        f"only test that settles it is walking past a pile of ammo",
    )

finally:
    summary()
