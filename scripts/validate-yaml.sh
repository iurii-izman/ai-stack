#!/usr/bin/env bash
set -euo pipefail

# Validate YAML files using PyYAML if available.
# Falls back to `find` if git is not initialized.

if ! command -v python >/dev/null 2>&1; then
  echo "Python is required to validate YAML files. Install Python and PyYAML (pip install pyyaml)."
  exit 1
fi

python - <<'PY'
import sys, subprocess
try:
    import yaml
except Exception as e:
    print('PyYAML not installed. Install with: pip install pyyaml')
    sys.exit(1)

import os
files = []
if os.path.isdir('.git'):
    try:
        out = subprocess.check_output(['git','ls-files','*.yaml','*.yml']).decode().strip()
        if out:
            files = out.splitlines()
    except Exception:
        pass
if not files:
    for root, dirs, filenames in os.walk('.'):
        # skip .git and node_modules
        if '.git' in root.split(os.sep) or 'node_modules' in root.split(os.sep):
            continue
        for fn in filenames:
            if fn.endswith(('.yaml', '.yml')):
                files.append(os.path.join(root, fn))

errors = 0
for f in files:
    try:
        with open(f, 'r', encoding='utf-8') as fh:
            yaml.safe_load(fh)
        print('OK  ' + f)
    except Exception as e:
        print('ERROR ' + f + ' -> ' + str(e))
        errors += 1

if errors:
    sys.exit(2)
PY

echo "YAML validation completed." 

