"""External sampling profiler for a 32-bit (WOW64) process, aimed at Borderlands2.exe.

Read-only: suspends one thread, reads its context and a slice of its stack,
resumes. Never writes to the target. See README.md.
"""
import argparse, bisect, ctypes, fnmatch, json, os, re, signal, struct, sys, time
from collections import Counter, defaultdict
from ctypes import wintypes as W
from datetime import datetime
from pathlib import Path

HOST64 = struct.calcsize("P") == 8
k32 = ctypes.WinDLL("kernel32", use_last_error=True)
ntdll = ctypes.WinDLL("ntdll")

PROCESS_QUERY_INFORMATION, PROCESS_VM_READ = 0x0400, 0x0010
THREAD_SUSPEND_RESUME, THREAD_GET_CONTEXT, THREAD_QUERY_INFORMATION = 0x0002, 0x0008, 0x0040
CONTEXT_i386_CONTROL = 0x00010001  # WOW64_CONTEXT_i386|CONTROL == CONTEXT_i386|CONTROL: Ebp, Eip, Esp
LIST_MODULES_32BIT = 1
STACK_SNAPSHOT = 32 * 1024  # ponytail: frames past ESP+32K are dropped; raise if walks end early
MAX_FRAMES = 16
BUCKET = 0x40
SYS32 = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32\\").lower()
SYSWOW = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "SysWOW64\\")
WOW_OS = os.path.isdir(SYSWOW)


class FILETIME(ctypes.Structure):
    _fields_ = [("lo", W.DWORD), ("hi", W.DWORD)]
    def v(self): return self.hi << 32 | self.lo


class CONTEXT32(ctypes.Structure):  # WOW64_CONTEXT, identical to the x86 CONTEXT
    _fields_ = [("ContextFlags", W.DWORD), ("Dr", W.DWORD * 6), ("FloatSave", ctypes.c_byte * 112),
                ("Seg", W.DWORD * 4), ("Edi", W.DWORD), ("Esi", W.DWORD), ("Ebx", W.DWORD),
                ("Edx", W.DWORD), ("Ecx", W.DWORD), ("Eax", W.DWORD), ("Ebp", W.DWORD),
                ("Eip", W.DWORD), ("SegCs", W.DWORD), ("EFlags", W.DWORD), ("Esp", W.DWORD),
                ("SegSs", W.DWORD), ("ExtendedRegisters", ctypes.c_byte * 512)]
assert ctypes.sizeof(CONTEXT32) == 716


class THREADENTRY32(ctypes.Structure):
    _fields_ = [("dwSize", W.DWORD), ("cntUsage", W.DWORD), ("th32ThreadID", W.DWORD),
                ("th32OwnerProcessID", W.DWORD), ("tpBasePri", W.LONG), ("tpDeltaPri", W.LONG), ("dwFlags", W.DWORD)]


class PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [("dwSize", W.DWORD), ("cntUsage", W.DWORD), ("th32ProcessID", W.DWORD),
                ("th32DefaultHeapID", ctypes.c_size_t), ("th32ModuleID", W.DWORD), ("cntThreads", W.DWORD),
                ("th32ParentProcessID", W.DWORD), ("pcPriClassBase", W.LONG), ("dwFlags", W.DWORD),
                ("szExeFile", W.WCHAR * 260)]


class MODULEINFO(ctypes.Structure):
    _fields_ = [("base", ctypes.c_void_p), ("size", W.DWORD), ("entry", ctypes.c_void_p)]


class MBI(ctypes.Structure):  # MEMORY_BASIC_INFORMATION (native layout)
    _fields_ = [("BaseAddress", ctypes.c_void_p), ("AllocationBase", ctypes.c_void_p), ("AllocationProtect", W.DWORD),
                ("PartitionId", W.WORD), ("RegionSize", ctypes.c_size_t), ("State", W.DWORD),
                ("Protect", W.DWORD), ("Type", W.DWORD)]


