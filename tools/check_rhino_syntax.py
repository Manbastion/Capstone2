"""Check only the modules that Rhino's Python 3.9 imports; no third-party deps."""
import ast
from pathlib import Path

root = Path(__file__).resolve().parents[1]
paths = list(root.glob('0[0-4]_*.py')) + list((root / 'grasshopper_components').glob('*.py'))
paths += [root / 'habsim_notifications.py', root / 'variable_transfer_v2.py']
for path in paths:
    ast.parse(path.read_text(encoding='utf-8'), filename=str(path), feature_version=(3, 9))
print('Rhino Python 3.9 syntax passed for %d modules.' % len(paths))
