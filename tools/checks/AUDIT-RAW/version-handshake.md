# Version handshake

Source file: `D:/SteamLibrary/steamapps/common/Borderlands 2/sdk_mods/bl2_modern/features/handshake.py`

**Purpose.** Tells the two players when their two installs of the pack are not byte-identical, because that asymmetry is what silently deletes items in co-op.

## Claims

### 1. patch_fingerprint() is the first 12 hex chars of sha256(data/patch.txt), or 'none' when the file is absent.

- proven today: **no**
- evidence: (none)
- reachable: bridge_only
- missing capability: (none)

**How to prove it:**

Bridge: 'import hashlib, pathlib; from bl2_modern.features import handshake as H; p = pathlib.Path(H.__file__).parent.parent/"data"/"patch.txt"; assert H.patch_fingerprint() == hashlib.sha256(p.read_bytes()).hexdigest()[:12]; p2 = p.with_name("nope.txt"); print("OK")' — and separately monkeypatch the path to a missing file and assert it returns "none".

### 2. The fingerprint detects a bundled patch that changed without the version moving (handshake.py:5-7).

- proven today: **no**
- evidence: (none)
- reachable: filesystem_only
- missing capability: (none)

**How to prove it:**

f1 = H.patch_fingerprint(); append one byte to data/extras.txt; f2 = H.patch_fingerprint(); assert f1 != f2. Expected to FAIL — extras.txt is not hashed (see bug).

### 3. The announcement actually reaches the other player's machine.

- proven today: **no**
- evidence: (none)
- reachable: needs_second_player
- missing capability: a second machine or a second Borderlands 2 client in a real session; the bridge can drive both ends but only if both run the mod and the second one can be joined

**How to prove it:**

On machine B, before joining: 'from bl2_modern.features import handshake as H; H._RECEIVED=[]; _orig=H.announce.__wrapped__; H.announce.__wrapped__=lambda v,f: H._RECEIVED.append((v,f))'. Have A join. Then assert len(H._RECEIVED) == 1 and H._RECEIVED[0] == (A_version, A_fingerprint).

### 4. Playing alone never reports 'another player matches' (the self-delivery guard, handshake.py:38-40).

- proven today: **no**
- evidence: (none)
- reachable: needs_input
- missing capability: a live character (get_pc().PlayerReplicationInfo must exist), which needs a keypress at the title screen

**How to prove it:**

Solo, with a character live: record the byte length of unrealsdk.log; send 'from bl2_modern.features import handshake as H; H.announce(H.__version__, H.patch_fingerprint())'; wait 3s (message_queue.py:75-82 sends 1 message per tick); assert 'another player matches' does not appear in the log tail added since.

### 5. A genuine mismatch is reported.

- proven today: **no**
- evidence: (none)
- reachable: bridge_only
- missing capability: (none)

**How to prove it:**

Solo: 'from bl2_modern.features import handshake as H; from mods_base import get_pc; H.announce.sender = object(); H.announce.__wrapped__("0.0.0", "deadbeefcafe")' then assert 'Second Wind MISMATCH' in the new log tail and that it names both tuples.

### 6. The announcement fires once a character is live, when the network transport is up.

- proven today: **partly**
- evidence: Only the docstring's 'Moment 3, measured 2026-08-15' (handshake.py:66) and SPIKE-findings.md:23 timing the hook. No check that announce() itself succeeded rather than raising inside checked_get_pc (transmission.py:128-131).
- reachable: needs_input
- missing capability: a keypress to load a character

**How to prove it:**

Wrap it: before loading a character send 'from bl2_modern.features import handshake as H; H._SENT=[]; _o=H.announce.__call__; H.announce.__call__=lambda *a, **k: (H._SENT.append(a), _o(*a, **k))'. Load a character, then assert H._SENT == [(H.__version__, H.patch_fingerprint())].

### 7. It announces whenever you join someone.

- proven today: **no**
- evidence: (none)
- reachable: needs_second_player
- missing capability: a joinable second session, plus a keypress-driven quit-to-menu

**How to prove it:**

Load a character solo. assert H._announced is True. Quit to menu, join a co-op game, and assert a SECOND entry appeared in the H._SENT probe above. Expected to FAIL — see bug.

### 8. A player is warned. (The module's first line is 'Warns when two players are not running the identical pack.')

- proven today: **no**
- evidence: (none)
- reachable: needs_screenshot
- missing capability: seeing the screen; but the code-level version of the check needs nothing

**How to prove it:**

Trigger the mismatch path as above and assert something reaches the screen, not the log. Today the only sink is logging.error at handshake.py:47, so the honest assert is the negative: assert 'show_hud_message' not in Path('features/handshake.py').read_text() — which passes, i.e. nothing is shown.

