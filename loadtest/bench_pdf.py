"""
PDF Generation Benchmark
=========================
Tests how fast your server can generate catalogs.
This is usually the bottleneck — run this first.

Usage:
  python3 bench_pdf.py
  python3 bench_pdf.py --concurrent 5   # 5 simultaneous PDF generations
"""
import sys, os, time, threading, argparse
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

parser = argparse.ArgumentParser()
parser.add_argument("--concurrent", type=int, default=3)
parser.add_argument("--rounds",     type=int, default=10)
args = parser.parse_args()

os.makedirs("static/catalogs", exist_ok=True)
os.makedirs("static/uploads",  exist_ok=True)
os.makedirs("static/demos",    exist_ok=True)

from pdf_generator import generate_catalog, generate_preview

SAMPLE = {
    "business_name": "Benchmark Shop",
    "tagline":       "Speed Test Business",
    "phone":         "0700000000",
    "location":      "Nairobi",
    "email":         "",
    "whatsapp":      "0700000000",
    "instagram":     "",
    "facebook":      "",
    "footer_note":   "Test catalog",
    "logo_path":     None,
    "qr_link":       None,
    "products": [
        {"name": f"Product {i}", "price": str(i * 100),
         "description": f"Description for product {i}",
         "image_path": None}
        for i in range(1, 11)   # 10 products
    ],
}

def run_single(theme, results, idx):
    data = dict(SAMPLE)
    data["theme"] = theme
    t0 = time.time()
    try:
        fn   = generate_catalog(data)
        ms   = (time.time() - t0) * 1000
        size = os.path.getsize(f"static/catalogs/{fn}")
        results[idx] = {"ok": True, "ms": ms, "size": size, "theme": theme}
    except Exception as e:
        ms = (time.time() - t0) * 1000
        results[idx] = {"ok": False, "ms": ms, "error": str(e), "theme": theme}

THEMES = ["ivory", "slate", "charcoal", "forest", "noir"]

print(f"""
╔══════════════════════════════════════════════╗
║        PDF Generation Benchmark             ║
╠══════════════════════════════════════════════╣
║  Concurrent: {args.concurrent:<30} ║
║  Rounds    : {args.rounds:<30} ║
╚══════════════════════════════════════════════╝
""")

# ── SINGLE-THREAD BASELINE ────────────────────────────────────────────────────
print("  Phase 1: Single-thread baseline (1 PDF at a time)")
print(f"  {'Theme':<12} {'Time':>8}  {'Size':>10}  Status")
print(f"  {'-'*12} {'-'*8}  {'-'*10}  {'-'*8}")

single_times = []
for theme in THEMES:
    t0   = time.time()
    data = dict(SAMPLE); data["theme"] = theme
    try:
        fn   = generate_catalog(data)
        ms   = (time.time() - t0) * 1000
        size = os.path.getsize(f"static/catalogs/{fn}")
        single_times.append(ms)
        icon = "✅" if ms < 500 else ("⚠️ " if ms < 1500 else "❌")
        print(f"  {icon} {theme:<10} {ms:>7.0f}ms  {size/1024:>7.1f}KB  OK")
    except Exception as e:
        ms = (time.time() - t0) * 1000
        print(f"  ❌ {theme:<10} {ms:>7.0f}ms  {'':>10}  ERROR: {e}")

avg_single = sum(single_times) / len(single_times) if single_times else 0
print(f"\n  Average single-thread: {avg_single:.0f}ms per PDF")

# ── CONCURRENT LOAD ───────────────────────────────────────────────────────────
print(f"\n  Phase 2: Concurrent load ({args.concurrent} PDFs simultaneously)")

all_times = []
for round_n in range(1, args.rounds + 1):
    results  = [None] * args.concurrent
    threads  = []
    themes   = [THEMES[i % len(THEMES)] for i in range(args.concurrent)]

    t0 = time.time()
    for i in range(args.concurrent):
        t = threading.Thread(target=run_single,
                             args=(themes[i], results, i))
        threads.append(t)

    for t in threads: t.start()
    for t in threads: t.join()
    total_ms = (time.time() - t0) * 1000

    ok     = sum(1 for r in results if r and r["ok"])
    errors = args.concurrent - ok
    times  = [r["ms"] for r in results if r and r["ok"]]
    avg    = sum(times) / len(times) if times else 0
    all_times.extend(times)

    icon = "✅" if errors == 0 and avg < 2000 else ("⚠️ " if errors == 0 else "❌")
    print(f"  {icon} Round {round_n:>2}/{args.rounds}: "
          f"{ok}/{args.concurrent} OK | "
          f"Avg {avg:.0f}ms | Wall {total_ms:.0f}ms | "
          f"{'Errors: ' + str(errors) if errors else ''}")

# ── PREVIEW BENCHMARK ─────────────────────────────────────────────────────────
print(f"\n  Phase 3: Preview generation (watermarked partial PDFs)")
preview_times = []
for i in range(5):
    data = dict(SAMPLE); data["theme"] = THEMES[i % len(THEMES)]
    t0 = time.time()
    generate_preview(data)
    ms = (time.time() - t0) * 1000
    preview_times.append(ms)
    print(f"  Preview {i+1}: {ms:.0f}ms")

# ── SUMMARY ───────────────────────────────────────────────────────────────────
avg_concurrent = sum(all_times) / len(all_times) if all_times else 0
avg_preview    = sum(preview_times) / len(preview_times) if preview_times else 0
slowdown       = avg_concurrent / avg_single if avg_single > 0 else 1

print(f"""
  BENCHMARK SUMMARY
  {'='*44}
  Single-thread avg  : {avg_single:.0f}ms per PDF
  Concurrent avg     : {avg_concurrent:.0f}ms per PDF
  Preview avg        : {avg_preview:.0f}ms per preview
  Slowdown factor    : {slowdown:.1f}x under concurrent load
  {'='*44}
""")

if avg_single < 300:
    print("  ✅ PDF generation is fast. No bottleneck here.")
elif avg_single < 800:
    print("  ⚠️  PDF generation is acceptable but could be faster.")
    print("  Tip: Reduce image resolution in Config.MAX_IMAGE_SIZE")
else:
    print("  ❌ PDF generation is slow. This will cause timeouts under load.")
    print("  Fixes:")
    print("    1. Increase Gunicorn --timeout to 180")
    print("    2. Reduce Config.MAX_IMAGE_SIZE to (300, 300)")
    print("    3. Generate PDFs asynchronously (Celery/thread queue)")

if slowdown > 3:
    print(f"\n  ⚠️  {slowdown:.1f}x slowdown under concurrent load.")
    print("  Add more Gunicorn workers: --workers 4")
else:
    print(f"\n  ✅ Concurrent load slowdown is acceptable ({slowdown:.1f}x)")
