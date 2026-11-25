#!/usr/bin/env bash
set -euo pipefail

if [[ $# != 1 || ! $1 =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "Usage: $0 <version>" >&2
  exit 2
fi
version=$1
cd "$(git rev-parse --show-toplevel)"
if [[ $(git branch --show-current) != main || -n $(git status --porcelain) ]]; then
  echo 'Release requires a clean main branch' >&2
  exit 1
fi
python3 - "$version" <<'PY'
import json
import sys
from pathlib import Path

path = Path('custom_components/energy_bill/manifest.json')
data = json.loads(path.read_text())
data['version'] = sys.argv[1]
path.write_text(json.dumps(data, indent=2) + '\n')
PY
git add custom_components/energy_bill/manifest.json
git commit -m "chore: release $version" --allow-empty
git tag "$version"
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
python3 - "$tmp/energy_bill.zip" <<'PY'
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile
import sys
import subprocess

root = Path('custom_components')
with ZipFile(sys.argv[1], 'w', ZIP_DEFLATED) as archive:
    files = subprocess.check_output(['git', 'ls-files', '-z', '--', str(root / 'energy_bill')])
    for name in files.split(b'\0'):
        if name:
            path = Path(name.decode())
            archive.write(path, path.relative_to(root))
PY
git push origin main "$version"
gh release create "$version" "$tmp/energy_bill.zip" --verify-tag --title "$version" --generate-notes
