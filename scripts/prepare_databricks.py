"""Stage deployment source without local secrets, virtualenvs or generated files."""
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
target = Path(sys.argv[1]).resolve()
if target.exists():
    raise SystemExit('Choose a new staging directory to avoid stale deployment files.')
allowed = {'app', 'agents', 'frontend', 'virtue-healthcare', 'pipeline'}
files = subprocess.check_output(['git', 'ls-files', '-z'], cwd=ROOT).decode().split('\0')
files += ['app.yaml', 'requirements.txt', 'package.json', 'app/database.py', 'app/init_lakebase.py']
for name in set(files):
    path = Path(name)
    if not name or not (path.parts[0] in allowed or name.startswith('data/processed/')
                        or name in ('app.yaml', 'requirements.txt', 'package.json')):
        continue
    if any(part.startswith('.') or part in ('node_modules', 'dist', '__pycache__') for part in path.parts):
        continue
    if path.suffix not in {'.py', '.txt', '.json', '.js', '.jsx', '.css', '.html', '.svg',
                           '.png', '.jpg', '.woff', '.woff2', '.sql', '.gz', '.xz', '.yaml', '.csv'}:
        continue
    if not (ROOT / path).is_file():
        continue
    dest = target / path
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / path, dest)
(target / '.gitignore').write_text('__pycache__/\n*.pyc\nnode_modules/\ndist/\n.env\n.env.*\n')
print('Prepared deployment source in', target)
