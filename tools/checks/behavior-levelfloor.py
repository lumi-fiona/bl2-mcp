# Enemies at your level below 50 - behavior checks for features/levelfloor.py
# Run: bash bl2-mcp/tools/ask.sh bl2-mcp/tools/checks/behavior-levelfloor.py   (after harness.py)
#
# Runs against the game's real code in memory: the switch is flipped off and on and the byte read
# back each time. The refusal is proved on a scratch page holding the wrong bytes, so the game's
# own code is never handed anything unexpected. That the byte really moves enemy levels was seen
# in the game, not here (ticket 12: area level 50 -> 1 for a level-1 character in playthrough 2).
reset()

import ctypes

from bl2_modern import core
from bl2_modern.features import levelfloor as LF

K = ctypes.WinDLL("kernel32")
K.VirtualAlloc.restype = ctypes.c_void_p
K.VirtualAlloc.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_uint32, ctypes.c_uint32]
K.VirtualFree.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_uint32]


def floor_byte(address=None):
    return ctypes.c_ubyte.from_address((address or LF._address()) + LF.FLOOR_AT).value


was = LF.enabled.value
real_address = LF._address
page = K.VirtualAlloc(None, 4096, 0x3000, 0x04)  # commit+reserve, read/write

try:
    feature = next((f for f in core.all_features() if f.name == "Enemies at your level below 50"), None)
    check("the feature loaded", feature is not None and feature.failed is None, feature and feature.failed)
    check("its switch is in the menu", feature is not None and LF.enabled in feature.options)

    code = bytes((ctypes.c_ubyte * len(LF.VANILLA)).from_address(LF._address()))
    check(
        "the live code is cmp esi,50 / jge +7 / mov eax,50 / pop esi / ret, the floor byte aside",
        code[: LF.FLOOR_AT] + code[LF.FLOOR_AT + 1 :] == LF.VANILLA[: LF.FLOOR_AT] + LF.VANILLA[LF.FLOOR_AT + 1 :],
        code.hex(" "),
    )

    for state, byte in ((False, 50), (True, 1), (True, 1), (False, 50), (True, 1)):
        LF.enabled.value = state
        check(f"switch {'on' if state else 'off'} leaves the floor at {byte}", floor_byte() == byte, floor_byte())

    # Writing through a null page would take the game down, so no page means no refusal checks.
    if check("a scratch page to test the refusal on was allocated", bool(page), page):
        # The refusal: a lookalike one byte off (cmp esi,51) must come back untouched.
        wrong = bytes.fromhex("83FE337D07B8320000005EC3")
        ctypes.memmove(page, wrong, len(wrong))
        LF._address = lambda: page
        LF._apply()
        got = ctypes.string_at(page, len(wrong))
        check("code that is not the floor is refused and nothing is written", got == wrong, got.hex(" "))

        # And the same path with the right bytes does write - so the refusal above is the check
        # refusing, not the write being broken.
        ctypes.memmove(page, LF.VANILLA, len(LF.VANILLA))
        LF._apply()
        check("the right bytes on the same page do get the 1", floor_byte(page) == 1, floor_byte(page))
finally:
    LF._address = real_address
    LF.enabled.value = was
    K.VirtualFree(page, 0, 0x8000)  # release
    check("the switch and the byte are left as found", floor_byte() == (1 if was else 50), floor_byte())

summary()
