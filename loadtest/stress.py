"""
CatalogPro Quick Stress Test
=============================
Runs without Locust — pure Python threads.
Good for a quick sanity check from Termux.

Usage:
  python3 stress.py                     # default: 20 users, 30 seconds
  python3 stress.py --users 50          # 50 concurrent users
  python3 stress.py --users 100 --time 60
  python3 stress.py --host https://your-domain.co.ke --users 30
"""

import threading, time, argparse, random, sys
import urllib.request, urllib.parse, urllib.error
from collections import defaultdict
from datetime import datetime

# ── CONFIG ────────────────────────────────────────────────────────────────────
parser = argparse.ArgumentParser()
parser.add_argument("--host",  default="http://localhost:5050")
parser.add_argument("--users", type=int, default=20)
parser.add_argument("--time",  type=int, default=30,  help="seconds")
parser.add_argument("--ramp",  type=int, default=5,   help="users per second spawn rate")
args = parser.parse_args()

BASE     = args.host.rstrip("/")
DURATION = args.time
USERS    = args.users
RAMP     = args.ramp

# ── SHARED STATS ──────────────────────────────────────────────────────────────
lock        = threading.Lock()
results     = defaultdict(lambda: {"count":0, "errors":0, "total_ms":0, "max_ms":0})
start_time  = None
stop_flag   = threading.Event()

def record(name, elapsed_ms, error=False):
    with lock:
        r = results[name]
        r["count"]    += 1
        r["errors"]   += 1 if error else 0
        r["total_ms"] += elapsed_ms
        if elapsed_ms > r["max_ms"]:
            r["max_ms"] = elapsed_ms

def get(path, name):
    url = BASE + path
    t0  = time.time()
    try:
        req  = urllib.request.Request(url, headers={"User-Agent": "CatalogProLoadTest/1.0"})
        resp = urllib.request.urlopen(req, timeout=10)
        ms   = (time.time() - t0) * 1000
        record(name, ms, error=(resp.status >= 400))
        return resp.read().decode("utf-8", errors="ignore"), resp.status
    except urllib.error.HTTPError as e:
        ms = (time.time() - t0) * 1000
        record(name, ms, error=(e.code not in [429, 404]))  # these are expected
        return "", e.code
    except Exception as e:
        ms = (time.time() - t0) * 1000
        record(name, ms, error=True)
        return "", 0

# ── SCENARIOS ─────────────────────────────────────────────────────────────────
SCENARIOS = [
    # (weight, function)
]

def scenario_browser():
    """A user browsing the site."""
    pages = [
        ("/",               "Landing Page"),
        ("/demo/fashion",   "Demo - Fashion"),
        ("/demo/food",      "Demo - Food"),
        ("/demo/electronics","Demo - Electronics"),
        ("/order/starter",  "Order Page - Starter"),
        ("/order/business", "Order Page - Business"),
        ("/order/premium",  "Order Page - Premium"),
    ]
    page, name = random.choice(pages)
    get(page, name)
    time.sleep(random.uniform(0.5, 2))

def scenario_track():
    """User tracking their order."""
    get("/track", "Track Page")
    time.sleep(random.uniform(1, 3))

def scenario_status_poll():
    """Simulates status page polling (waiting for payment)."""
    # Random order ID — will 404 but tests the endpoint
    fake_id = "".join(random.choices("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789", k=10))
    _, code = get(f"/status/{fake_id}?json=1", "Status Poll")
    time.sleep(0.5)

def scenario_attack_probe():
    """Tests that attack paths return 404 fast."""
    paths = ["/admin", "/wp-admin", "/.env", "/config.php", "/phpinfo.php"]
    get(random.choice(paths), "Attack Probe [expect 404]")

def scenario_rapid_fire():
    """Hammers the landing page rapidly — tests rate limiting."""
    for _ in range(5):
        get("/", "Rapid Landing [rate limit test]")
        time.sleep(0.05)

WEIGHTED_SCENARIOS = (
    [scenario_browser]       * 50 +
    [scenario_track]         * 10 +
    [scenario_status_poll]   * 15 +
    [scenario_attack_probe]  * 10 +
    [scenario_rapid_fire]    * 15
)

def worker():
    """Each thread runs this — picks random scenarios until stop."""
    while not stop_flag.is_set():
        fn = random.choice(WEIGHTED_SCENARIOS)
        try:
            fn()
        except Exception:
            pass

# ── LIVE STATS PRINTER ────────────────────────────────────────────────────────
def print_live_stats():
    last_count = 0
    while not stop_flag.is_set():
        time.sleep(5)
        with lock:
            total = sum(r["count"] for r in results.values())
            errors = sum(r["errors"] for r in results.values())
            rps    = (total - last_count) / 5
            last_count = total
            elapsed = time.time() - start_time
            remaining = max(0, DURATION - elapsed)

        err_pct = (errors / total * 100) if total > 0 else 0
        bar_len = 30
        done    = int(bar_len * (DURATION - remaining) / DURATION)
        bar     = "█" * done + "░" * (bar_len - done)

        print(f"\r  [{bar}] {remaining:.0f}s left | "
              f"Req: {total:,} | RPS: {rps:.1f} | "
              f"Errors: {errors} ({err_pct:.1f}%) | "
              f"Users: {threading.active_count()-2}",
              end="", flush=True)