def _fn(dll, name, res, *args):
    f = getattr(dll, name); f.restype, f.argtypes = res, list(args); return f

H = W.HANDLE
OpenProcess = _fn(k32, "OpenProcess", H, W.DWORD, W.BOOL, W.DWORD)
OpenThread = _fn(k32, "OpenThread", H, W.DWORD, W.BOOL, W.DWORD)
CloseHandle = _fn(k32, "CloseHandle", W.BOOL, H)
Snapshot = _fn(k32, "CreateToolhelp32Snapshot", H, W.DWORD, W.DWORD)
Thread32First = _fn(k32, "Thread32First", W.BOOL, H, ctypes.POINTER(THREADENTRY32))
Thread32Next = _fn(k32, "Thread32Next", W.BOOL, H, ctypes.POINTER(THREADENTRY32))
Process32First = _fn(k32, "Process32FirstW", W.BOOL, H, ctypes.POINTER(PROCESSENTRY32W))
Process32Next = _fn(k32, "Process32NextW", W.BOOL, H, ctypes.POINTER(PROCESSENTRY32W))
IsWow64Process = _fn(k32, "IsWow64Process", W.BOOL, H, ctypes.POINTER(W.BOOL))
GetThreadTimes = _fn(k32, "GetThreadTimes", W.BOOL, H, *[ctypes.POINTER(FILETIME)] * 4)
SuspendThread = _fn(k32, "SuspendThread", W.DWORD, H)
ResumeThread = _fn(k32, "ResumeThread", W.DWORD, H)
GetThreadCtx = _fn(k32, "Wow64GetThreadContext" if HOST64 else "GetThreadContext", W.BOOL, H, ctypes.POINTER(CONTEXT32))
ReadProcessMemory = _fn(k32, "ReadProcessMemory", W.BOOL, H, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t))
VirtualQueryEx = _fn(k32, "VirtualQueryEx", ctypes.c_size_t, H, ctypes.c_void_p, ctypes.POINTER(MBI), ctypes.c_size_t)
EnumProcessModulesEx = _fn(k32, "K32EnumProcessModulesEx", W.BOOL, H, ctypes.POINTER(ctypes.c_void_p), W.DWORD, ctypes.POINTER(W.DWORD), W.DWORD)
GetModuleFileNameEx = _fn(k32, "K32GetModuleFileNameExW", W.DWORD, H, ctypes.c_void_p, W.LPWSTR, W.DWORD)
GetModuleInformation = _fn(k32, "K32GetModuleInformation", W.BOOL, H, ctypes.c_void_p, ctypes.POINTER(MODULEINFO), W.DWORD)
GetThreadDescription = _fn(k32, "GetThreadDescription", ctypes.c_long, H, ctypes.POINTER(W.LPWSTR))
LocalFree = _fn(k32, "LocalFree", ctypes.c_void_p, ctypes.c_void_p)
SetThreadPriority = _fn(k32, "SetThreadPriority", W.BOOL, H, ctypes.c_int)
GetCurrentThread = _fn(k32, "GetCurrentThread", H)
NtQueryInformationThread = _fn(ntdll, "NtQueryInformationThread", ctypes.c_long, H, ctypes.c_int, ctypes.c_void_p, W.ULONG, ctypes.c_void_p)


def die(msg): sys.exit(f"error: {msg}")


def winerr(what): return f"{what} failed: {ctypes.WinError(ctypes.get_last_error()).strerror}"


def find_pid(name):
    snap = Snapshot(0x2, 0); e = PROCESSENTRY32W(dwSize=ctypes.sizeof(PROCESSENTRY32W)); pids = []
    ok = Process32First(snap, ctypes.byref(e))
    while ok:
        if e.szExeFile.lower() == name.lower(): pids.append(e.th32ProcessID)
        ok = Process32Next(snap, ctypes.byref(e))
    CloseHandle(snap)
    if not pids: die(f"{name} is not running")
    if len(pids) > 1: die(f"several {name} processes {pids}; pick one with --pid")
    return pids[0]


