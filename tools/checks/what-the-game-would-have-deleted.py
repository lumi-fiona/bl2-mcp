# What the game would have deleted - everything decidable without reloading a character.
# Run: bash bl2-mcp/tools/ask.sh bl2-mcp/tools/harness.py
#      bash bl2-mcp/tools/ask.sh bl2-mcp/tools/checks/what-the-game-would-have-deleted.py
#
# NOTHING IN HERE CALLS ValidateItemDefinition OR ValidateWeaponDefinition. That is not caution,
# it is the single rule this feature is built around: SanitySaver/hooks.py:418-419 says calling
# them "means we have to force all items to get sanity checked and be destroyed". The first check
# below reads the feature's own source and fails if it ever starts calling them, and this file
# holds itself to the same rule. It touches no real gear either - the description machinery is
# driven with a stand-in and, where a real item is used, only read.
#
# The half that genuinely needs a character reload - does the hook fire at all during a load, and
# does the count comparison name a real loss - is in
# what-the-game-would-have-deleted-needs-travel.py.
reset()

import re
from pathlib import Path

import unrealsdk
from bl2_modern import core, mod as pack
from bl2_modern.features import itemcheck as I
from unrealsdk.hooks import Type as HookKind

was = {
    "enabled": I.enabled.value,
    "on_screen": I.on_screen.value,
    "even_fine": I.even_when_fine.value,
    "write": I.write_a_file.value,
    "folder": I.FOLDER,
    "seen": list(I._seen),
    "chest": I._chest_until,
    "report": I._last_report,
}
scratch = I.FOLDER.parent / "nights-check-itemcheck"


class Fake:
    """A stand-in for a DefinitionData struct. The feature only ever getattrs, so this is enough."""

    def __init__(self, **kw):
        self.__dict__.update(kw)


class FakePart:
    def __init__(self, path):
        self._path = path
        self.Name = path.rsplit(".", 1)[-1]

    def PathName(self, _self):
        return self._path


def fake_weapon(uid, missing=(), stage=50):
    """A weapon definition with every slot filled except the ones named."""
    data = Fake(UniqueId=uid, GameStage=stage)
    for field in I.WEAPON_FIELDS:
        setattr(data, field, None if field in missing else FakePart(f"GD_Test.Parts.{field}"))
    return data


def fake_item(uid, missing=(), stage=50):
    data = Fake(UniqueId=uid, GameStage=stage)
    for field in I.ITEM_FIELDS:
        setattr(data, field, None if field in missing else FakePart(f"GD_Test.Parts.{field}"))
    return data


def function_exists(path):
    for candidate in (path.replace(":", "."), path):
        try:
            if unrealsdk.find_object("Function", candidate) is not None:
                return candidate
        except Exception:
            continue
    return None


