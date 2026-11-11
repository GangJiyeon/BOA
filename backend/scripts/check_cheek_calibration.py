"""Validate profile syntax; does not certify scientific validity or enable it."""
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.services.cheek_calibration import CheekProfile
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('profile', nargs='?')
p.add_argument('--schema', action='store_true')
a=p.parse_args()
if a.schema:
    print(json.dumps(CheekProfile.model_json_schema(),ensure_ascii=False,indent=2))
elif a.profile:
    try:
        profile=CheekProfile.model_validate_json(Path(a.profile).read_bytes())
    except (OSError, ValueError) as e:
        p.exit(1,f'Invalid profile: {e}\n')
    print(f'Syntax OK: {profile.version}; status={profile.status}; site={profile.site}')
    print('This checks file structure only, not skin measurement accuracy.')
else:
    p.error('provide a profile path or --schema')
