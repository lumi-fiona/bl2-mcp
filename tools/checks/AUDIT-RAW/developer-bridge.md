# Developer bridge

Source file: `D:/SteamLibrary/steamapps/common/Borderlands 2/sdk_mods/bl2_modern/features/bridge.py`

**Purpose.** Lets Claude run arbitrary Python inside the live game by dropping a file in data/bridge/, and reads the printed output back out of another file, so questions about the game get looked up instead of guessed.

## Claims

### 1. Python written to data/bridge/request.py is executed inside the running game process.

- proven today: **partly**
- evidence: Binaries/Win32/Plugins/unrealsdk.log lines 42-86: 22 separate 'bridge.py@108 INFO| bridge: served request N, X characters back' entries on 2026-08-19. That is a human/agent driving it, not a check. regress.py contains zero bridge assertions (its 14 results are all grinder/levelless, regress.py:28-94).
- reachable: filesystem_only
- missing capability: (none)

**How to prove it:**

From outside: write 'import unrealsdk; print("PID-PROOF", len(list(unrealsdk.find_all("WillowPlayerController"))))' to data/bridge/request.py; poll data/bridge/response.txt for <=15s; assert resp.startswith('--- request ') and 'PID-PROOF' in resp and int(resp.split('PID-PROOF')[1].split()[0]) >= 1

### 2. The request runs exactly once — request.py is unlinked before exec, so a request that crashes the game is not replayed on the next launch.

- proven today: **no**
- evidence: (none)
- reachable: filesystem_only
- missing capability: (none)

**How to prove it:**

Write 'raise SystemExit' to request.py. Within 2s assert not Path('data/bridge/request.py').exists(). Then read heartbeat.txt, wait 15s, read again, assert the 'N requests served' number advanced by exactly 1 and never again.

### 3. response.txt is never observed half-written (written to .part then atomically replaced, bridge.py:74-77).

- proven today: **no**
- evidence: (none)
- reachable: filesystem_only
- missing capability: (none)

**How to prove it:**

Send 'print("X"*8_000_000)'. From outside, spin reading response.txt as fast as possible for the whole window; assert every successful read either is the previous generation's text or is len>=8_000_020 and ends with '\n'; assert Path('data/bridge/response.part').exists() is False at the end.

### 4. Whatever the request prints to stdout comes back in response.txt.

- proven today: **partly**
- evidence: data/bridge/response.txt as read 2026-08-19 13:08 contained printed section headers and a function list ('=== what movies are up right now ==='), so stdout capture works. No assert anywhere.
- reachable: filesystem_only
- missing capability: (none)

**How to prove it:**

Send 'print("MARKER-42")'; assert 'MARKER-42' in response.txt

### 5. An exception inside the request does not take the game down, and the traceback comes back.

- proven today: **no**
- evidence: (none)
- reachable: filesystem_only
- missing capability: (none)

**How to prove it:**

Send '1/0'; assert '--- it raised ---' in resp and 'ZeroDivisionError' in resp. Immediately send 'print("ALIVE")'; assert 'ALIVE' in the next resp within 15s.

### 6. State survives between requests, so one request can build something the next uses (_scope, bridge.py:68).

- proven today: **no**
- evidence: (none)
- reachable: filesystem_only
- missing capability: (none)

**How to prove it:**

Send 'BRIDGE_PROBE = 7'. Then send 'print(BRIDGE_PROBE)'; assert '7' in the second response and 'NameError' not in it.

### 7. heartbeat.txt ticks up on its own, so 'is the game running this' is answerable without sending a request.

- proven today: **partly**
- evidence: Measured by me 2026-08-19 13:26:16-13:26:30, reading the file only: 'alive, 1800 ticks' -> 'alive, 2700 ticks', monotonic. Manual observation, no automated check.
- reachable: filesystem_only
- missing capability: (none)

**How to prove it:**

t0=heartbeat ticks and os.path.getmtime; sleep 15; t1=same; assert t1_ticks > t0_ticks and (time.time() - t1_mtime) < 15

### 8. The heartbeat is written 'roughly every three seconds' (bridge.py:127).

- proven today: **no**
- evidence: Measured false: 900 ticks elapsed between 13:26:16.108 and 13:26:25.851 = 9.7s per heartbeat, ~98 ticks/s not the 264 assumed at bridge.py:58-60.
- reachable: filesystem_only
- missing capability: (none)

