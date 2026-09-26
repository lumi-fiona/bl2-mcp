# sampler.py: external sampling profiler for Borderlands2.exe

It samples one thread of the 32-bit game from outside. For each sample it suspends the thread,
reads EIP/EBP/ESP (Wow64GetThreadContext on 64-bit Python, GetThreadContext on 32-bit Python),
copies up to 32 KB of stack, and resumes the thread. Resume always runs in a `finally`. It never
writes to the game's memory. The EBP-chain walk (up to 16 frames) happens after the thread has
resumed, on the copied stack.

```
python sampler.py --dry-run                      # attach, show the top 5 threads by CPU, take no samples
python sampler.py --label town --functions       # 60 s at 200 Hz on the busiest thread
python sampler.py --tid 1234 --duration 20 --hz 500
python sampler.py --analyze runs/<dir> --functions   # re-summarize a finished run offline (no attach)
```

Other flags: `--process NAME` (default `Borderlands2.exe`) and `--pid N`. Ctrl+C or Ctrl+Break
stops the run between samples, and the summary is still written.

Each run goes to `runs/<timestamp>[-label]/`:
- `samples.jsonl`: one line per sample, `{tid, t, eip, stack:[return addrs], sus_us}`
- `modules.json`: module bases, sizes, and paths, plus the run metadata and the thread table
- `summary.txt`: suspend-window cost, idle %, per-module share, module groups (python, unrealsdk,
  PhysX, d3d9/dxvk, GFx, kernel/ntdll), top 40 exclusive and top 40 inclusive exe RVAs in 0x40
  buckets, and, with `--functions`, the hot RVAs grouped by guessed function start

Things to know when reading the summary:
- **Thread choice.** The default is the thread with the most CPU over a 1 s pre-sample. The table
  shows each thread's start address and flags the first-created thread, which is the process main
  thread and, in UE3, the game thread. If the render thread is busier, pass the game thread with `--tid`.
- **Idle.** A sample counts as idle when EIP sits in an ntdll/win32u export whose name looks like a
  wait (`Wait|Delay|Sleep|RemoveIoCompletion|GetMessage|...`). Idle samples are left out of the
  "busy" percentages.
- **Inclusive** counts are unreliable. Frames come from the EBP chain, which breaks at any function
  compiled without a frame pointer. The walk stops at the first frame that looks wrong.
- **`--functions` is a heuristic.** It scans backwards through the exe on disk to the nearest
  `55 8B EC` prologue, or to a 16-aligned byte just after `CC` padding. A function built without a
  frame pointer can be credited to the previous function. Check any result in a disassembler.
- **Cost.** Each sample stalls the game thread for about 50-70 us: a 64-bit host measured
  51 us median and 99 us p99 on a stand-in. At 200 Hz that is roughly 1% of the thread's time.
  32-bit Python is slower (about 70 us), so use the default 64-bit `python`.
