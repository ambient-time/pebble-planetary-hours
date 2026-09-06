"""Native Planetary screenshots; isolated persistent profiles, no physical watches.

Run with the installed pebble-tool Python after pebble build.
"""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import time
import tempfile
import subprocess
import struct
from uuid import UUID
from types import SimpleNamespace

SDK=Path.home()/'Library/Application Support/Pebble SDK/SDKs/current'
toolchain=str(SDK.resolve()/'toolchain/bin')
os.environ.setdefault('PEBBLE_QEMU_PATH',toolchain+'/qemu-pebble')
os.environ['PATH']=toolchain+os.pathsep+os.environ['PATH']
import png
from pebble_tool.commands.screenshot import ScreenshotCommand
from libpebble2.services.install import AppInstaller
from libpebble2.protocol.apps import AppRunState,AppRunStateStart,AppRunStateStop
from libpebble2.services.appmessage import AppMessageService, ByteArray
from libpebble2.protocol.logs import AppLogMessage,AppLogShippingControl
import pebble_tool.sdk.emulator as emulator
from libpebble2.communication.transports.qemu.protocol import QemuButton
from pebble_tool.commands.emucontrol import send_data_to_qemu

ROOT=Path(__file__).resolve().parent.parent
PBW=ROOT/'build'/f'{ROOT.name}.pbw' # The SDK uses the checkout folder's name.
APP=UUID('70cc559e-2c8d-4b47-acec-46f1dce646c8')

