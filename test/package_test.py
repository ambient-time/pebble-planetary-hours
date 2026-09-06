"""Packaging regression tests using synthetic archives, never an emulator.

Copyright 2026 Luke Steuber. MIT License.
"""
import copy
import io
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

import png
from libpebble2.util.stm32_crc import crc32

import package


def image(size, value=0):
    out = io.BytesIO()
    png.Writer(*size, greyscale=True).write(out, [[value] * size[0]] * size[1])
    return out.getvalue()


class PackageTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='planetary-hours-package-test-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / 'renamed-import'
        self.root.mkdir()
        (self.root / 'build').mkdir()
        for directory in package.SOURCE_DIRS:
            (self.root / directory).mkdir()
        (self.root / 'resources/images').mkdir()
        (self.root / 'resources/images/menu-icon.png').write_bytes(image((25, 25)))
        for name in package.ROOT_FILES:
            (self.root / name).write_text('Synthetic packaging test input.\n')
        (self.root / 'reference/source.html').write_text('<!doctype html><title>Test reference</title>')
        self.source = {'name': 'planetary-hours', 'author': 'Luke Steuber', 'version': '0.1.0',
                       'pebble': {'uuid': package.UUID, 'companyName': 'Luke Steuber',
                                  'targetPlatforms': list(package.SIZES), 'capabilities': ['location'],
                                  'messageKeys': package.KEYS, 'enableMultiJS': True}}
        self.save_source()
        self.info = {'uuid': package.UUID, 'versionLabel': '0.1.0', 'companyName': 'Luke Steuber',
                     'watchapp': {'watchface': True}, 'targetPlatforms': list(package.SIZES),
                     'capabilities': ['location'], 'appKeys': package.KEYS, 'resources': {'media': [{'menuIcon': True}]}}
        self.pbw = self.root / 'build' / 'renamed-import.pbw'
        self.write_pbw()

    def save_source(self):
        (self.root / 'package.json').write_text(json.dumps(self.source))

    def write_pbw(self, corrupt=None):
        with zipfile.ZipFile(self.pbw, 'w') as archive:
            archive.writestr('appinfo.json', json.dumps(self.info))
            archive.writestr('pebble-js-app.js', '// Synthetic phone companion')
            for platform in package.SIZES:
                manifest = {}
                for kind in ('application', 'resources'):
                    payload = (platform + kind).encode() * 4
                    checksum = crc32(payload)
                    if corrupt == (platform, kind):
                        checksum ^= 1
                    manifest[kind] = {'name': kind + '.bin', 'size': len(payload), 'crc': checksum}
                    archive.writestr(f'{platform}/{kind}.bin', payload)
                archive.writestr(f'{platform}/manifest.json', json.dumps(manifest))

    def evidence(self):
        folder = self.root / 'build/evidence'
        folder.mkdir()
        for platform, size in package.SIZES.items():
            frames = []
            for name in sorted(package.REQUIRED_FRAMES | {'boot'}):
                filename = f'{platform}-{name}.png'
                (folder / filename).write_bytes(image(size, int(name == 'polar-day')))
                frames.append('build/evidence/' + filename)
            report = {'platform': platform, 'pbwSHA256': package.sha(self.pbw),
                      'capturedAt': '2026-09-06T08:00:00+00:00', **{flag: True for flag in package.FLAGS},
                      'frames': frames, 'frameSHA256': {Path(frame).name: package.sha(folder / Path(frame).name) for frame in frames},
                      'logs': [f'Planetary time={stamp}:00 frame_ms=4 free=10000'
                                                for stamp in ('09:24', '05:59', '06:00', '17:59', '18:00', '23:59', '00:00')]
                               + ['Planetary schedule accepted', 'Planetary schedule rejected']}
            (folder / f'{platform}-report.json').write_text(json.dumps(report))
        return folder

    def amend_report(self, folder, **changes):
        path = folder / 'basalt-report.json'
        report = json.loads(path.read_text())
        report.update(changes)
        path.write_text(json.dumps(report))

    def test_renamed_import_validates_without_evidence(self):
        source, pbw, digest = package.validate_build(self.root)
        self.assertEqual(source['version'], '0.1.0')
        self.assertEqual(pbw, self.pbw)
        self.assertEqual(digest, package.sha(pbw))
        self.assertFalse((self.root / 'release').exists())

    def test_rejects_crc_mismatch(self):
        self.write_pbw(corrupt=('gabbro', 'resources'))
        with self.assertRaisesRegex(ValueError, 'STM32 CRC'):
            package.validate_build(self.root)

    def test_rejects_source_identity_or_target_changes(self):
        original = copy.deepcopy(self.source)
        changes = [('author', 'Ambient Time'), ('name', 'another-face')]
        for field, value in changes:
            with self.subTest(field=field):
                self.source = copy.deepcopy(original)
                self.source[field] = value
                self.save_source()
                with self.assertRaises(ValueError):
                    package.validate_build(self.root)
        self.source = copy.deepcopy(original)
        self.source['pebble']['targetPlatforms'][0] = 'aplite'
        self.save_source()
        with self.assertRaisesRegex(ValueError, 'six target'):
            package.validate_build(self.root)

    def test_rejects_pbw_metadata_changes(self):
        original = copy.deepcopy(self.info)
        for field, value in [('uuid', 'another-uuid'), ('versionLabel', '0.0.9'),
                             ('companyName', 'Ambient Time'), ('capabilities', []),
                             ('appKeys', {'unexpected': 1}), ('watchapp', {'watchface': False}),
                             ('targetPlatforms', ['basalt'] * 6), ('resources', {'media': []})]:
            with self.subTest(field=field):
                self.info = copy.deepcopy(original)
                self.info[field] = value
                self.write_pbw()
                with self.assertRaises(ValueError):
                    package.validate_build(self.root)

    def test_rejects_wrong_size_or_truncated_menu_png(self):
        path = self.root / 'resources/images/menu-icon.png'
        path.write_bytes(image((24, 25)))
        with self.assertRaisesRegex(ValueError, 'expected'):
            package.validate_build(self.root)
        path.write_bytes(image((25, 25))[:33])
        with self.assertRaises(png.Error):
            package.validate_build(self.root)

    def test_rejects_stale_evidence_and_missing_rollover(self):
        folder = self.evidence()
        self.amend_report(folder, pbwSHA256='stale')
        with self.assertRaisesRegex(ValueError, 'stale evidence'):
            package.validate_evidence(folder, package.sha(self.pbw))
        self.amend_report(folder, pbwSHA256=package.sha(self.pbw), naturalSunriseRollover=False)
        with self.assertRaisesRegex(ValueError, 'naturalSunriseRollover'):
            package.validate_evidence(folder, package.sha(self.pbw))

    def test_rejects_absent_fixture_log(self):
        folder = self.evidence()
        self.amend_report(folder, logs=['Planetary time=10:08:00'])
        with self.assertRaisesRegex(ValueError, 'missing time fixture'):
            package.validate_evidence(folder, package.sha(self.pbw))

    def test_rejects_wrong_size_and_changed_restart_pixels(self):
        folder = self.evidence()
        later = folder / 'basalt-restart-saved.png'
        later.write_bytes(image((1, 1)))
        report = json.loads((folder / 'basalt-report.json').read_text())
        report['frameSHA256'][later.name] = package.sha(later)
        self.amend_report(folder, frameSHA256=report['frameSHA256'])
        with self.assertRaisesRegex(ValueError, 'expected'):
            package.validate_evidence(folder, package.sha(self.pbw))
        later.write_bytes(image(package.SIZES['basalt'], 1))
        report['frameSHA256'][later.name] = package.sha(later)
        self.amend_report(folder, frameSHA256=report['frameSHA256'])
        with self.assertRaisesRegex(ValueError, 'changed saved schedule'):
            package.validate_evidence(folder, package.sha(self.pbw))

    def test_rejects_changed_capture_bytes(self):
        folder = self.evidence()
        (folder / 'basalt-hero.png').write_bytes(image(package.SIZES['basalt'], 1))
        with self.assertRaisesRegex(ValueError, 'native capture hash mismatch'):
            package.validate_evidence(folder, package.sha(self.pbw))

    def test_stages_portable_source_and_normalized_evidence(self):
        folder = self.evidence()
        cache = self.root / 'test/__pycache__'
        cache.mkdir()
        (cache / 'excluded.pyc').write_bytes(b'cache')
        (self.root / 'test/package_test.py').write_text('# synthetic test source\n')
        source, pbw, digest = package.validate_build(self.root)
        reports = package.validate_evidence(folder, digest)
        summary = package.stage(self.root, folder, source, pbw, digest, reports)
        release = self.root / 'release'
        archive = release / 'planetary-hours-0.1.0-source.zip'
        with zipfile.ZipFile(archive) as source_zip:
            names = source_zip.namelist()
            self.assertIn('reference/source.html', names)
            self.assertIn('test/package_test.py', names)
            self.assertTrue(set(package.ROOT_FILES).issubset(names))
            self.assertFalse(any(name.startswith(('build/', 'release/', 'evidence/')) or '__pycache__' in name for name in names))
        self.assertEqual(summary['sourceZipSHA256'], package.sha(archive))
        self.assertEqual(package.sha(release / 'planetary-hours-0.1.0.pbw'), digest)
        self.assertIn(digest, (release / 'SHA256SUMS').read_text())
        captures = self.root / 'evidence'
        report = json.loads((captures / 'basalt-report.json').read_text())
        self.assertTrue(all('/' not in name and 'boot' not in name for name in report['frames']))
        self.assertEqual(summary['platforms']['basalt']['loggedRenderMS'], {'min': 4, 'max': 4})
        self.assertEqual(summary['platforms']['basalt']['minimumLoggedFreeHeapBytes'], 10000)
        # Staged reports remain valid without their original build/evidence paths.
        package.validate_evidence(captures, digest)


if __name__ == '__main__':
    unittest.main()
