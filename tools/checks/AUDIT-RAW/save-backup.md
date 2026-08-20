# Save backup

Source file: `D:/SteamLibrary/steamapps/common/Borderlands 2/sdk_mods/bl2_modern/features/savebackup.py`

**Purpose.** Keeps five rotating copies of every character save, taken once at mod load, so a load that corrupts a save is recoverable.

## Claims

### 1. It runs once per launch, at import, before any other feature.

- proven today: **partly**
- evidence: Ordering is structural: features/__init__.py:23 puts "savebackup" first in FEATURES and core.load_features iterates in order (core.py:109-115). Observed in unrealsdk.log line 24: 'savebackup.py@79 INFO| savebackup: 4 saves, 0 newly copied, 5 deep, 0.3 MB' at 11:25:39.188, before the pack's status line at 11:25:39.276. That is one observed launch, not a check.
- reachable: filesystem_only
- missing capability: (none)

**How to prove it:**

Parse unrealsdk.log: assert the index of the first line matching 'savebackup: .* saves' is lower than the index of every other 'sdk_mods\\bl2_modern' line, and that it appears exactly once per process start.

### 2. Every Save*.sav in the account folder gets a .1 copy.

- proven today: **partly**
- evidence: Observed on disk 2026-08-19: SaveData/76561198860136601 holds Save0104/0106/0107/0108.sav, and bl2_modern_backups holds a .1 for each. Nothing asserts it.
- reachable: filesystem_only
- missing capability: (none)

**How to prove it:**

acct = savedata_dir()/'76561198860136601'; live = {p.name for p in acct.glob('Save*.sav')}; ones = {p.name[:-2] for p in (acct/'bl2_modern_backups').iterdir() if p.name.endswith('.1')}; assert live <= ones

### 3. Depth is exactly five: nothing older than .5 ever survives.

- proven today: **no**
- evidence: Save0104 currently has .1 through .5 and no .6, which is consistent but is not a test of the boundary.
- reachable: bridge_only
- missing capability: savebackup.py:16 does 'from unrealsdk import logging' at module scope, so _rotate cannot be imported outside the game. Making that import lazy would move this whole class of check to filesystem_only, the way gamefiles.py:137-168 already does.

**How to prove it:**

tmp = Path(tempfile.mkdtemp()); s = tmp/'Save9999.sav'; b = tmp/'b'; b.mkdir(); for i in range(7): s.write_bytes(bytes([i])*100); savebackup._rotate(s, b); assert sorted(p.name for p in b.iterdir()) == [f'Save9999.sav.{i}' for i in range(1,6)]; assert (b/'Save9999.sav.1').read_bytes()[0] == 6 and (b/'Save9999.sav.5').read_bytes()[0] == 2

### 4. An unchanged save does not consume a rotation slot (_rotate returns False, savebackup.py:41-42).

- proven today: **partly**
- evidence: unrealsdk.log line 24 reads '4 saves, 0 newly copied' — the skip path fired for all four. Observed once, no assert.
- reachable: bridge_only
- missing capability: same lazy-import change as above

**How to prove it:**

Same tmp harness: write s once, call _rotate twice; assert the second call returns False and not (b/'Save9999.sav.2').exists()

### 5. The copy is byte-identical to the save it came from.

- proven today: **no**
- evidence: (none)
- reachable: filesystem_only
- missing capability: (none)

**How to prove it:**

for s in acct.glob('Save*.sav'): assert (acct/'bl2_modern_backups'/f'{s.name}.1').read_bytes() == s.read_bytes() — valid only immediately after a launch where the log said that save was 'newly copied'.

### 6. Restoring a backup gives you your character back.

- proven today: **no**
- evidence: (none)
- reachable: needs_input
- missing capability: loading a character needs a keypress; the compare itself is bridge-readable via pc.GetPawnInventoryManager().Backpack

**How to prove it:**

Rename Save0104.sav aside, copy bl2_modern_backups/Save0104.sav.3 to Save0104.sav, launch, load it, and read the backpack through the bridge: assert every item that was in the .3-era character is still there. Expected to FAIL on non-vanilla items — see bug.

### 7. It never modifies the live save.

- proven today: **no**
- evidence: (none)
- reachable: filesystem_only
- missing capability: (none)

**How to prove it:**

Hash every Save*.sav before launch, launch, and re-hash after the savebackup log line appears: assert the dict of hashes is unchanged.

### 8. It refuses to guess when the account folder is ambiguous, and says so (savebackup.py:62-70).

- proven today: **no**
- evidence: (none)
- reachable: bridge_only
- missing capability: (none)

**How to prove it:**

Bridge: monkeypatch savebackup.savedata_dir to a temp root containing two digit-named dirs, call savebackup._back_up(), assert neither dir gained a bl2_modern_backups folder and that 'expected one account folder' appears in the log tail.

### 9. It warns when the backup folder passes 500 MB.

- proven today: **no**
- evidence: (none)
- reachable: bridge_only
- missing capability: (none)

**How to prove it:**

Bridge: savebackup.WARN_MB = 0; savebackup._back_up(); assert 'past the 0 MB mark' appears in the log tail. Then restore WARN_MB = 500.

### 10. A failure inside this feature does not stop the rest of the pack loading.

- proven today: **partly**
- evidence: Structural only: core.load_features wraps each import in 'except Exception' (core.py:112-115), and savebackup calls _back_up() at :89 before register() at :91 so a raise leaves exactly one failed entry.
- reachable: filesystem_only
- missing capability: (none)

