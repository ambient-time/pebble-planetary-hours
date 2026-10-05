"""Luke Steuber. Capture revision PBWs in fresh face-local native profiles.

Synthetic phone messages exercise layout and data states; no phone location is
requested. This is emulator evidence, not physical-watch acceptance.
"""
import argparse
import datetime as dt
import hashlib
import json
import math
import os
from pathlib import Path
import re
import struct
import subprocess
import tempfile
import time
from types import SimpleNamespace
from uuid import UUID

SDK = Path.home() / 'Library/Application Support/Pebble SDK/SDKs/4.33.1'
os.environ['PATH'] = str(SDK / 'toolchain/bin') + os.pathsep + os.environ['PATH']
os.environ['PEBBLE_QEMU_PATH'] = str(SDK / 'toolchain/bin/qemu-pebble')
import png
from pebble_tool.commands.screenshot import ScreenshotCommand
from libpebble2.services.install import AppInstaller
from libpebble2.services.appmessage import AppMessageService, Int32, ByteArray, CString
from libpebble2.protocol.apps import AppRunState, AppRunStateStart, AppRunStateStop
from libpebble2.protocol.logs import AppLogMessage, AppLogShippingControl
from libpebble2.communication.transports.qemu.protocol import QemuButton
from pebble_tool.commands.emucontrol import send_data_to_qemu
import pebble_tool.sdk.emulator as emulator

ROOT = Path(__file__).resolve().parents[1]

