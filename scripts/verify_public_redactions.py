"""Verify the published redacted records and, optionally, their private originals."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile

WORKSPACE = Path(__file__).resolve().parents[1]


def verify(originals=None):
    manifest = json.loads((WORKSPACE / 'loho-study/public_redactions.json').read_text())
    assert manifest['schema_version'] == 1
    checked = set()
    for entry in manifest['files']:
        path = (WORKSPACE / entry['file']).resolve()
        path.relative_to(WORKSPACE.resolve())
        assert entry['file'] not in checked, 'Duplicate manifest entry'
        checked.add(entry['file'])
        assert hashlib.sha256(path.read_bytes()).hexdigest() == entry['public_sha256'], entry['file']
    if originals is not None:
        with zipfile.ZipFile(str(originals)) as archive:
            for entry in manifest['files']:
                assert hashlib.sha256(archive.read(entry['file'])).hexdigest() == entry['original_sha256'], entry['file']
    print('Verified {} public records{}.'.format(len(checked),
        ' and their private originals' if originals is not None else ''))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--originals', type=Path, help='Optional private originals.zip backup')
    args = parser.parse_args()
    verify(args.originals)
