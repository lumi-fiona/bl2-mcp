# Feature registry list

Source file: `D:/SteamLibrary/steamapps/common/Borderlands 2/sdk_mods/bl2_modern/features/__init__.py`

**Purpose.** Names the fifteen feature modules and fixes their load order, with savebackup first so every later feature runs on a machine whose saves are already copied.

## Claims

### 1. savebackup is first, so everything after it runs on a backed-up machine.

- proven today: **partly**
- evidence: features/__init__.py:23 is literally "savebackup", and unrealsdk.log:24 shows its line at 11:25:39.188 ahead of every other bl2_modern line. One observed launch.
- reachable: filesystem_only
- missing capability: (none)

**How to prove it:**

assert FEATURES[0] == 'savebackup' — plus the log-ordering assert listed under the savebackup feature.

### 2. Every name in FEATURES resolves to a module that imports cleanly.

- proven today: **yes**
- evidence: unrealsdk.log:26 and :83 both read 'Second Wind 0.17.0 - 15 of 15 loaded' with no FAILED suffix, which core.status_line (core.py:200-202) only prints when len(broken) == 0.
- reachable: filesystem_only
- missing capability: (none)

**How to prove it:**

Parse unrealsdk.log for the last 'Second Wind .* loaded' line; assert it matches r'(\d+) of \1 loaded' and does not contain 'FAILED'.

### 3. Nothing is missing from the list by accident.

- proven today: **no**
- evidence: (none)
- reachable: filesystem_only
- missing capability: (none)

**How to prove it:**

orphans = {p.stem for p in Path('features').glob('*.py')} - set(FEATURES) - {'__init__'}; assert orphans == {'cleanmenu', 'fastboot'} — i.e. pin the two deliberate exclusions so a third one cannot appear silently.

### 4. cleanmenu and fastboot are excluded deliberately and their exclusion is visible.

- proven today: **partly**
- evidence: The comment at features/__init__.py:12-20 states it and gives the reason (the menu became unusable, and a screenshot showed a clean menu every time it was broken). The files still exist on disk (features/cleanmenu.py, features/fastboot.py).
- reachable: filesystem_only
- missing capability: (none)

**How to prove it:**

Same orphans assert as above; it fails loudly the day someone adds a feature file and forgets the list, which is otherwise indistinguishable from a typo.

## Suspected bugs

- **[cosmetic]** features/__init__.py:22-38 FEATURES, versus the files present in features/
  - A feature file that exists but was never added to FEATURES loads as nothing, and status_line still reports 'N of N loaded' because _features only ever contains what load_features was asked for (core.py:109-115, :199-202).
  - bites: '15 of 15 loaded' is true and useless — it counts the list against itself. cleanmenu.py and fastboot.py sit on disk today looking exactly like a forgotten sixteenth feature would. The three-line orphans check above turns a silent omission into a log line.
