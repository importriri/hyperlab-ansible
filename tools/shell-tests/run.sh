#!/bin/sh
# Also runnable with `sh run.sh`: a unified patch does not preserve the executable bit.
# Structural shell test suite. No display and no real GTK.
set -u
here="$(cd "$(dirname "$0")" && pwd)"
status=0
for suite in test_drawer.py test_sections.py test_design.py test_css_coverage.py; do
  printf '\n===== %s\n' "$suite"
  (cd "$here" && PYTHONDONTWRITEBYTECODE=1 python3 "$suite") || status=1
done
printf '\n'
if [ "$status" -eq 0 ]; then printf 'SHELL: GREEN\n'; else printf 'SHELL: RED\n'; fi
exit "$status"