def run(platform,fresh=False):
    out=ROOT/'build/evidence';out.mkdir(exist_ok=True)
    state=Path(tempfile.mkdtemp(prefix='emulator-fresh-',dir=ROOT/'build')) if fresh else ROOT/'build/emulator-state'
    state.mkdir(exist_ok=True)
    # AppInstaller sends native resources from the production PBW straight to
    # the watch. The emulator phone must not have a cached copy that would also
    # start the bundled JS and race these explicitly synthetic DATA fixtures.
    cached=state/platform/'app_cache'/f'{APP}.pbw'
    if cached.exists():
        raise RuntimeError('This profile contains a phone-side bundle. Run with --fresh to isolate fixtures.')
    def persist(target,version=None):
        p=state/target;p.mkdir(exist_ok=True);return str(p)
    emulator.get_sdk_persist_dir=persist
    emulator.get_emulator_info_path=lambda:str(state/'emulators.json')
    emulator.get_default_account=lambda:SimpleNamespace(is_logged_in=False)
    bridge_log=(out/f'{platform}-bridge.log').open('w')
    emulator.ManagedEmulatorTransport._get_output=lambda self:bridge_log
    cmd=ScreenshotCommand();cmd._set_debugging(0)
    def shutdown():
        info=emulator.get_emulator_info(platform,emulator.sdk_manager.get_current_sdk())
        if info:
            for key in ('qemu','pypkjs','websockify'):
                pid=info.get(key,{}).get('pid')
                if not pid:continue
                process=subprocess.run(['ps','-p',str(pid),'-o','command='],capture_output=True,text=True)
                if process.returncode==0 and str(state/platform) not in process.stdout:
                    raise RuntimeError(f'Refusing to stop PID {pid}: it no longer belongs to this test profile.')
        cmd._shutdown_platform_emulator(platform,None)
    # Only this test's private profile: clear a bridge left by interrupted runs.
    shutdown()
    try:
        watch=cmd._connect_emulator(platform,None);cmd.pebble=watch
    except BaseException:
        shutdown();bridge_log.close()
        raise
    service=AppMessageService(watch)
    keys=json.loads((ROOT/"package.json").read_text())["pebble"]["messageKeys"]
    logs=[];frames=[];frame_hashes={}
    def log(packet):
        logs.append(str(packet.message));print(str(packet.message),flush=True)
    handle=watch.register_endpoint(AppLogMessage,log)
    watch.send_packet(AppLogShippingControl(enable=True))
    args=argparse.Namespace(no_correction=True,scale=1,no_open=True,v=0)
    def grab(name,clock=None):
        if clock:
            target=clock
            h,m,s=target.hour,target.minute,target.second
            expected=f'time={h:02d}:{m:02d}:{s:02d}'
            data=None
            for attempt in range(3):
                start=len(logs)
                cmd._set_time(watch,target-datetime.timedelta(seconds=1))
                deadline=time.monotonic()+4
                while not any(expected in line for line in logs[start:]) and time.monotonic()<deadline:
                    time.sleep(.02)
                if not any(expected in line for line in logs[start:]):continue
                time.sleep(.03)
                candidate=cmd._grab_processed_image(args,show_progress=False)
                native=[line for line in logs[start:] if 'Planetary time=' in line]
                if native and expected in native[-1]:
                    data=candidate
                    break
            assert data is not None,f'Watch did not capture exact requested time {h:02d}:{m:02d}:{s:02d}'
        else:
            data=cmd._grab_processed_image(args,show_progress=False)
        file=out/f'{platform}-{name}.png';png.from_array(data,mode='RGBA;8').save(str(file))
        frames.append(str(file.relative_to(ROOT)))
        frame_hashes[file.name]=hashlib.sha256(file.read_bytes()).hexdigest()
        return data
    try:
        time.sleep(4)
        send_data_to_qemu(watch.transport,QemuButton(state=QemuButton.Button.Back))
        time.sleep(.2)
        send_data_to_qemu(watch.transport,QemuButton(state=0))
        time.sleep(.5)
        grab('boot')
        AppInstaller(watch,str(PBW)).install()
        watch.send_packet(AppRunState(data=AppRunStateStart(uuid=APP)))
        time.sleep(2)
        # Synthetic, explicit phone-message fixtures. No real geolocation is requested.
        day=datetime.datetime.now().replace(hour=0,minute=0,second=0,microsecond=0)
        def at(hour,minute=0,second=0,days=0):
            return day+datetime.timedelta(days=days,hours=hour,minutes=minute,seconds=second)
        def epoch(dt):return int(dt.timestamp())
        generation=epoch(at(5))
        def payload(status=1,mode=1,error=0,generated=None,fix=None):
            g=generation if generated is None else generated
            f=epoch(at(5)) if fix is None else fix
            data=bytearray(72)
            count=3 if status==1 else 0
            until=epoch(at(6,days=2)) if status==1 else g+21600
            if status==5:mode=0;f=0
            offset=int(-at(5).astimezone().utcoffset().total_seconds()/60)
            struct.pack_into('<BBBBIIIiI',data,0,1,status,mode,error,g,f,until,offset,count)
            if count:
                for index,days in enumerate((-1,0,1)):
                    rise=at(6,days=days)
                    weekday=(rise.weekday()+1)%7
                    struct.pack_into('<IIII',data,24+index*16,epoch(rise),epoch(at(18,days=days)),
                                     epoch(at(6,days=days+1)),weekday)
            return data
        def deliver(data,expected='accepted'):
            begin=len(logs)
            service.send_message(APP,{keys['DATA']:ByteArray(bytes(data))})
            deadline=time.monotonic()+5
            while not any('schedule '+expected in line for line in logs[begin:]) and time.monotonic()<deadline:
                time.sleep(.05)
            assert any('schedule '+expected in line for line in logs[begin:]),'No native '+expected+' response'
        begin=len(logs)
        grab('waiting',at(5))
        assert any('status=0 active=-1' in line for line in logs[begin:]),'Initial state received unexpected phone data'
        deliver(payload(status=5,error=1))
        grab('denied')
        generation+=1
        deliver(payload())
        # Seven successive active rulers, with the source's equal-angle wheel.
        for index in range(7):
            first=len(logs)
            grab('ruler-'+str(index),at(6+index,15))
            assert any(f'active={index} ' in line for line in logs[first:]),'Wrong planetary-hour slot'
        hero=grab('hero',at(9,24,20))
        # Partial and obsolete data must not replace the accepted solar schedule.
        deliver(payload()[:-1],'rejected')
        assert grab('partial-rejected',at(9,24,20))==hero,'Partial data changed the face'
        old=payload(generated=generation-1)
        deliver(old,'rejected')
        assert grab('older-rejected',at(9,24,20))==hero,'Obsolete data changed the face'
        generation+=1
        deliver(payload(mode=2,error=1))
        saved=grab('saved',at(9,24,20))
        watch.send_packet(AppRunState(data=AppRunStateStop(uuid=APP)))
        time.sleep(.5)
        watch.send_packet(AppRunState(data=AppRunStateStart(uuid=APP)))
        time.sleep(1)
        restored=grab('restart-saved',at(9,24,20))
        assert saved==restored,'Restart did not preserve the saved-location face'
        grab('stale',at(14))
        for name,before,expected,slot in [('sunrise',at(5,59,58),'time=06:00:',0),
                                        ('sunset',at(17,59,58),'time=18:00:',12),
                                        ('midnight',at(23,59,58),'time=00:00:',18)]:
            grab('before-'+name,before)
            begin=len(logs);deadline=time.monotonic()+5
            while not any(expected in line for line in logs[begin:]) and time.monotonic()<deadline:
                time.sleep(.05)
            assert any(expected in line for line in logs[begin:]),'No natural '+name+' transition'
            assert any(expected in line and f'active={slot} ' in line for line in logs[begin:]),'Wrong slot after '+name
            grab(name+'-rollover')
        grab('expired',at(12,days=3))
        generation=epoch(at(12,days=3))
        for name,status in [('polar-day',2),('polar-night',3),('solar-gap',4)]:
            generation+=1
            deliver(payload(status=status,mode=2,generated=generation,fix=generation-3600))
            grab(name)
        # Feed a schedule from the shipped solar implementation through the real
        # AppMessage decoder too. Coordinates here are explicit test input.
        solar_time=at(13,24,20,days=3)
        # SetUTC is asynchronous; wait for a native draw before sending a
        # generation timestamp more than five minutes ahead of the prior pose.
        grab('await-phone-solar',solar_time)
        fixture=json.loads(subprocess.check_output([
            'node',str(ROOT/'test/fixtures.js'),solar_time.astimezone().isoformat(),
            '37.7749','-122.4194','phone'],text=True))
        plan=fixture['schedule'];cycle=plan['cycles'][0]
        current=epoch(solar_time)
        if current<cycle['set']:
            expected_slot=(current-cycle['rise'])*12//(cycle['set']-cycle['rise'])
        else:
            expected_slot=12+(current-cycle['set'])*12//(cycle['nextRise']-cycle['set'])
        assert cycle['set']-cycle['rise']!=cycle['nextRise']-cycle['set'],'Expected unequal solar periods'
        deliver(bytearray(fixture['payload']['DATA']))
        first=len(logs)
        grab('phone-solar',solar_time)
        assert any(f'active={expected_slot} ' in line for line in logs[first:]),'Wrong slot for phone solar schedule'
        old_fix=bytearray(fixture['payload']['DATA']);old_fix[2]=2
        struct.pack_into('<I',old_fix,4,current+1)
        struct.pack_into('<I',old_fix,8,current-171*86400)
        deliver(old_fix)
        grab('very-old-fix',solar_time)
        assert any('Planetary time=' in line for line in logs),'No native app frame log'
        assert not any('crash' in line.lower() or 'fault' in line.lower() for line in logs),'Native fault logged'
        report={'platform':platform,'pbwSHA256':hashlib.sha256(PBW.read_bytes()).hexdigest(),
                'capturedAt':datetime.datetime.now(datetime.timezone.utc).isoformat(),
                'nativeMessages':True,'phoneCompanionIsolated':True,'invalidRejected':True,'restartRetained':True,
                'sevenRulers':True,'phoneSolarSchedule':True,'naturalSunriseRollover':True,'naturalSunsetRollover':True,'naturalMidnightRollover':True,
                'frames':frames,'frameSHA256':frame_hashes,'logs':logs,
                'limits':'Isolated emulator with synthetic AppMessage schedules. No physical phone location or permission test. Frames require visual inspection; no physical-watch battery/readability evidence.'}
        (out/f'{platform}-report.json').write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps(report,indent=2),flush=True)
    finally:
        service.shutdown()
        watch.unregister_endpoint(handle);cmd._close_pebble_connection(watch);cmd.pebble=None
        shutdown();bridge_log.close()

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('platform',choices=['emery','diorite','basalt','flint','chalk','gabbro'])
    parser.add_argument('--fresh',action='store_true',help='Use a new isolated profile; preserve existing flash images.')
    args=parser.parse_args()
    run(args.platform,args.fresh)