**How to prove it:**

Sample heartbeat.txt every 0.25s for 30s, record the wall time of each content change; assert max gap < 4.0 seconds

### 9. Polling the filesystem every 30th PlayerTick costs the game nothing measurable.

- proven today: **no**
- evidence: (none)
- reachable: bridge_only
- missing capability: (none)

**How to prove it:**

Send a request that runs: import time,statistics; from pathlib import Path; p=Path(r'...data/bridge/request.py'); s=[ (lambda t: time.perf_counter()-t)(time.perf_counter()) for _ in range(0)]; better: ts=[]; [ (t:=time.perf_counter(), p.is_file(), ts.append(time.perf_counter()-t)) for _ in range(500)]; print(statistics.median(ts)*1000); assert median_ms < 0.2

### 10. Turning the 'Developer bridge' option off switches the whole thing off.

- proven today: **no**
- evidence: (none)
- reachable: filesystem_only
- missing capability: (none)

**How to prove it:**

Send 'from bl2_modern.features import bridge as B; B.enabled.value=False'. Record heartbeat ticks; sleep 20; assert ticks unchanged. Write a new request; assert no response.txt appears in 20s. Then flip it back via the mods menu (this cannot be undone through the bridge once off — note that in the test).

### 11. With the option off, the feature stops touching disk entirely ('Turn it off before calling the pack finished', bridge.py:26).

- proven today: **no**
- evidence: (none)
- reachable: needs_input
- missing capability: loading a character needs a keypress at the title screen; bl2-mcp/server.py:138-140 says that steals focus. Automatable only when Lumi is away.

**How to prove it:**

Set enabled.value=False, delete response.txt, load a character (which fires apply_all -> _ready), assert response.txt was NOT recreated. Expected to FAIL: _ready (bridge.py:141-148) has no enabled guard.

### 12. Nothing listens on the network; the only thing that can reach it is a local file inside the mod's folder.

- proven today: **no**
- evidence: (none)
- reachable: filesystem_only
- missing capability: (none)

**How to prove it:**

Static: assert not re.search(r'\b(socket|http|urllib|requests|asyncio)\b', Path('features/bridge.py').read_text()). Dynamic: send "import socket,gc; print([o for o in gc.get_objects() if isinstance(o, socket.socket)])" and assert the list is empty.

### 13. The file the bridge reads is the whole file the caller wrote.

- proven today: **no**
- evidence: (none)
- reachable: filesystem_only
- missing capability: (none)

**How to prove it:**

Loop 200 times: write a 200 KB request whose last line is 'print("TAIL-OK")' using a plain non-atomic write (the way server.py:80 does it), poll for the response, assert 'TAIL-OK' in every one of the 200 responses and 'SyntaxError' in none.

## Suspected bugs

- **[breaks_the_feature]** features/bridge.py:141-148 (_ready), reached from core.py:180-193 (apply_all) via __init__.py:39 register_save_options(..., on_load=apply_all) and save_options/hooks.py:168 load_player_save_game
  - _ready() does 'REQUEST.unlink(missing_ok=True)' and '_reply("bridge ready, no request yet\n")'. Because the feature is writes_game_data=True with apply=_ready, this runs at the main menu AND again on every character load. An in-flight request is deleted and response.txt is overwritten with 'bridge ready, no request yet'.
  - bites: Both callers return the first response.txt they see — bl2-mcp/tools/ask.sh line 'cat "$B/response.txt"; exit 0' and server.py:85-87. So the caller silently gets 'bridge ready, no request yet' as the ANSWER to a real question. This is not theoretical: unrealsdk.log shows 'served request 20' at 11:29:46.004 and 'bridge: watching ...' (_ready, bridge.py@148) at 11:29:47.148 — 1.14s apart, inside the poll window. Worse, tools/load.sh polls via ask.sh WHILE a character loads, which is exactly when _ready fires. The unlink+_reply in _ready earn nothing (_serve already unlinks before exec, bridge.py:91) and cost this race — delete both lines.

