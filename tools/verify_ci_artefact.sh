#!/usr/bin/env bash
# N3: Download the CI OrbitRx-windows-unsigned artefact for a run and prove
# byte-identical match against a local artefact-vN/ folder.
#
# Why gh sometimes returns 401:
#   - `gh` uses GH_TOKEN / GITHUB_TOKEN. A missing, expired, or wrong-scope
#     token yields HTTP 401 ("bad credentials"). The GitHub connector also
#     cannot download Actions artefacts.
#   - Use the sign-off PAT that can read private repo Actions artefacts:
#       export GH_TOKEN="$GH_TOKEN_SIGNOFF"
#     or pass it per-invocation. Do not print the token.
#
# Usage:
#   tools/verify_ci_artefact.sh <run_id> <local_artefact_dir>
# Example:
#   GH_TOKEN=$GH_TOKEN_SIGNOFF tools/verify_ci_artefact.sh 41981810503 \
#       /workspace/reviews/orbitrx-merge/artefact-v9
set -euo pipefail
RUN_ID="${1:?usage: verify_ci_artefact.sh <run_id> <local_artefact_dir>}"
LOCAL="${2:?usage: verify_ci_artefact.sh <run_id> <local_artefact_dir>}"
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

if [[ -z "${GH_TOKEN:-${GITHUB_TOKEN:-}}" ]]; then
  echo "error: set GH_TOKEN (or GITHUB_TOKEN) to a PAT that can read Actions artefacts" >&2
  echo "hint: GH_TOKEN=\$GH_TOKEN_SIGNOFF $0 $RUN_ID $LOCAL" >&2
  exit 2
fi

echo "Downloading OrbitRx-windows-unsigned from run $RUN_ID ..."
gh run download "$RUN_ID" -n OrbitRx-windows-unsigned -D "$TMP"

echo "CI SHA256SUMS:"
cat "$TMP/SHA256SUMS.txt"
echo
echo "Local SHA256SUMS:"
cat "$LOCAL/SHA256SUMS.txt"
echo

cd "$TMP"
sha256sum -c SHA256SUMS.txt
echo
python3 - <<PY
from pathlib import Path
import hashlib, sys
local = Path(r"$LOCAL")
ci = Path(r"$TMP")
ok = True
for name in ("OrbitRxMonitor.exe", "OrbitRxMonitor-Setup.exe"):
    lb, cb = (local/name).read_bytes(), (ci/name).read_bytes()
    lh, ch = hashlib.sha256(lb).hexdigest(), hashlib.sha256(cb).hexdigest()
    match = lh == ch and len(lb) == len(cb)
    print(f"{name}: local={lh} ci={ch} bytes={len(lb)} match={match}")
    ok = ok and match
sys.exit(0 if ok else 1)
PY
echo "BYTE-IDENTICAL: PASS"
