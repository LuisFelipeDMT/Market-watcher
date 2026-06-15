#!/usr/bin/env bash
# Dependency vulnerability + secret audit for CI / pre-deploy.
# Hash-pinning: generate a locked, hashed requirements file with
#   pip install pip-tools && pip-compile --generate-hashes -o requirements.lock requirements.txt
# then install with `pip install --require-hashes -r requirements.lock`.
set -euo pipefail

echo "==> pip-audit (known CVEs in dependencies)"
python -m pip install --quiet pip-audit
pip-audit || { echo "pip-audit found issues"; exit 1; }

echo "==> scanning for accidentally committed secrets"
if git grep -nIE '(XP_PASSWORD|BEGIN [A-Z ]*PRIVATE KEY|SNAPSHOT_KEY=.+)' \
    -- ':!*.example' ':!scripts/audit.sh'; then
    echo "Potential secret committed — review the matches above"; exit 1
fi
echo "OK: no obvious secrets committed"