def capture(slug, platform):
    face = ROOT if (ROOT / 'src/c').is_dir() else ROOT / 'appstores/pebble' / slug
    meta = json.loads((face / 'package.json').read_text())
    assert platform in meta['pebble']['targetPlatforms']
    pbw = face / 'build' / (slug + '.pbw')
    digest = hashlib.sha256(pbw.read_bytes()).hexdigest()
    app = UUID(meta['pebble']['uuid'])
    out = face / 'build/owner-review-native'
    out.mkdir(exist_ok=True)
    state = Path(tempfile.mkdtemp(prefix='owner-review-profile-', dir=face / 'build'))
    def persist(target, version=None):
        p = state / target
        p.mkdir(exist_ok=True)
        return str(p)
    emulator.get_sdk_persist_dir = persist
    emulator.get_emulator_info_path = lambda: str(state / 'emulators.json')
    emulator.get_default_account = lambda: SimpleNamespace(is_logged_in=False)
    bridge = (out / (platform + '-bridge.log')).open('w')
    emulator.ManagedEmulatorTransport._get_output = lambda self: bridge
    cmd = ScreenshotCommand()
    cmd._set_debugging(0)
    def shutdown():
        info = emulator.get_emulator_info(platform, '4.33.1')
        if info:
            for key in ('qemu', 'pypkjs', 'websockify'):
                pid = info.get(key, {}).get('pid')
                if not pid:
                    continue
                found = subprocess.run(['ps', '-p', str(pid), '-o', 'command='], capture_output=True, text=True)
                if found.returncode == 0 and str(state / platform) not in found.stdout:
                    raise RuntimeError('Refusing to stop a process outside this profile')
        cmd._shutdown_platform_emulator(platform, '4.33.1')
    watch = None
    logs, frames = [], []
    try:
        watch = cmd._connect_emulator(platform, '4.33.1')
        cmd.pebble = watch
        handle = watch.register_endpoint(AppLogMessage, lambda packet: logs.append(str(packet.message)))
        watch.send_packet(AppLogShippingControl(enable=True))
        service = AppMessageService(watch)
        keys = meta['pebble'].get('messageKeys', {})
        if isinstance(keys, list) and keys:
            # The SDK allocates automatic keys from 10000, not zero.
            generated = (face / 'build/src/message_keys.auto.c').read_text()
            keys = {key: int(value) for key, value in re.findall(r'uint32_t MESSAGE_KEY_(\w+) = (\d+);', generated)}
        elif isinstance(keys, list):
            keys = {}
        def send(values):
            wire = {keys[k]: ByteArray(v) if isinstance(v, bytes) else Int32(v) if isinstance(v, int) else CString(v) for k, v in values.items()}
            service.send_message(app, wire)
            time.sleep(.3)
        day = dt.datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        def at(h, m=0, s=0, days=0):
            return day + dt.timedelta(days=days, hours=h, minutes=m, seconds=s)
        def epoch(value):
            return int(value.timestamp())
        def fixture(clock, variant=0):
            now = epoch(clock)
            if slug == 'planetary-hours':
                wire = bytearray(72)
                offset = int(-day.astimezone().utcoffset().total_seconds() / 60)
                struct.pack_into('<BBBBIIIiI', wire, 0, 1, 1, 1, 0, epoch(at(5)), epoch(at(5)), epoch(at(6, days=2)), offset, 3)
                for i, days in enumerate((-1, 0, 1)):
                    rise = at(6, days=days)
                    struct.pack_into('<IIII', wire, 24 + i * 16, epoch(rise), epoch(at(18, days=days)), epoch(at(6, days=days+1)), (rise.weekday()+1) % 7)
                send({'DATA': bytes(wire)})
            elif slug == 'coast-almanac':
                send({'VARIANT': variant, 'STILL': 1, 'MODE': 1, 'UNITS': 0, 'STATION': 9411340, 'REVISION': variant+1})
                send({'REVISION': variant+1, 'WX_AT': now-600, 'TEMP_C10': 200, 'WIND_MS10': 40, 'CODE': 0,
                      'OBS_AT': now-300, 'HEIGHT_MM': 1200, 'SUN_AT': epoch(day), 'SUN_END': epoch(day)+86400,
                      'RISE': epoch(at(6)), 'SET': epoch(at(18)), 'POLAR': 0, 'SOUTH': 0})
                send({'REVISION': variant+1, 'CURVE_AT': epoch(day),
                      'CURVE': ','.join(str(round(1000+800*math.sin(i*math.pi/6))) for i in range(49)),
                      'EVENTS': ';'.join(str(epoch(at(h)))+','+str(height)+','+str(high)
                                         for h,height,high in [(3,1800,1),(9,200,0),(15,1800,1),(21,200,0)])})
            elif slug == 'fault-type':
                send({'MODE': 1, 'REVISION': 1})
                send({'MODE': 1, 'REVISION': 1, 'AT': now-60, 'UNTIL': now+7200, 'A': 42, 'B': 105, 'C': 99, 'TEXT': 'Synthetic test event'})
            elif slug == 'signals':
                send({'TEMP_UNIT': 0, 'PALETTE': variant, 'REFRESH_MINUTES': 30, 'WEATHER_VALID': 1,
                      'WEATHER_TEMP': 68, 'FEELS_TEMP': 66, 'WEATHER_CODE': 0, 'RAIN_CHANCE': 30,
                      'SUNRISE': epoch(at(6)), 'SUNSET': epoch(at(18)), 'WEATHER_UPDATED': now-600})
            elif slug == 'golden-hour':
                values = {'HAVE_FIX': 1, 'SUNRISE': epoch(at(6, 45)), 'SUNSET': epoch(at(18, 30))}
                for i, (start, end, kind) in enumerate([(at(6, 20), at(7, 20), 1), (at(18, 10), at(19, 10), 2), (at(6, 20, days=1), at(7, 20, days=1), 1)], 1):
                    values.update({'GOLDEN_START_'+str(i): epoch(start), 'GOLDEN_END_'+str(i): epoch(end), 'GOLDEN_KIND_'+str(i): kind})
                send(values)
            elif slug == 'neon':
                send({'VARIANT': variant, 'STILL': 1})
            elif slug == 'daisy-clock':
                send({'VARIANT': variant})
        args = argparse.Namespace(no_correction=True, scale=1, no_open=True, v=0)
        def grab(name, clock=None, use_fixture=True, variant=0):
            if clock:
                cmd._set_time(watch, clock)
                time.sleep(.35)
                cmd._set_time(watch, clock)
                watch.send_packet(AppRunState(data=AppRunStateStop(uuid=app)))
                time.sleep(.15)
                watch.send_packet(AppRunState(data=AppRunStateStart(uuid=app)))
                time.sleep(1.2 if slug != 'signals' else 3)
                if use_fixture:
                    fixture(clock, variant)
                time.sleep(.8)
            pixels = cmd._grab_processed_image(args, show_progress=False)
            file = out / (platform + '-' + name + '.png')
            png.from_array(pixels, mode='RGBA;8').save(str(file))
            frames.append(str(file.relative_to(face)))
        time.sleep(4)
        send_data_to_qemu(watch.transport, QemuButton(state=QemuButton.Button.Back))
        time.sleep(.1)
        send_data_to_qemu(watch.transport, QemuButton(state=0))
        AppInstaller(watch, str(pbw)).install()
        watch.send_packet(AppRunState(data=AppRunStateStart(uuid=app)))
        time.sleep(1.5)
        grab('offline', at(10, 8, 30), False)
        for name, clock in [('hero', at(10, 8, 30)), ('morning', at(6, 45, 15)), ('noon', at(12)), ('evening', at(18, 30, 30)), ('before-midnight', at(23, 59, 55))]:
            grab(name, clock)
        time.sleep(3)
        grab('midnight-rollover')
        for variant in range(1, {'neon': 2, 'coast-almanac': 4, 'signals': 3, 'daisy-clock': 7}.get(slug, 1)):
            grab('variant-'+str(variant), at(10, 8, 30), True, variant)
        assert hashlib.sha256(pbw.read_bytes()).hexdigest() == digest
        assert not any(any(term in line.lower() for term in ('hardfault', 'allocation failed', 'assertion failed', 'app crashed')) for line in logs), logs[-20:]
        report = {'face': slug, 'version': meta['version'], 'platform': platform, 'pbwSHA256': digest,
                  'capturedAt': dt.datetime.now(dt.timezone.utc).isoformat(), 'frames': frames, 'logs': logs,
                  'syntheticPhoneFixtures': slug in {'planetary-hours', 'coast-almanac', 'fault-type', 'signals', 'golden-hour'},
                  'passed': True, 'limitations': 'Native emulator captures. Source math is tested separately. Visual inspection and physical-watch acceptance are separate.'}
        (out / (platform+'-report.json')).write_text(json.dumps(report, indent=2)+'\n')
        print('CAPTURE', slug, platform, len(frames), 'frames', flush=True)
    finally:
        if watch:
            cmd._close_pebble_connection(watch)
            cmd.pebble = None
        shutdown()
        bridge.close()

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('face')
    parser.add_argument('platform')
    args = parser.parse_args()
    capture(args.face, args.platform)
