#!/data/data/com.termux/files/usr/bin/bash
# =============================================================
#  CatalogPro Load Test Runner
#  Usage: ./run_tests.sh [preset]
#
#  Presets:
#    quick     - 10 users, 20 seconds  (quick sanity check)
#    normal    - 30 users, 60 seconds  (typical day load)
#    heavy     - 100 users, 90 seconds (busy day simulation)
#    attack    - 200 users, 60 seconds (stress test / DDoS sim)
#    pdf       - PDF generation benchmark only
#    locust    - Opens Locust web UI at http://localhost:8089
# =============================================================

cd "$(dirname "$0")/.."   # go to catalogpro2 root

PRESET=${1:-quick}
HOST=${HOST:-http://localhost:5050}

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║     CatalogPro Load Test Runner         ║"
echo "╠══════════════════════════════════════════╣"
echo "║  Preset : $PRESET$(printf '%*s' $((32-${#PRESET})) '')║"
echo "║  Target : $HOST$(printf '%*s' $((32-${#HOST})) '')║"
echo "╚══════════════════════════════════════════╝"
echo ""

# Check server is running
echo "  Checking server..."
if ! curl -s --max-time 3 "$HOST/" > /dev/null 2>&1; then
  echo "  ❌ Server not responding at $HOST"
  echo "  Start it with: gunicorn app:app --bind 0.0.0.0:5050 --workers 2"
  exit 1
fi
echo "  ✅ Server is up"
echo ""

case "$PRESET" in

  quick)
    echo "  Running: Quick check (10 users, 20 seconds)"
    python3 loadtest/stress.py --host "$HOST" --users 10 --time 20 --ramp 2
    ;;

  normal)
    echo "  Running: Normal load (30 users, 60 seconds)"
    python3 loadtest/stress.py --host "$HOST" --users 30 --time 60 --ramp 3
    ;;

  heavy)
    echo "  Running: Heavy load (100 users, 90 seconds)"
    echo "  ⚠️  This will push your server hard. Watch gunicorn.log"
    sleep 2
    python3 loadtest/stress.py --host "$HOST" --users 100 --time 90 --ramp 5
    ;;

  attack)
    echo "  Running: Attack simulation (200 users, 60 seconds)"
    echo "  ⚠️  Simulates a DDoS. Rate limiting should kick in."
    sleep 2
    python3 loadtest/stress.py --host "$HOST" --users 200 --time 60 --ramp 20
    ;;

  pdf)
    echo "  Running: PDF benchmark"
    python3 loadtest/bench_pdf.py --concurrent 3 --rounds 5
    ;;

  pdf-heavy)
    echo "  Running: Heavy PDF benchmark (5 concurrent)"
    python3 loadtest/bench_pdf.py --concurrent 5 --rounds 10
    ;;

  locust)
    echo "  Starting Locust web UI..."
    echo "  Open http://localhost:8089 in your browser"
    echo "  Set host to: $HOST"
    echo ""
    locust -f loadtest/locustfile.py --host "$HOST"
    ;;

  locust-headless)
    echo "  Running Locust headless (50 users, 60 seconds)"
    locust -f loadtest/locustfile.py \
      --headless \
      --users 50 \
      --spawn-rate 5 \
      --run-time 60s \
      --host "$HOST"
    ;;

  all)
    echo "  Running full test suite..."
    echo ""
    echo "  [1/3] PDF Benchmark"
    python3 loadtest/bench_pdf.py --concurrent 3 --rounds 5
    echo ""
    echo "  [2/3] Normal load test"
    python3 loadtest/stress.py --host "$HOST" --users 30 --time 30 --ramp 3
    echo ""
    echo "  [3/3] Attack simulation"
    python3 loadtest/stress.py --host "$HOST" --users 100 --time 30 --ramp 10
    echo ""
    echo "  ✅ Full test suite complete"
    ;;

  *)
    echo "  Unknown preset: $PRESET"
    echo ""
    echo "  Available presets:"
    echo "    quick       10 users, 20s  — quick sanity check"
    echo "    normal      30 users, 60s  — typical load"
    echo "    heavy      100 users, 90s  — busy day"
    echo "    attack     200 users, 60s  — stress/DDoS sim"
    echo "    pdf                        — PDF generation benchmark"
    echo "    pdf-heavy                  — Heavy PDF benchmark"
    echo "    locust                     — Locust web UI"
    echo "    all                        — Run everything"
    echo ""
    echo "  Example:"
    echo "    ./loadtest/run_tests.sh heavy"
    echo "    HOST=https://catalogpro.co.ke ./loadtest/run_tests.sh normal"
    exit 1
    ;;
esac
