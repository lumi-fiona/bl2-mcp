# The patch proof-read - checks for features/patchproof.py
# Run: bash bl2-mcp/tools/ask.sh bl2-mcp/tools/checks/patch-proof-read.py
#
# SAFETY: this feature only ever reads. Nothing here spawns, destroys, charges or applies
# anything. The one thing it does change is the mod's own options, and those are put back in
# the finally block. The job it starts is stopped there too, so nothing is left running.
#
# The check that matters most is "the game can be asked for an object without naming its
# class". If that comes back FAIL, the whole feature is worthless as written and the fix is a
# class lookup, not a tweak - patchproof.py says so in its own docstring.

reset()
import unrealsdk
from bl2_modern import reportjob
from bl2_modern.features import patchproof as PP

SAVED = (PP.enabled.value, PP.check_map_only.value, PP.work_per_frame.value)
SAID = []
REAL_SAY = reportjob.say
reportjob.say = lambda title, message, seconds=6: SAID.append(message)


class Struct:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class Deep:
    def __init__(self):
        self.Thing = [Struct(Inner=Struct(Value=3.0))]


try:
    # --- taking a set command apart -------------------------------------------------------
    check(
        "a plain set line is read apart into object, property and value",
        PP.parse_set("set A.B.C Prop 1.0") == ("A.B.C", [("Prop", None)], "1.0"),
        PP.parse_set("set A.B.C Prop 1.0"),
    )
    check(
        "a value containing spaces is kept whole",
        PP.parse_set("set A.B Prop (X=1, Y=2)")[2] == "(X=1, Y=2)",
        PP.parse_set("set A.B Prop (X=1, Y=2)"),
    )
    # 1,631 of the patch's own lines look like this. Getting it wrong puts two lines in five
    # into "cannot tell" and the report stops meaning anything.
    check(
        "a property several steps down is read apart step by step",
        PP.parse_set("set A.B Thing[2].Inner.Value 7")[1]
        == [("Thing", 2), ("Inner", None), ("Value", None)],
        PP.parse_set("set A.B Thing[2].Inner.Value 7"),
    )
    check(
        "a line that is not a set command is refused",
        PP.parse_set("exec other.txt") is None and PP.parse_set("set A.B") is None,
        "",
    )
    check(
        "a value several steps down can be read off an object",
        PP.read_value(Deep(), PP.parse_property("Thing[0].Inner.Value")) == (True, 3.0, ""),
        PP.read_value(Deep(), PP.parse_property("Thing[0].Inner.Value")),
    )
    check(
        "a property the object does not have is reported rather than guessed at",
        PP.read_value(Deep(), PP.parse_property("Thing[0].Missing"))[0] is False,
        PP.read_value(Deep(), PP.parse_property("Thing[0].Missing")),
    )

    # --- deciding whether a value landed ---------------------------------------------------
    wrong = {
        name: (got, want)
        for name, got, want in (
            ("1.0 against a float", PP.matches(1.0, "1.0"), True),
            ("a different number", PP.matches(2.0, "1.0"), False),
            ("True written as 1", PP.matches(True, "1"), True),
            ("None against None", PP.matches(None, "None"), True),
            ("None against a value", PP.matches(None, "3"), False),
            ("a struct that agrees", PP.matches(Struct(X=1.0, Y=2.0), "(X=1.0,Y=2.0)"), True),
            ("a struct that disagrees", PP.matches(Struct(X=1.0, Y=9.0), "(X=1.0,Y=2.0)"), False),
            ("an array of the wrong length", PP.matches([1.0], "(1.0,2.0)"), False),
            ("an array of structs", PP.matches([Struct(A=1)], "((A=1))"), True),
        )
        if got is not want
    }
    check(
        "the comparison agrees with a value that landed and disagrees with one that did not",
        not wrong,
        wrong or "all nine shapes agreed",
    )
    check(
        "a value this cannot compare is called out rather than failed",
        PP.matches(Struct(X=1.0), "(X=1.0,Z=2.0)") is None,
        PP.matches(Struct(X=1.0), "(X=1.0,Z=2.0)"),
    )

    # --- the one unknown the whole feature rests on -----------------------------------------
    # find_object wants a class name. The patch's set commands carry none. If asking for
    # "Object" cannot find a real object, every line comes back "not loaded" and the report is
    # four thousand confident wrong answers.
    KNOWN = "GD_Itempools.WeaponPools.Pool_Weapons_All_01_Common"
    by_class = None
    try:
        by_class = unrealsdk.find_object("ItemPoolDefinition", KNOWN)
    except Exception as ex:
        print(f"could not even find it by its own class: {ex!r}")
    found = reportjob.find(KNOWN)
    check(
        "the game can be asked for an object without naming its class",
        found is not None and by_class is not None and str(found) == str(by_class),
        f"asked for {KNOWN}: without a class -> {found}, with one -> {by_class}",
    )
    check(
        "asking for something that does not exist comes back empty rather than raising",
        reportjob.find("No.Such.Object.At.All") is None,
        reportjob.find("No.Such.Object.At.All"),
    )

    # --- the commands it will actually read back ---------------------------------------------
    PP.enabled.value = True
    PP.check_map_only.value = True
    commands = PP._commands_to_check()
    check(
        "the proof-read finds the patch lines the pack ran",
        len(commands) > 100,
        f"{len(commands)} lines gathered",
    )
    unparsed = [c for _f, c, _m in commands if PP.parse_set(c) is None]
    check(
        "every line the pack ran can be read apart",
        not unparsed,
        f"{len(unparsed)} of {len(commands)} could not be: {unparsed[:3]}",
    )
    map_only = sum(1 for _f, _c, m in commands if m)
    print(f"   {map_only} of the {len(commands)} lines belong to one particular map")

    # --- running it, a slice at a time --------------------------------------------------------
    # NOT to completion. Four thousand look-ups in one request would hold the frame open for
    # seconds, which is the one thing this pack's checks may never do. Two hundred steps is
    # enough to prove it starts, writes and makes progress.
    started = reportjob.start(PP.OWNER, PP.NAME, PP._work, 3)
    check("the proof-read starts", started and reportjob.busy() == PP.NAME, reportjob.busy())

    if started:
        blocked = reportjob.start("someone-else", "Another job", lambda: iter(()), 3)
        check(
            "a second long job is refused while one is running",
            blocked is False and reportjob.busy() == PP.NAME,
            f"second start returned {blocked}, running is {reportjob.busy()}",
        )

        for _ in range(200):
            if reportjob.busy() != PP.NAME:
                break
            reportjob.pump(PP.OWNER)

        written = reportjob.REPORTS / "patch-proof-read.txt"
        check(
            "the report file is written while the job is still running",
            written.is_file() and written.stat().st_size > 0,
            f"{written} - {written.stat().st_size if written.is_file() else 'missing'} bytes",
        )
        text = written.read_text(encoding="utf-8", errors="replace") if written.is_file() else ""
        check(
            "the report says whether object look-up works before it says anything else",
            "can this even find an object from a patch line" in text,
            text[:300],
        )

except Exception:
    import traceback
    print("\n--- this file raised; the checks below this point never ran ---")
    traceback.print_exc()

finally:
    reportjob.cancel(PP.OWNER)
    reportjob.say = REAL_SAY
    PP.enabled.value, PP.check_map_only.value, PP.work_per_frame.value = SAVED
    print(f"\nstopped the job (running now: {reportjob.busy()}), options put back")
    if SAID:
        print("it said: " + " | ".join(SAID[-6:]))

summary()
