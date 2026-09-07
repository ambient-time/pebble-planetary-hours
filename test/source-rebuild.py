"""Extract the final source ZIP into a separate directory and build every target.

Run after package.py. Copyright 2026 Luke Steuber. MIT License.
"""
import datetime
import hashlib
import json
from pathlib import Path
import subprocess
import struct
from libpebble2.util.stm32_crc import crc32
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parent.parent


def digest(data):
    return hashlib.sha256(data).hexdigest()


def normalized_binary(data):
    # SDK 4.33.1 header plus its GNU build-id note. Verify each original CRC
    # before removing only build metadata from the byte comparison.
    load_size = struct.unpack_from('<H', data, 0x0e)[0]
    assert crc32(data[0x82:load_size]) == struct.unpack_from('<I', data, 0x14)[0]
    assert data[0x84:0x94] == struct.pack('<III', 4, 20, 3) + b'GNU\0'
    normalized = bytearray(data)
    for offset, count in ((0x14, 4), (0x7c, 4), (0x94, 20)):
        normalized[offset:offset + count] = bytes(count)
    return bytes(normalized)


def main():
    metadata = json.loads((ROOT / 'package.json').read_text())
    release = ROOT / 'release'
    archive = release / f'planetary-hours-{metadata["version"]}-source.zip'
    original = release / f'planetary-hours-{metadata["version"]}.pbw'
    proof_name = f'planetary-hours-{metadata["version"]}-source-rebuild'
    (release / f'{proof_name}.json').write_text(json.dumps({'sourceZIPSHA256': digest(archive.read_bytes()), 'result': 'incomplete'}, indent=2) + '\n')
    with tempfile.TemporaryDirectory(prefix='planetary-hours-source-check-') as temp:
        root = Path(temp) / 'planetary-hours'
        root.mkdir()
        with zipfile.ZipFile(archive) as z:
            assert z.testzip() is None
            assert 'package.json' in z.namelist() and 'src/c/main.c' in z.namelist()
            assert not any(Path(n).is_absolute() or '..' in Path(n).parts for n in z.namelist())
            z.extractall(root)
        run = subprocess.run(['make', 'build'], cwd=root, stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, text=True)
        (release / f'{proof_name}.log').write_text(run.stdout)
        assert run.returncode == 0, f'Independent source build failed; inspect release/{proof_name}.log'
        with zipfile.ZipFile(original) as a, zipfile.ZipFile(root / 'build/planetary-hours.pbw') as b:
            assert a.testzip() is None and b.testzip() is None
            assert json.loads(a.read('appinfo.json')) == json.loads(b.read('appinfo.json'))
            assert a.read('pebble-js-app.js') == b.read('pebble-js-app.js'), 'Phone companion changed'
            comparisons = {}
            for platform in metadata['pebble']['targetPlatforms']:
                resource = platform + '/app_resources.pbpack'
                assert a.read(resource) == b.read(resource), f'{platform} resources changed'
                binary = platform + '/pebble-app.bin'
                release_bin, rebuilt_bin = a.read(binary), b.read(binary)
                normalized_release = normalized_binary(release_bin)
                normalized_rebuilt = normalized_binary(rebuilt_bin)
                assert normalized_release == normalized_rebuilt, f'{platform} code or data changed beyond build metadata'
                comparisons[platform] = {'resourceSHA256': digest(b.read(resource)),
                                         'binaryMatchesExceptBuildMetadata': True,
                                         'normalizedBinarySHA256': digest(normalized_rebuilt),
                                         'ignoredFields': ['verified internal CRC at 0x14', 'SDK resource timestamp at 0x7c', 'GNU build-id payload at 0x94'],
                                         'binarySHA256': digest(b.read(binary)),
                                         'binaryMatchesRelease': a.read(binary) == b.read(binary)}
        report = {'sourceZIP': archive.name, 'sourceZIPSHA256': digest(archive.read_bytes()),
                  'pbwSHA256': digest(original.read_bytes()), 'sdk': '4.33.1',
                  'checkedAt': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                  'buildDirectory': str(root), 'result': 'passed',
                  'hostChecks': 'native sanitizer boundary checks, 907 solar/source checks, 20 phone scenarios and built-companion event checks',
                  'platforms': comparisons, 'phoneCompanionIdentical': True,
                  'limits': 'Independent local SDK build from root-level ZIP. CloudPebble import still needs its own check.'}
        (release / f'{proof_name}.json').write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