try:
    # --- THE SAFETY RULE ----------------------------------------------------------------------
    source = Path(str(core.__file__)).parent.joinpath("features", "itemcheck.py").read_text(
        encoding="utf-8",
    )
    code_only = "\n".join(
        line for line in source.splitlines() if not line.lstrip().startswith("#")
    )
    # A call looks like `.ValidateItemDefinition(` - the bare name appears all over the docstring
    # and in the hook strings, and neither of those runs anything.
    calls = re.findall(r"\.\s*Validate(?:Item|Weapon)Definition\s*\(", code_only)
    check(
        "the feature never calls the game's item check, which is the call that destroys items",
        not calls,
        f"found {calls}" if calls else "no call sites in itemcheck.py",
    )

    # The self-check needs the same comment-stripping as the check just above it, and for the
    # same reason it was needed there: this very file explains, in a comment, what a dangerous
    # call looks like - "a call looks like `.ValidateItemDefinition(`" - and a regex that reads
    # comments cannot tell that sentence apart from the call it is warning about. MEASURED
    # 2026-08-20: read as raw text, this file matches the pattern once, at that comment, so the
    # self-check failed on every run - not because a call was ever added.
    self_source = Path(str(core.__file__)).parent.parent.parent.joinpath(
        "bl2-mcp", "tools", "checks", "what-the-game-would-have-deleted.py",
    ).read_text(encoding="utf-8")
    self_code_only = "\n".join(
        line for line in self_source.splitlines() if not line.lstrip().startswith("#")
    )
    check(
        "this check file does not call it either",
        not re.findall(r"\.\s*Validate(?:Item|Weapon)Definition\s*\(", self_code_only),
        "self-check, so a future edit to this file cannot quietly break the rule",
    )

    # --- do the two functions exist ---------------------------------------------------------------
    for name in (
        "WillowGame.WillowPlayerController:ValidateItemDefinition",
        "WillowGame.WillowPlayerController:ValidateWeaponDefinition",
        "WillowGame.WillowInventoryStorage:Open",
    ):
        found = function_exists(name)
        check(
            f"the game really has {name.rsplit(':', 1)[1]}",
            found is not None,
            f"found as {found}" if found else "not an object in this game, so the hook is dead",
        )

    # --- wired in ------------------------------------------------------------------------------------
    feature = next(
        (f for f in core.all_features() if f.name == "What the game would have deleted"), None,
    )
    check(
        "the feature loaded into the pack without failing",
        feature is not None and feature.failed is None,
        "not registered" if feature is None else (feature.failed or "registered, no failure"),
    )
    check(
        "it watches both checks before they run",
        sorted(f for f, t in I.on_checked.hook_funcs if t is HookKind.PRE)
        == [
            "WillowGame.WillowPlayerController:ValidateItemDefinition",
            "WillowGame.WillowPlayerController:ValidateWeaponDefinition",
        ],
        f"{list(I.on_checked.hook_funcs)}",
    )
    check(
        "it reads the answer with an unconditional post-hook, so Sanity Saver blocking it "
        "does not hide the answer",
        all(t is HookKind.POST_UNCONDITIONAL for _f, t in I.on_verdict.hook_funcs)
        and len(I.on_verdict.hook_funcs) == 2,
        f"{list(I.on_verdict.hook_funcs)}",
    )
    check(
        "all four hooks are live in this session rather than merely defined",
        all(
            h.get_active_count() == len(h.hook_funcs)
            for h in (I.on_checked, I.on_verdict, I.on_container_opened, I.on_character_live)
        ),
        ", ".join(
            f"{h.__wrapped__.__name__}={h.get_active_count()}/{len(h.hook_funcs)}"
            for h in (I.on_checked, I.on_verdict, I.on_container_opened, I.on_character_live)
        ),
    )
    check(
        "all four settings belong to the pack that owns the settings file",
        all(
            o.mod is pack
            for o in (I.enabled, I.on_screen, I.even_when_fine, I.write_a_file)
        ),
        f"{[getattr(o.mod, 'name', None) for o in (I.enabled, I.on_screen, I.even_when_fine, I.write_a_file)]}",
    )

    # --- is Sanity Saver actually on, which is what the report's honesty depends on ------------------
    from mods_base import mod_list

    saver = next((m for m in mod_list.mod_list if m.name == "Sanity Saver"), None)
    check(
        "Sanity Saver is installed and switched on, so nothing should really be being deleted",
        saver is not None and saver.is_enabled,
        "not installed" if saver is None else f"enabled={saver.is_enabled} version={saver.version}",
    )
    state = I._sanity_saver_state()
    check(
        "the report can tell the player which of those two worlds they are in",
        "Sanity Saver" in state,
        state,
    )

    # --- the hooks never change what the game does ------------------------------------------------------
    I.enabled.value = True
    I.FOLDER = scratch
    # No messages on screen and no files: this file drives the load handler directly several
    # times, and a person playing should not get four "something was deleted" banners because a
    # check ran.
    I.on_screen.value = False
    I.write_a_file.value = False
    del I._seen[:]
    I._chest_until = -99.0

    returns = [
        I.on_checked.__wrapped__(None, Fake(DefinitionData=fake_weapon(1)), None, None),
        I.on_verdict.__wrapped__(None, None, True, None),
        I.on_container_opened.__wrapped__(None, None, None, None),
    ]
    check(
        "watching the check never blocks it and never changes its answer",
        set(returns) == {None},
        f"returned {returns!r}",
    )
    I._chest_until = -99.0

    # --- weapon and item are told apart by their fields, not by which function fired -------------------
    del I._seen[:]
    I.on_checked.__wrapped__(None, Fake(DefinitionData=fake_weapon(11)), None, None)
    I.on_checked.__wrapped__(None, Fake(DefinitionData=fake_item(12)), None, None)
    check(
        "a weapon is recorded as a gun and an item as an item",
        [e["kind"] for e in I._seen] == ["gun", "item"],
        f"{[e['kind'] for e in I._seen]}",
    )
    check(
        "each entry keeps the id the comparison later matches on",
        [e["id"] for e in I._seen] == [11, 12],
        f"{[e['id'] for e in I._seen]}",
    )

    # --- the reason ------------------------------------------------------------------------------------
    del I._seen[:]
    I.on_checked.__wrapped__(
        None, Fake(DefinitionData=fake_weapon(20, missing=("BarrelPartDefinition",))), None, None,
    )
    check(
        "a missing barrel is named as the reason",
        I._seen[0]["suspicious"] == ["BarrelPartDefinition"],
        f"{I._seen[0]['suspicious']} (all empty: {I._seen[0]['empty']})",
    )

    del I._seen[:]
    I.on_checked.__wrapped__(
        None,
        Fake(DefinitionData=fake_weapon(21, missing=("SightPartDefinition", "Accessory1PartDefinition"))),
        None,
        None,
    )
    check(
        "a gun with no scope and no accessory is not accused of anything - that is ordinary",
        I._seen[0]["suspicious"] == [] and len(I._seen[0]["empty"]) == 2,
        f"suspicious={I._seen[0]['suspicious']} empty={I._seen[0]['empty']}",
    )

    # --- the verdict lands on the right entry --------------------------------------------------------------
    del I._seen[:]
    I.on_checked.__wrapped__(None, Fake(DefinitionData=fake_weapon(30)), None, None)
    I.on_verdict.__wrapped__(None, None, False, None)
    I.on_checked.__wrapped__(None, Fake(DefinitionData=fake_weapon(31)), None, None)
    I.on_verdict.__wrapped__(None, None, True, None)
    check(
        "each answer is attached to the item it was about",
        [(e["id"], e["verdict"]) for e in I._seen] == [(30, False), (31, True)],
        f"{[(e['id'], e['verdict']) for e in I._seen]}",
    )

    # --- bank items are not counted as the character's losses -------------------------------------------------
    del I._seen[:]
    I.on_container_opened.__wrapped__(None, None, None, None)
    I.on_checked.__wrapped__(None, Fake(DefinitionData=fake_weapon(40)), None, None)
    check(
        "something checked just after a bank opened is marked as the bank's",
        I._seen and I._seen[0]["from_a_chest"] is True,
        f"{I._seen}",
    )
    I._chest_until = -99.0
    I.on_checked.__wrapped__(None, Fake(DefinitionData=fake_weapon(41)), None, None)
    check(
        "and something checked well after it is not",
        I._seen[1]["from_a_chest"] is False,
        f"{I._seen[1]}",
    )

    # --- the comparison, against the real character -------------------------------------------------------------
    # A real carried item's id is used as the one that survived, and an id nothing has as the one
    # that did not. Nothing is spawned, nothing is removed, nothing is written to any item.
    from bl2_modern.features.levelless import carried

    live = carried(pc())
    real_ids = []
    for item in live:
        try:
            real_ids.append(int(item.DefinitionData.UniqueId))
        except Exception:
            pass
    check(
        "this character is carrying something, so the comparison has real data to work on",
        bool(real_ids),
        f"{len(live)} things carried, {len(real_ids)} with a readable id",
    )

    if real_ids:
        del I._seen[:]
        I._chest_until = -99.0
        I.on_checked.__wrapped__(
            None, Fake(DefinitionData=fake_weapon(real_ids[0])), None, None,
        )
        I.on_checked.__wrapped__(
            None,
            Fake(DefinitionData=fake_weapon(-777, missing=("BodyPartDefinition",))),
            None,
            None,
        )
        text, lost = I._build_report(pc())
        check(
            "the thing that is still in your hands is not reported as deleted",
            len(lost) == 1 and lost[0]["id"] == -777,
            f"reported {[e['id'] for e in lost]} as lost, real id was {real_ids[0]}",
        )
        check(
            "the report names what went and why",
            "did not survive" in text and "BodyPartDefinition" in text,
            text,
        )
        check(
            "the report says which of Sanity Saver's two worlds this is",
            "Sanity Saver" in text,
            text,
        )

        del I._seen[:]
        I.on_checked.__wrapped__(None, Fake(DefinitionData=fake_weapon(real_ids[0])), None, None)
        clean, nothing_lost = I._build_report(pc())
        check(
            "a load where everything survived says so instead of saying nothing",
            not nothing_lost and "still here" in clean,
            clean,
        )

    # --- checks from a previous load are not dragged into this one ------------------------------------------------
    del I._seen[:]
    I._chest_until = -99.0
    I.on_checked.__wrapped__(None, Fake(DefinitionData=fake_weapon(-888)), None, None)
    I._seen[0]["at"] -= I.WINDOW_SECONDS + 60
    stale_text, stale_lost = I._build_report(pc())
    check(
        "an item checked an hour ago is not reported as lost on this load",
        not stale_lost and "Nothing was checked" in stale_text,
        stale_text,
    )

    # --- nothing at all ---------------------------------------------------------------------------------------------
    del I._seen[:]
    empty_text, empty_lost = I._build_report(pc())
    check(
        "with nothing checked, the report says so rather than claiming a clean load",
        not empty_lost and "Nothing was checked" in empty_text,
        empty_text,
    )
    check(
        "with nothing checked it does not ALSO say items were skipped - one nothing, said once",
        "Guns were checked and items were not" not in empty_text,
        empty_text,
    )

    # Guns checked and items not is the shape Sanity Saver actually produces, and it is the one
    # asymmetry worth explaining. It must be explained then, and only then.
    del I._seen[:]
    I._chest_until = -99.0
    I.on_checked.__wrapped__(None, Fake(DefinitionData=fake_weapon(-999)), None, None)
    guns_only, _lost = I._build_report(pc())
    check(
        "when guns were checked and items were not, the report explains why",
        "Guns were checked and items were not" in guns_only,
        guns_only,
    )

    # --- nonsense in, no exception out --------------------------------------------------------------------------------
    escaped = []
    for name, hook_object, arguments in (
        ("checked", I.on_checked, (None, Fake(), None, None)),
        ("checked-nothing", I.on_checked, (None, None, None, None)),
        ("verdict", I.on_verdict, (None, None, object(), None)),
        ("container", I.on_container_opened, (None, None, None, None)),
        ("live", I.on_character_live, (None, None, None, None)),
    ):
        try:
            hook_object.__wrapped__(*arguments)
        except Exception as ex:
            escaped.append(f"{name}: {ex!r}")
    check(
        "loading a character cannot fail because this feature was handed something it did not expect",
        not escaped,
        "; ".join(escaped) or "all five survived",
    )

    # --- with the feature off, it records nothing at all ------------------------------------------------------------------
    I.enabled.value = False
    del I._seen[:]
    I.on_checked.__wrapped__(None, Fake(DefinitionData=fake_weapon(50)), None, None)
    check(
        "switched off, it does not even look",
        not I._seen,
        f"{I._seen}",
    )

finally:
    for path in sorted(scratch.glob("*")) if scratch.is_dir() else []:
        try:
            path.unlink()
        except Exception:
            pass
    try:
        scratch.rmdir()
    except Exception:
        pass

    I.enabled.value = was["enabled"]
    I.on_screen.value = was["on_screen"]
    I.even_when_fine.value = was["even_fine"]
    I.write_a_file.value = was["write"]
    I.FOLDER = was["folder"]
    I._chest_until = was["chest"]
    I._last_report = was["report"]
    del I._seen[:]
    I._seen.extend(was["seen"])

    check(
        "everything this file changed has been put back",
        I.enabled.value == was["enabled"]
        and I.FOLDER == was["folder"]
        and I._seen == was["seen"]
        and I._chest_until == was["chest"]
        and not scratch.exists(),
        f"enabled={I.enabled.value} folder={I.FOLDER} seen={len(I._seen)} "
        f"scratch still there={scratch.exists()}",
    )

summary()