- **[wrong_in_an_edge_case]** features/bridge.py:86-91 (_serve reads then unlinks), against bl2-mcp/server.py:80 'REQUEST.write_text(code, encoding="utf-8")' and tools/ask.sh 'cp "$1" "$B/request.py"'
  - No caller writes the request atomically, and _serve treats REQUEST.is_file() as 'complete'. is_file() becomes true the instant open(...,'w') truncates the file, before a single byte is written.
  - bites: The bridge can exec a truncated script and then unlink it, so the rest is gone forever. Best case a SyntaxError that reads like the game rejected the code; worst case a partially valid script that half-executes a mutation. Fix is one line on each caller: write request.py.part then os.replace — the same trick _reply already uses at bridge.py:75-77.

- **[breaks_the_feature]** features/bridge.py:129-134 writes heartbeat.txt; nothing ever deletes it. bl2-mcp/server.py:144 'LOG.unlink(missing_ok=True)' and :156 'if HEARTBEAT.is_file(): return "running, bridge alive..."'
  - heartbeat.txt is never removed and carries no timestamp, only a tick count. game_launch deletes the SDK log but not the heartbeat, then waits for HEARTBEAT.is_file() as its proof the bridge came up.
  - bites: On any machine that has ever run the bridge once — including this one right now — game_launch(steal_focus=False) returns 'running, bridge alive, sitting on the title screen' on its very first 3-second poll, roughly 4 minutes before the mod is actually serving (unrealsdk.log: process start 11:25:31, first served request 11:26:13). Every eval that follows then fails for no visible reason. Same hole in the timeout message at server.py:91-96, which tells the reader to judge whether the heartbeat is 'stale' from a string that contains no clock.

- **[cosmetic]** features/bridge.py:58-61 '# PlayerTick runs once a frame, which at 264 frames a second ... Every 30th is about nine checks a second' and :127 '# Roughly every three seconds'
  - Both numbers are wrong on the live machine. Measured by reading heartbeat.txt only, 2026-08-19 13:26:16.108 -> 13:26:25.851: 900 ticks in 9.74s = ~92 ticks/s, so EVERY=30 gives ~3 checks/s and the heartbeat lands every ~9.7s, not ~3s.
  - bites: The 3-second figure is what server.py:91-96 and ask.sh implicitly trust when they treat a heartbeat as fresh, and the ~0.33s poll interval is three times the assumed latency for every request. Nothing breaks, but every timing decision downstream is built on a number that is 2.8x off.

- **[wrong_in_an_edge_case]** features/bridge.py:63 '_counter = 0' / :151-159 register(...), with two Borderlands2.exe processes observed live (tasklist 2026-08-19 13:25: PIDs 8520 and 32980)
  - The bridge has no instance identity. Every game process watches the same request.py and writes the same response.txt and heartbeat.txt. Whichever process's tick lands first unlinks the request and answers it.
  - bites: With two instances up, a request is answered by a random one of the two games and the other's heartbeat/_ready overwrites the shared files. There is no PID in the heartbeat to tell them apart, so the caller cannot even detect it. Putting os.getpid() in the heartbeat line is one line and makes the condition visible.

- **[cosmetic]** features/bridge.py:101 'with contextlib.redirect_stdout(captured):'
  - Only sys.stdout is captured. unrealsdk.logging.info/error output and sys.stderr are not.
  - bites: A request written in the pack's own idiom (the rest of the codebase logs with unrealsdk.logging, e.g. savebackup.py:79) returns an empty body, which reads as 'the code did nothing' rather than 'look in unrealsdk.log'. Adding contextlib.redirect_stderr(captured) alongside it is a one-line fix for half of it.

- **[wrong_in_an_edge_case]** features/bridge.py:100-106 — exec with no timeout, on the hook thread
  - A request containing an infinite loop or a blocking call freezes the game thread permanently, and request.py has already been unlinked at line 91 so there is nothing left to inspect afterwards.
  - bites: The only recovery is taskkill, which loses the session. Acceptable for a stated non-sandbox, but the response file gets no 'started request N' marker before exec, so from outside a hang is indistinguishable from a crash, a stale heartbeat, or the game not running.

- **[cosmetic]** features/bridge.py:103 'except Exception:'
  - BaseException subclasses (SystemExit, KeyboardInterrupt, and anything pyunrealsdk raises that is not an Exception) escape _serve and propagate into the PlayerTick hook.
  - bites: The comment on that line says 'a failed request must never take the game down', which is exactly what a bare 'except Exception' does not guarantee. 'except BaseException' is the same number of characters.
