# Game files / ini editor

Source file: `D:/SteamLibrary/steamapps/common/Borderlands 2/sdk_mods/bl2_modern/gamefiles.py`

**Purpose.** Finds the real Documents folder on Windows and edits single keys inside the game's ini files without disturbing any other byte, keeping a one-time pristine copy of each file it touches.

## Claims

### 1. A key is edited only inside the named section.

- proven today: **yes**
- evidence: gamefiles.py:152 'assert out[5] == "bAdminCanPause=false\\r\\n", "edited the wrong section’s copy of the key"' in the __main__ self-check — the one feature in this audit that ships a runnable check.
- reachable: filesystem_only
- missing capability: (none)

**How to prove it:**

python gamefiles.py; assert exit code 0 and stdout contains 'gamefiles: all checks passed'

### 2. CRLF line endings and the line count survive an edit.

- proven today: **yes**
- evidence: gamefiles.py:151 (asserts the \r\n survives), :153 and :160 (assert len(out) == len(SAMPLE), including for a final line with no ending).
- reachable: filesystem_only
- missing capability: (none)

**How to prove it:**

Same self-check.

### 3. A pristine copy is written once and never overwritten, so it keeps the owner's own settings rather than yesterday's.

- proven today: **no**
- evidence: Only the structural guard at gamefiles.py:129-131 'if not untouched.exists()'. The __main__ block never touches a real file.
- reachable: filesystem_only
- missing capability: (none)

**How to prove it:**

tmp ini with a known value; edit_ini twice with different values; assert the .bl2_modern_original file's bytes equal the ORIGINAL content, not the first edit's. Needs edit_ini to take a path or config_dir to be monkeypatchable — today it hardcodes config_dir() at :113, so the check needs a one-line seam.

### 4. documents_dir() finds a redirected or OneDrive Documents folder.

- proven today: **partly**
- evidence: gamefiles.py:169-171 prints the resolved paths and their .is_dir() when run directly, but prints rather than asserts. The paths do resolve on this machine — C:/Users/Lumi/Documents/My Games/Borderlands 2/WillowGame/SaveData exists and holds account 76561198860136601.
- reachable: filesystem_only
- missing capability: (none)

**How to prove it:**

Add to __main__: assert config_dir().is_dir(), config_dir(); assert savedata_dir().is_dir(), savedata_dir() — turn the two prints into asserts so a redirected Documents folder fails the check instead of printing 'exists: False'.

### 5. Edits actually land in the real files the game reads.

- proven today: **partly**
- evidence: unrealsdk.log:76-79 show configtweaks reporting four keys 'already' at the wanted value in WillowInput.ini / WillowGame.ini / WillowEngine.ini — which proves the reader works, not the writer.
- reachable: bridge_only
- missing capability: (none)

**How to prove it:**

Bridge: read the current value, edit_ini it to a different value, re-read the file from disk and assert the new value is present AND that len(open(path,'rb').read().split(b'\r\n')) is unchanged AND that a .bl2_modern_original file now exists; then edit it back.

## Suspected bugs

- **[cosmetic]** gamefiles.py:113 'path = config_dir() / filename'
  - edit_ini has no seam for testing — the directory is computed inside the function, so none of its behaviour (the pristine-copy-once rule, the line-count guard at :123-125, the no-change early return at :121) can be exercised without writing to the player's real config folder.
  - bites: The pure function apply_ini_edits has six asserts; edit_ini, which is the half that can destroy someone's settings, has none. An optional 'directory: Path | None = None' parameter would let the existing __main__ block cover it in about eight more lines.

- **[wrong_in_an_edge_case]** gamefiles.py:118 'path.read_text(encoding="utf-8", errors="replace")' and :133 'path.write_text("".join(updated), encoding="utf-8", errors="replace")'
  - errors="replace" on the read means any byte that is not valid UTF-8 becomes U+FFFD, and the write then persists the replacement character back to disk.
  - bites: The line-count guard at :123-125 cannot catch this — the count is identical, the bytes are not. A single non-UTF-8 byte anywhere in WillowGame.ini (a player name, a path with a latin-1 character) is silently rewritten the first time any feature edits any key in that file, and the pristine copy is taken with copy2 at :131 so at least it is recoverable. Reading as bytes, or with encoding='utf-8-sig' plus errors='surrogateescape', keeps the round trip honest.

- **[wrong_in_an_edge_case]** gamefiles.py:133 'path.write_text(...)' — in place, not atomic
  - The game's ini is truncated and rewritten directly.
  - bites: A crash mid-write leaves the player with a truncated WillowGame.ini. The pristine copy at :129-131 makes it recoverable by hand, but nothing in the pack knows to restore it. Write to path.with_suffix('.part') and replace — the same pattern bridge._reply already uses at bridge.py:75-77.
