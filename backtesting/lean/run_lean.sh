#!/bin/bash
# Usage: ./run_lean.sh <AlgorithmName> [config_file]
# AlgorithmName: directory under backtesting/lean/
# Runs LEAN via direct Docker, copies results to results/<AlgorithmName>/

set -e

ALGO="${1}"
CONFIG="${2:-lean-docker-config.json}"

if [ -z "$ALGO" ]; then
    echo "Usage: $0 <AlgorithmName> [config_file]"
    echo "Example: $0 IronCondor"
    exit 1
fi

# Resolve host path for this workspace
# /workspace/agent -> /home/kevin/nc/nanoclaw-v2/groups/dm-with-kevin
HOST_BASE="/home/kevin/nc/nanoclaw-v2/groups/dm-with-kevin/backtesting/lean"
CONTAINER_BASE="/workspace/agent/backtesting/lean"
RESULTS_DIR="${CONTAINER_BASE}/results/${ALGO}"
mkdir -p "${RESULTS_DIR}"

# Get class name from algorithm-type-name in config
CLASS_NAME=$(python3 -c "import json; d=json.load(open('${CONTAINER_BASE}/${CONFIG}')); print(d['algorithm-type-name'])" 2>/dev/null || echo "${ALGO}")

echo "Running LEAN backtest: ${ALGO} (class: ${CLASS_NAME})"
echo "Config: ${CONFIG}"
echo ""

docker run --name "lean_${ALGO}_$$" \
  -v "${HOST_BASE}/${CONFIG}:/Lean/Launcher/bin/Debug/config.json:ro" \
  -v "${HOST_BASE}/${ALGO}:/Lean/Launcher/bin/Debug/Algorithm.Python/${ALGO}:ro" \
  quantconnect/lean:latest 2>&1 | tee "${RESULTS_DIR}/lean.log"

# Copy result files
docker cp "lean_${ALGO}_$$:/Lean/Launcher/bin/Debug/${CLASS_NAME}.json" "${RESULTS_DIR}/" 2>/dev/null || true
docker cp "lean_${ALGO}_$$:/Lean/Launcher/bin/Debug/${CLASS_NAME}-summary.json" "${RESULTS_DIR}/" 2>/dev/null || true
docker cp "lean_${ALGO}_$$:/Lean/Launcher/bin/Debug/${CLASS_NAME}-order-events.json" "${RESULTS_DIR}/" 2>/dev/null || true
docker rm "lean_${ALGO}_$$"

echo ""
echo "Results in: ${RESULTS_DIR}/"
grep "STATISTICS::" "${RESULTS_DIR}/lean.log" | head -20