**How to prove it:**

Temporarily insert 'raise RuntimeError("probe")' at the top of _back_up, relaunch, and assert unrealsdk.log contains 'Second Wind 0.17.0 - 14 of 15 loaded - FAILED: savebackup' and still contains the grinder/display apply lines.

### 11. Backups do not grow without bound in a way anybody notices.

- proven today: **no**
- evidence: (none)
- reachable: filesystem_only
- missing capability: (none)

**How to prove it:**

assert sum(f.stat().st_size for f in backups.iterdir())/1048576 < 500 — currently 0.3 MB per the log, so this passes today and proves nothing about the growth path.

## Suspected bugs

- **[breaks_the_feature]** features/savebackup.py:75 'saves = sorted(accounts[0].glob("Save*.sav"))'
  - The backup is incomplete. Sanity Saver — the component this pack calls non-negotiable (features/sanitysaver.py:6-8) — keeps the data that makes non-vanilla items survive a load OUTSIDE SaveData, at sdk_mods/SanitySaver/Saves/<SaveName>.json.gz. Confirmed: SanitySaver/save_manager.py:17 '_SAVES_DIR = Path(__file__).parent / "Saves"' and :43 'file_name = Path(save_name).stem + ("_Bank" if is_bank else "") + ".json"'. That folder currently holds Save0104/0106/0107/0108.json.gz. None of it is copied.
  - bites: Restoring bl2_modern_backups/Save0104.sav.3 pairs a three-launches-old .sav with today's Save0104.json.gz. The item ids in the restored save will not match the sidecar, so the exact deletion this feature was written to survive happens on the restore. The module docstring names the reason ('Several components this pack bundles carry live save-corruption reports, so this runs before any of them') without noticing that the component in question stores half the save somewhere else. Rotating the matching .json.gz alongside each .sav is the same _rotate call with a second path.

- **[wrong_in_an_edge_case]** features/savebackup.py:44-52 — 'oldest.unlink()', then the shift loop, then 'shutil.copy2(save, newest)'
  - Destroys before it creates. The oldest backup is deleted and .1-.4 are shifted up before the new copy is written.
  - bites: If copy2 raises (disk full, the file locked by Steam Cloud sync, antivirus), .5 is already gone, .1 is now missing, and the exception escapes the generator at :76 so none of the remaining saves get backed up either. The next launch sees no .1, rotates again, and eats another generation. Two failed launches cost two real backups. Copy first to a .part then rotate, or copy into .1 only after the shift has succeeded.

- **[wrong_in_an_edge_case]** features/savebackup.py:52 'shutil.copy2(save, newest)'
  - The .1 copy is written in place, non-atomically.
  - bites: A crash or a taskkill mid-copy leaves a truncated file at .1. On the next launch _same_bytes (:30) compares it, finds it different, and promotes the truncated file into .2 — a corrupt backup laundered into the history where it will look like a real generation forever. bridge._reply already demonstrates the fix in this codebase (bridge.py:75-77: write .part, then replace).

- **[wrong_in_an_edge_case]** features/savebackup.py:62 'accounts = [p for p in root.iterdir() if p.is_dir() and p.name.isdigit()]' and :66-70
  - Any second numeric folder under SaveData turns the whole feature off, and the only signal is a logging.warning nobody reads.
  - bites: This pack is explicitly for two people; a second Steam account, a family-share profile, or a leftover folder silently disables save protection while the pack keeps reporting '15 of 15 loaded'. The refusal to guess is right; the silence is not. Surfacing it through status_line (core.py:196-203) or ui_utils.show_hud_message would cost one line, and the condition is trivially testable by monkeypatching savedata_dir.

- **[wrong_in_an_edge_case]** features/savebackup.py — nothing in the file, and bl2-mcp/tools/restore-saves.sh
  - There is no restore path anywhere. The backups are named Save0104.sav.3, which the game does not load, and the only restore tool on the machine copies from a completely different folder ('BACKUP-saves-before-overnight-testing') and has never heard of bl2_modern_backups.
  - bites: The feature's promise ends at 'copies exist'. In the moment it matters, a panicking person has to work out the naming scheme, guess which generation predates the corruption, and remember the SanitySaver sidecar. A ten-line restore helper (or even a README dropped into the backups folder naming the mtime of each generation) is the difference between a backup and a pile of files.

- **[cosmetic]** features/savebackup.py:30 'return a.stat().st_size == b.stat().st_size and a.read_bytes() == b.read_bytes()'
  - Both files are read fully on every launch for every save whose size is unchanged.
  - bites: Harmless at today's sizes (4 saves, 0.3 MB total per unrealsdk.log:24) but it runs on the mod-load thread at :89 during startup, and BL2 saves keep a lot of fixed-width fields so a size match with different content is the common case, not the rare one. Comparing st_mtime_ns first would skip nearly all of it.

- **[cosmetic]** features/savebackup.py:77 'total_mb = sum(...)' and :82-86
  - The size warning is computed after the copies have already been written.
  - bites: The check can only ever tell you the folder is too big once it already is. Deliberate per the ponytail note at :24-26 ('a flat warning, not a cleanup'), and I agree with not auto-deleting — but the warning currently fires into a log file, which means in practice it fires nowhere. Backups exist for ten characters (Save0000, Save0100-0108) while only four saves are live, so the growth path is real.
