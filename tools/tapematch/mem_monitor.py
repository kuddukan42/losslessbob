#!/usr/bin/env python3
"""Sample RSS of a subprocess every INTERVAL seconds and print a summary."""
import subprocess, sys, time, threading, datetime

INTERVAL = 0.5
LOG = "/home/tjenkins/Documents/losslessbob/tools/tapematch/last_run.log"
TARGET = sys.argv[1:]

samples = []   # (elapsed_sec, rss_mb)
_stop = threading.Event()

def _sampler(pid):
    t0 = time.monotonic()
    while not _stop.is_set():
        try:
            with open(f"/proc/{pid}/status") as fh:
                for line in fh:
                    if line.startswith("VmRSS:"):
                        kb = int(line.split()[1])
                        samples.append((round(time.monotonic() - t0, 2), kb / 1024))
                        break
        except FileNotFoundError:
            break
        time.sleep(INTERVAL)

run_ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
header = f"\n{'='*64}\nRUN  {run_ts}\nCMD  {' '.join(TARGET)}\n{'='*64}\n"
print(f"[monitor] appending to {LOG}  ({run_ts})", flush=True)
with open(LOG, "a") as log_fh:
    log_fh.write(header)
with open(LOG, "a") as log_fh:
    proc = subprocess.Popen(TARGET, stdout=log_fh, stderr=subprocess.STDOUT)
    t = threading.Thread(target=_sampler, args=(proc.pid,), daemon=True)
    t.start()
    last_tick = 0
    while proc.poll() is None:
        elapsed = samples[-1][0] if samples else 0
        rss_now = samples[-1][1] if samples else 0
        if elapsed - last_tick >= 30:
            print(f"[monitor] t={elapsed:.0f}s  RSS={rss_now:.0f} MB  samples={len(samples)}", flush=True)
            last_tick = elapsed
        time.sleep(1)
_stop.set()
t.join(timeout=2)

if not samples:
    print("\n[monitor] No samples collected.", file=sys.stderr)
    sys.exit(proc.returncode)

times = [s[0] for s in samples]
rss   = [s[1] for s in samples]
peak  = max(rss)
t_peak = times[rss.index(peak)]

drops = []
for i in range(1, len(rss)):
    delta = rss[i-1] - rss[i]
    if delta > 100:
        drops.append((times[i], rss[i-1], rss[i]))

lo, hi = min(rss), max(rss)
W = 76
step = max(1, len(rss) // W)
spark_rss = rss[::step][:W]
blocks = " ▁▂▃▄▅▆▇█"

def _block(v):
    if hi == lo:
        return "▄"
    return blocks[min(int((v - lo) / (hi - lo) * 8), 8)]

summary_lines = [
    "",
    "╔══════════════════════════════════════════════════════════╗",
    "║              tapematch  — memory summary                 ║",
    "╠══════════════════════════════════════════════════════════╣",
    f"║  Runtime        : {times[-1]:.1f} s",
    f"║  Samples        : {len(samples)}  (every {INTERVAL}s)",
    f"║  Peak RSS       : {peak:.0f} MB  @ t={t_peak:.1f}s",
    f"║  Final RSS      : {rss[-1]:.0f} MB",
    f"║  Baseline (min) : {lo:.0f} MB",
    "╠══════════════════════════════════════════════════════════╣",
    "║  Large drops (>100 MB — source freed):",
]
if drops:
    for d in drops:
        summary_lines.append(f"║    t={d[0]:.1f}s  {d[1]:.0f}→{d[2]:.0f} MB  (−{d[1]-d[2]:.0f} MB)")
else:
    summary_lines.append("║    none detected")
summary_lines += [
    "╚══════════════════════════════════════════════════════════╝",
    "",
    "RSS over time (▁=low, █=peak):",
    "  " + "".join(_block(v) for v in spark_rss),
    f"  0s {'':>30} {times[-1]:.0f}s",
    f"  lo={lo:.0f} MB   hi={hi:.0f} MB",
]

summary = "\n".join(summary_lines)
print(summary)
with open(LOG, "a") as fh:
    fh.write("\n" + summary + "\n")

sys.exit(proc.returncode)