def list_tids(pid):
    snap = Snapshot(0x4, 0); e = THREADENTRY32(dwSize=ctypes.sizeof(THREADENTRY32)); tids = []
    ok = Thread32First(snap, ctypes.byref(e))
    while ok:
        if e.th32OwnerProcessID == pid: tids.append(e.th32ThreadID)
        ok = Thread32Next(snap, ctypes.byref(e))
    CloseHandle(snap)
    return tids


def list_modules(hp):
    arr = (ctypes.c_void_p * 2048)(); need = W.DWORD()
    if not EnumProcessModulesEx(hp, arr, ctypes.sizeof(arr), ctypes.byref(need), LIST_MODULES_32BIT): return []
    mods, buf = [], ctypes.create_unicode_buffer(1024)
    for base in arr[:need.value // ctypes.sizeof(ctypes.c_void_p)]:
        mi = MODULEINFO()
        if GetModuleInformation(hp, base, ctypes.byref(mi), ctypes.sizeof(mi)) and GetModuleFileNameEx(hp, base, buf, 1024):
            path = buf.value  # the target is 32-bit, so a "System32" DLL is really the SysWOW64 copy on disk
            if WOW_OS and path.lower().startswith(SYS32): path = SYSWOW + path[len(SYS32):]
            mods.append({"base": mi.base, "size": mi.size, "path": path})
    return mods  # first entry is the main exe


class ModMap:
    def __init__(self, mods):
        self.mods = sorted(mods, key=lambda m: m["base"]); self.bases = [m["base"] for m in self.mods]
    def find(self, addr):
        i = bisect.bisect_right(self.bases, addr) - 1
        if i >= 0 and addr < self.bases[i] + self.mods[i]["size"]: return self.mods[i]
    def name(self, addr):
        m = self.find(addr); return os.path.basename(m["path"]) if m else "?"


def thread_info(tid):
    """(cpu_100ns, creation, description, start_addr) with query rights only."""
    ht = OpenThread(THREAD_QUERY_INFORMATION, False, tid)
    if not ht: return None
    try:
        c, e, k, u = FILETIME(), FILETIME(), FILETIME(), FILETIME()
        if not GetThreadTimes(ht, c, e, k, u): return None
        desc, p = "", W.LPWSTR()
        if GetThreadDescription(ht, ctypes.byref(p)) >= 0 and p:
            desc = p.value or ""; LocalFree(p)
        start = ctypes.c_void_p()  # ThreadQuerySetWin32StartAddress
        NtQueryInformationThread(ht, 9, ctypes.byref(start), ctypes.sizeof(start), None)
        return k.v() + u.v(), c.v(), desc, start.value or 0
    finally:
        CloseHandle(ht)


def presample(pid, mm):
    tids = list_tids(pid); a = {t: thread_info(t) for t in tids}
    time.sleep(1.0)
    rows = []
    for t in list_tids(pid):
        b = thread_info(t)
        if b and a.get(t): rows.append((b[0] - a[t][0], t, b[1], b[2], b[3]))
    if not rows: die("could not query any thread (access denied?)")
    first = min(rows, key=lambda r: r[2])[1]
    rows.sort(reverse=True)
    lines = [f"{len(rows)} threads; top 5 by CPU over 1 s:"]
    for d, t, _, desc, start in rows[:5]:
        m = mm.find(start); where = f"{os.path.basename(m['path'])}+0x{start - m['base']:X}" if m else f"0x{start:X}"
        tag = " [first-created = process main thread]" if t == first else ""
        lines.append(f"  tid {t:>6}  {d / 1e5:5.1f}% cpu  start {where}{'  ' + repr(desc) if desc else ''}{tag}")
    if first not in [r[1] for r in rows[:5]]: lines.append(f"  (first-created thread is tid {first})")
    return rows[0][1], "\n".join(lines)


class Sampler:
    def __init__(self, hp, tid):
        self.hp = hp
        self.ht = OpenThread(THREAD_SUSPEND_RESUME | THREAD_GET_CONTEXT | THREAD_QUERY_INFORMATION, False, tid)
        if not self.ht: die(winerr(f"OpenThread({tid})"))
        self.ctx = CONTEXT32(); self.buf = ctypes.create_string_buffer(STACK_SNAPSHOT)
        self.got = ctypes.c_size_t(); self.stack_top = 0

    def _stack_top(self, esp):
        mbi = MBI()
        if VirtualQueryEx(self.hp, esp, ctypes.byref(mbi), ctypes.sizeof(mbi)):
            self.stack_top = mbi.BaseAddress + mbi.RegionSize

    def sample(self):
        """Returns (eip, ebp, esp, stack_bytes) or None; the thread is suspended only inside the try."""
        ctx = self.ctx; ctx.ContextFlags = CONTEXT_i386_CONTROL
        if SuspendThread(self.ht) == 0xFFFFFFFF: raise OSError(winerr("SuspendThread"))
        try:
            if not GetThreadCtx(self.ht, ctypes.byref(ctx)): return None
            esp = ctx.Esp
            n = min(STACK_SNAPSHOT, self.stack_top - esp) if esp < self.stack_top else 0
            ok = n > 0 and ReadProcessMemory(self.hp, esp, self.buf, n, ctypes.byref(self.got))
        finally:
            ResumeThread(self.ht)
        if not ok:  # stack region not known yet (or moved); look it up with the thread running
            self._stack_top(esp)
            return ctx.Eip, ctx.Ebp, esp, b""
        return ctx.Eip, ctx.Ebp, esp, self.buf.raw[:self.got.value]


def walk(ebp, esp, stack, mm):
    """EBP chain inside the snapshot. Unreliable by nature: stops at the first frame that looks wrong."""
    out = []
    while len(out) < MAX_FRAMES:
        off = ebp - esp
        if ebp & 3 or off < 0 or off + 8 > len(stack): break
        nxt, ret = struct.unpack_from("<II", stack, off)
        if not mm.find(ret): break
        out.append(ret)
        if nxt <= ebp: break
        ebp = nxt
    return out


# ---------- PE helpers (on-disk image) ----------
class PE:
    def __init__(self, path):
        d = self.d = Path(path).read_bytes()
        pe = struct.unpack_from("<I", d, 0x3C)[0]
        ns, so = struct.unpack_from("<H", d, pe + 6)[0], struct.unpack_from("<H", d, pe + 20)[0]
        self.opt = pe + 24; self.secs = []
        if struct.unpack_from("<H", d, self.opt)[0] != 0x10B: raise OSError(f"{path}: not a 32-bit PE")
        for i in range(ns):
            o = self.opt + so + 40 * i
            vs, va, rs, rp = struct.unpack_from("<4I", d, o + 8)
            self.secs.append((va, max(vs, rs), rp, rs, struct.unpack_from("<I", d, o + 36)[0]))
    def off(self, rva, code=False):
        for va, vs, rp, rs, ch in self.secs:
            if va <= rva < va + min(vs, rs) and (not code or ch & 0x20000000): return rp + rva - va
    def exports(self):
        rva, size = struct.unpack_from("<II", self.d, self.opt + 96)  # PE32 data dir 0
        o = self.off(rva)
        if not size or o is None: return []
        nf, nn, af, an, ao = struct.unpack_from("<5I", self.d, o + 20)
        funcs = struct.unpack_from(f"<{nf}I", self.d, self.off(af))
        out = []
        for i in range(nn):
            no = self.off(struct.unpack_from("<I", self.d, self.off(an) + 4 * i)[0])
            name = self.d[no:self.d.index(b"\0", no)].decode()
            out.append((funcs[struct.unpack_from("<H", self.d, self.off(ao) + 2 * i)[0]], name))
        return sorted(out)


WAIT_RE = re.compile(r"Wait|Delay|Sleep|RemoveIoCompletion|Yield|GetMessage|AlertByThreadId|ReplyWaitReceive|WaitMessage", re.I)
IDLE_MODS = ("ntdll.dll", "win32u.dll")


def symbolizer(mods):
    """nearest-export name for ntdll/win32u, used only for the idle test."""
    tabs = {}
    for m in mods:
        if os.path.basename(m["path"]).lower() in IDLE_MODS:
            try: tabs[m["base"]] = PE(m["path"]).exports()
            except OSError: pass
    def sym(m, addr):
        t = tabs.get(m["base"])
        if not t: return None
        i = bisect.bisect_right(t, (addr - m["base"], "￿")) - 1
        return t[i][1] if i >= 0 else None
    return sym


def guess_start(pe, rva, limit=0x10000):
    """Heuristic function start: nearest 55 8B EC (push ebp; mov ebp,esp) or 16-aligned byte after CC padding."""
    o = pe.off(rva, code=True)
    if o is None: return None, "not-code"
    d = pe.d
    for p in range(o, max(o - limit, 1), -1):
        if d[p:p + 3] == b"\x55\x8b\xec":
            return rva - (o - p) - (2 if d[p - 2:p] == b"\x8b\xff" else 0), "push-ebp"
        if d[p - 1] == 0xCC and d[p] != 0xCC and (rva - (o - p)) % 16 == 0:
            return rva - (o - p), "after-cc"
    return None, "none"


# ---------- analysis ----------
def pct(n, d): return f"{100 * n / d:5.1f}%" if d else "  n/a"

GROUPS = [("python", ["python*.dll"]), ("unrealsdk/pyunrealsdk", ["*unrealsdk*.dll"]), ("PhysX", ["physx*.dll", "*physx*"]),
          ("d3d9/dxvk", ["d3d9*.dll", "dxgi*.dll", "*dxvk*", "d3d11*.dll", "vulkan*.dll", "nv*.dll", "amd*.dll", "ig*.dll"]),
          ("GFx", ["*gfx*"]), ("kernel/ntdll", ["ntdll.dll", "kernel32.dll", "kernelbase.dll", "win32u.dll", "user32.dll"])]


def analyze(run, functions):
    meta = json.loads((run / "modules.json").read_text())
    mods, mm = meta["modules"], ModMap(meta["modules"])
    exe = meta["modules"][0]; exe_name = os.path.basename(exe["path"]); eb, es = exe["base"], exe["size"]
    sym = symbolizer(mods)
    samples = [json.loads(l) for l in (run / "samples.jsonl").open()]
    N = len(samples)
    if not N: return "no samples"
    excl, idle_syms, busy = Counter(), Counter(), []
    for s in samples:
        m = mm.find(s["eip"]); name = os.path.basename(m["path"]) if m else "?"
        excl[name] += 1
        fn = sym(m, s["eip"]) if m and name.lower() in IDLE_MODS else None
        if fn and WAIT_RE.search(fn): idle_syms[fn] += 1
        else: busy.append(s)
    B = len(busy); idle = N - B
    in_exe = lambda a: eb <= a < eb + es
    ex_b, inc_b, ex_rva, inc_rva, depth = Counter(), Counter(), Counter(), Counter(), Counter()
    for s in busy:
        depth[len(s["stack"])] += 1
        if in_exe(s["eip"]): ex_b[(s["eip"] - eb) & ~(BUCKET - 1)] += 1; ex_rva[s["eip"] - eb] += 1
        frames = {a - eb for a in [s["eip"]] + s["stack"] if in_exe(a)}
        for r in {f & ~(BUCKET - 1) for f in frames}: inc_b[r] += 1
        for r in frames: inc_rva[r] += 1
    busy_mod = Counter(mm.name(s["eip"]) for s in busy)
    sus = sorted(s["sus_us"] for s in samples if "sus_us" in s)
    q = lambda f: sus[min(len(sus) - 1, int(f * len(sus)))] if sus else 0
    L = [f"run {run.name}   target {exe_name} pid {meta['pid']} tid {meta['tid']}   host {'64' if meta.get('host64') else '32'}-bit python",
         f"samples {N} over {meta.get('elapsed', 0):.1f}s ({meta.get('hz')} Hz requested, {N / max(meta.get('elapsed', 1), 1e-9):.0f} Hz achieved), errors {meta.get('errors', 0)}",
         f"suspended window (suspend..resume, us): median {q(.5):.1f}  p90 {q(.9):.1f}  p99 {q(.99):.1f}  max {sus[-1] if sus else 0:.1f}",
         f"idle/waiting (EIP in ntdll/win32u wait stub): {idle} = {pct(idle, N)}   busy samples {B}",
         f"stack depth (busy, frames via EBP chain): " + ", ".join(f"{d}:{c}" for d, c in sorted(depth.items())),
         "", meta.get("threads", ""), "",
         "== per-module share, exclusive (EIP) ==", f"  {'module':<34}{'all':>8}{'busy':>8}"]
    for name, c in excl.most_common():
        L.append(f"  {name:<34}{pct(c, N):>8}{pct(busy_mod[name], B):>8}")
    L += ["", "== groups (exclusive, % of all / % of busy) =="]
    for g, pats in GROUPS:
        hit = [n for n in excl if any(fnmatch.fnmatch(n.lower(), p) for p in pats)]
        a, b = sum(excl[n] for n in hit), sum(busy_mod[n] for n in hit)
        L.append(f"  {g:<24}{pct(a, N):>8}{pct(b, B):>8}  {', '.join(hit) if hit else '(not loaded / no samples)'}")
    L.append(f"  {exe_name:<24}{pct(excl[exe_name], N):>8}{pct(busy_mod[exe_name], B):>8}")
    if idle_syms:
        L += ["", "== idle wait stubs =="] + [f"  {c:>6}  {n}" for n, c in idle_syms.most_common(8)]
    L += ["", f"== top 40 exclusive RVAs in {exe_name} (0x{BUCKET:X} buckets, % of busy) =="]
    L += [f"  {exe_name}+0x{r:08X}  {c:>6}  {pct(c, B)}" for r, c in ex_b.most_common(40)]
    L += ["", f"== top 40 inclusive RVAs in {exe_name} (EIP or any walked frame; frames are return addresses) =="]
    L += [f"  {exe_name}+0x{r:08X}  {c:>6}  {pct(c, B)}" for r, c in inc_b.most_common(40)]
    if functions:
        pe = PE(exe["path"]); memo = {}
        def fstart(r):
            if r not in memo: memo[r] = guess_start(pe, r)
            return memo[r]
        for title, cnt in (("exclusive", ex_rva), ("inclusive", inc_rva)):
            grp, kinds, hot = Counter(), {}, defaultdict(Counter)
            for r, c in cnt.most_common(2000):  # ponytail: only the 2000 hottest exact RVAs get scanned
                st, kind = fstart(r)
                grp[st] += c; kinds[st] = kind; hot[st][r & ~(BUCKET - 1)] += c
            if title == "inclusive":  # one count per sample per function
                grp = Counter()
                for s in busy:
                    for st in {fstart(a - eb)[0] for a in [s["eip"]] + s["stack"] if in_exe(a)}: grp[st] += 1
            L += ["", f"== {title} by GUESSED function start (HEURISTIC: backward scan for 55 8B EC / CC padding on disk) =="]
            for st, c in grp.most_common(40):
                top = ", ".join(f"+0x{b:X}" for b, _ in hot[st].most_common(3))
                L.append(f"  {'0x%08X' % st if st is not None else '?':>10} [{kinds[st]:<8}] {c:>6}  {pct(c, B)}  hot: {top}")
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--process", default="Borderlands2.exe"); ap.add_argument("--pid", type=int)
    ap.add_argument("--tid", type=int, help="thread to sample (default: busiest over a 1 s pre-sample)")
    ap.add_argument("--duration", type=float, default=60.0); ap.add_argument("--hz", type=float, default=200.0)
    ap.add_argument("--label", default=""); ap.add_argument("--dry-run", action="store_true", help="attach, list threads, no samples")
    ap.add_argument("--functions", action="store_true", help="add heuristic function grouping to the summary")
    ap.add_argument("--analyze", metavar="RUN_DIR", help="re-summarize an existing run (no attach)")
    a = ap.parse_args()
    if a.hz <= 0 or a.duration <= 0: die("--hz and --duration must be positive")

    if a.analyze:
        run = Path(a.analyze); txt = analyze(run, a.functions)
        (run / "summary.txt").write_text(txt); print(txt); return

    pid = a.pid or find_pid(a.process)
    hp = OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, False, pid)
    if not hp: die(winerr(f"OpenProcess({pid})"))
    wow, self_wow = W.BOOL(), W.BOOL()
    IsWow64Process(hp, ctypes.byref(wow)); IsWow64Process(ctypes.c_void_p(-1), ctypes.byref(self_wow))
    if (HOST64 or self_wow.value) and not wow.value: die("target is a 64-bit process; this tool only handles 32-bit (WOW64) targets")
    mods = list_modules(hp) or die(winerr("EnumProcessModulesEx")); mm = ModMap(mods)
    busiest, threads = presample(pid, mm)
    print(f"pid {pid}  {len(mods)} modules  main module {os.path.basename(mods[0]['path'])}  host {'64' if HOST64 else '32'}-bit\n{threads}")
    tid = a.tid or busiest
    if tid not in list_tids(pid): die(f"tid {tid} is not a thread of pid {pid}")
    if a.dry_run: print(f"dry run: would sample tid {tid}"); return

    stop = []
    for sig in (signal.SIGINT, signal.SIGBREAK):  # Ctrl+C / Ctrl+Break end the loop between samples, never mid-suspend
        signal.signal(sig, lambda *_: stop.append(1))
    run = Path(__file__).parent / "runs" / (datetime.now().strftime("%Y%m%d-%H%M%S") + (f"-{a.label}" if a.label else ""))
    run.mkdir(parents=True)
    smp = Sampler(hp, tid); period = 1.0 / a.hz; errors = n = 0
    SetThreadPriority(GetCurrentThread(), 2)  # HIGHEST: less chance of being preempted while the target is suspended
    print(f"sampling tid {tid} at {a.hz:g} Hz for {a.duration:g}s -> {run}")
    t0 = time.perf_counter(); nxt = t0; end = t0 + a.duration
    with (run / "samples.jsonl").open("w") as f:
        while not stop and (now := time.perf_counter()) < end:
            if nxt > now: time.sleep(nxt - now)
            nxt = max(nxt + period, time.perf_counter())
            t1 = time.perf_counter_ns()
            try: r = smp.sample()
            except OSError as e: print(f"stopping: {e}"); break
            sus = (time.perf_counter_ns() - t1) / 1000
            if r is None: errors += 1; continue
            eip, ebp, esp, stack = r
            f.write(json.dumps({"tid": tid, "t": round(time.perf_counter() - t0, 5), "eip": eip,
                                "stack": walk(ebp, esp, stack, mm), "sus_us": round(sus, 1)}) + "\n"); n += 1
    elapsed = time.perf_counter() - t0
    by_base = {m["base"]: m for m in mods + list_modules(hp)}  # union: modules loaded mid-run
    mods = [mods[0]] + [m for b, m in by_base.items() if b != mods[0]["base"]]
    (run / "modules.json").write_text(json.dumps({"pid": pid, "tid": tid, "hz": a.hz, "elapsed": elapsed, "errors": errors,
                                                   "host64": HOST64, "threads": threads, "modules": mods}, indent=1))
    txt = analyze(run, a.functions); (run / "summary.txt").write_text(txt)
    print(txt + f"\n\n{n} samples -> {run}")


if __name__ == "__main__":
    main()