# ── MAIN ──────────────────────────────────────────────────────────────────────
def main():
    global start_time

    print(f"""
╔══════════════════════════════════════════════════╗
║        CatalogPro Stress Test                    ║
╠══════════════════════════════════════════════════╣
║  Target : {BASE:<38} ║
║  Users  : {USERS:<38} ║
║  Duration: {DURATION}s{' '*(37-len(str(DURATION)))}║
║  Ramp   : {RAMP} users/second{' '*(29-len(str(RAMP)))}║
╚══════════════════════════════════════════════════╝
""")

    # Quick connectivity check
    print("  Checking connectivity...", end="")
    try:
        urllib.request.urlopen(BASE + "/", timeout=5)
        print(" ✅ Server is reachable\n")
    except Exception as e:
        print(f" ❌ Cannot reach server: {e}")
        print("  Make sure your app is running first!")
        sys.exit(1)

    start_time = time.time()
    threads    = []

    # Start live stats printer
    stats_thread = threading.Thread(target=print_live_stats, daemon=True)
    stats_thread.start()

    # Ramp up users gradually
    print(f"  Ramping up {USERS} users at {RAMP}/second...")
    for i in range(USERS):
        t = threading.Thread(target=worker, daemon=True)
        t.start()
        threads.append(t)
        if (i + 1) % RAMP == 0:
            time.sleep(1)

    print(f"  All {USERS} users active. Running for {DURATION}s...\n")
    time.sleep(DURATION)

    stop_flag.set()
    time.sleep(1)

    # ── FINAL REPORT ──────────────────────────────────────────────────────────
    print("\n\n" + "="*60)
    print("  STRESS TEST RESULTS")
    print("="*60)
    print(f"  {'Endpoint':<35} {'Reqs':>6} {'Err%':>6} {'Avg':>7} {'Max':>7}")
    print(f"  {'-'*35} {'-'*6} {'-'*6} {'-'*7} {'-'*7}")

    total_req = 0
    total_err = 0
    all_ms    = []

    with lock:
        for name, r in sorted(results.items(), key=lambda x: -x[1]["count"]):
            count    = r["count"]
            errors   = r["errors"]
            avg_ms   = r["total_ms"] / count if count > 0 else 0
            max_ms   = r["max_ms"]
            err_pct  = errors / count * 100 if count > 0 else 0
            total_req += count
            total_err += errors
            all_ms.extend([avg_ms] * count)

            # Colour code by speed
            speed_icon = "✅" if avg_ms < 300 else ("⚠️ " if avg_ms < 800 else "❌")
            trunc_name = name[:34]
            print(f"  {speed_icon} {trunc_name:<33} {count:>6,} {err_pct:>5.1f}% "
                  f"{avg_ms:>6.0f}ms {max_ms:>6.0f}ms")

    print("="*60)
    overall_err  = total_err / total_req * 100 if total_req > 0 else 0
    overall_avg  = sum(all_ms) / len(all_ms) if all_ms else 0
    elapsed      = time.time() - start_time
    overall_rps  = total_req / elapsed

    print(f"\n  Total requests : {total_req:,}")
    print(f"  Total errors   : {total_err:,} ({overall_err:.1f}%)")
    print(f"  Avg response   : {overall_avg:.0f}ms")
    print(f"  Average RPS    : {overall_rps:.1f}")

    # Grade
    print()
    if overall_avg < 300 and overall_err < 1:
        print("  ✅ EXCELLENT — Handles heavy load well. Ready for launch.")
    elif overall_avg < 600 and overall_err < 5:
        print("  ⚠️  GOOD — Works under load. Consider adding more Gunicorn workers.")
    elif overall_avg < 1200 and overall_err < 15:
        print("  ⚠️  FAIR — Sluggish under load. Add workers, check PDF generation time.")
    else:
        print("  ❌ POOR — Failing under load. Check bottlenecks below.")
        print_bottlenecks()

    print()
    print_recommendations(overall_avg, overall_err, overall_rps)
    print("="*60 + "\n")


def print_bottlenecks():
    print("\n  BOTTLENECKS DETECTED:")
    with lock:
        for name, r in sorted(results.items(), key=lambda x: -x[1]["total_ms"]):
            avg = r["total_ms"] / r["count"] if r["count"] > 0 else 0
            if avg > 800:
                print(f"  ❌ Slow: {name} — {avg:.0f}ms avg")


def print_recommendations(avg_ms, err_pct, rps):
    print("  RECOMMENDATIONS:")
    if avg_ms > 500:
        print("  • Increase Gunicorn workers: --workers 4")
        print("  • PDF generation is slow — consider caching generated PDFs")
    if err_pct > 5:
        print("  • High error rate — check app logs: tail -f gunicorn.log")
    if rps < 10:
        print("  • Low RPS — your server may be CPU-bound")
        print("  • Consider upgrading to a VPS for production")
    if avg_ms < 300 and err_pct < 1:
        print("  • Everything looks good!")
        print("  • For very high traffic, consider Redis for session storage")
        print("  • Add a CDN (Cloudflare) for static files")


if __name__ == "__main__":
    main()
