#!/usr/bin/env bash
set -euo pipefail

echo "Starting core module..."
exec ./stack.sh start core