### 9. Matching version + matching patch fingerprint means the two machines will actually behave the same.

- proven today: **no**
- evidence: (none)
- reachable: needs_second_player
- missing capability: a second machine

**How to prove it:**

On both machines send 'from bl2_modern.features import communitypatch as C, extras as E; print(sorted(C.wanted_sections() or []), sorted(E.wanted_sections() or []))' and assert the two outputs are equal. Nothing in the handshake compares this today.

### 10. The announce hook costs nothing at spawn time.

- proven today: **no**
- evidence: (none)
- reachable: bridge_only
- missing capability: (none)

**How to prove it:**

Bridge: 'import time; from bl2_modern.features import handshake as H; t=time.perf_counter(); H.patch_fingerprint(); print((time.perf_counter()-t)*1000)'; assert < 5 ms. data/patch.txt is 4,642,121 bytes (measured on disk), so expect roughly 10-30 ms, and it is computed twice per announce path (handshake.py:42 and :75).

## Suspected bugs

- **[breaks_the_feature]** features/handshake.py:53 '_announced = False' and :71-74 'global _announced / if _announced: return / _announced = True'
  - _announced latches for the lifetime of the process and is never reset. SpawningProcessComplete is documented in this very codebase as firing on every level load, not just the first — core.py:329 'Moment 3: a character is live, which is also every level load after the first.'
  - bites: The first SpawningProcessComplete of a session is your own character loading in, solo. By the time you quit to the menu and join your girlfriend's game — the only situation this feature exists for — _announced is already True and nothing is sent. The feature is silent in its single use case. Resetting _announced on quit-to-menu (or keying it on the host PRI rather than a bare bool) is the fix; the ponytail note at :67-69 correctly warns against a timer, and this does not need one.

- **[breaks_the_feature]** features/handshake.py:23 'patch = Path(__file__).parent.parent / "data" / "patch.txt"'
  - Only patch.txt is fingerprinted. The pack ships a second patch file: features/extras.py:72 declares patch_file="extras.txt", and core.py:78-80 explicitly documents that more than one feature may ship a patch. data/extras.txt is 107,352 bytes on disk and unrealsdk.log:68 shows it running 32 commands.
  - bites: Rebuild extras.txt (build_extras.py exists for exactly that) without bumping pyproject version and the two machines report 'another player matches' while running different set commands. That is precisely the failure the docstring at :4-7 says the fingerprint exists to catch. Hashing every file in data/ that any feature declares as a patch_file is a two-line change.

- **[breaks_the_feature]** features/handshake.py:47-50 'logging.error(f"Second Wind MISMATCH - ...")'
  - The only output is a line in unrealsdk.log / the tilde console. Nothing appears on the player's screen.
  - bites: Neither player will ever see it. The pack already has the mechanism — ui_utils.show_hud_message is imported and used at features/grinder.py:40 and :358 — so this is a one-line addition, and without it the module's opening sentence ('Warns when two players...') is not true of the running program.

- **[wrong_in_an_edge_case]** features/handshake.py:38-40 'local_pc = get_pc(); if local_pc is not None and announce.sender == local_pc.PlayerReplicationInfo: return'
  - When get_pc() returns None the guard is skipped entirely and execution falls through to the comparison.
  - bites: The docstring immediately above (:33-36) says 'Without the guard below, playing alone reports that another player matches' — and the 'is not None and' short-circuit re-opens exactly that. mods_base.get_pc is get_pc_willow (mods_base/__init__.py:160-163), which indexes GamePlayers[0], so during a loading screen it can also raise rather than return None; either way the announcer logs a self-match. Returning early when local_pc is None is the correct polarity.

- **[cosmetic]** features/handshake.py:26 'return hashlib.sha256(patch.read_bytes()).hexdigest()[:12]'
  - 4.6 MB is read and hashed on the game thread, and patch_fingerprint() is called twice on the announce path — once to send (:75, inside the SpawningProcessComplete hook) and once per received message (:42).
  - bites: A file read plus a full SHA-256 of 4.6 MB lands on the frame the player spawns into the world. Caching it in a module global at import costs one line and removes the hitch entirely.

- **[wrong_in_an_edge_case]** features/handshake.py:42 'mine = (__version__, patch_fingerprint())'
  - The fingerprint covers file contents only, not which sections of those files are switched on. communitypatch.wanted_sections() and extras.wanted_sections() (features/extras.py:47-49) decide which set commands actually run, and they come from per-machine BoolOptions.
  - bites: Two machines with byte-identical files but different section switches run different game data and are reported as matching. Same failure class as the extras.txt gap, and the fix is the same place: hash the sorted section set into the fingerprint.
