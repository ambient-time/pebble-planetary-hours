# Planetary Hours for Pebble

Planetary Hours divides daylight and night into twelve parts each. The current ruler moves through the seven classical planets in Chaldean order. A planetary day starts at sunrise, so the hours before dawn still belong to the previous day.

Native Pebble watchface, version 0.1.1. Design and implementation by Luke Steuber, under the MIT license. This release candidate is ready for store preparation after the checks below.

## Reading the face

The wheel keeps the original 24 equal wedges, upright planetary symbols, highlighted current hour, and inner radius of 52%. Wedges represent successive planetary hours; their equal visual widths do not imply equal durations. The right half is daylight and the left half is night. The center shows the current planet and minutes remaining, rounded up.

Color screens use the source palette with a static dither for the dark wedges. Monochrome screens use white symbols and a white active wedge with a black symbol. The symbols are drawn with native lines and circles, without a downloaded font. Pebble's limited palette and pixel resolution replace the web face's smooth glow. Location status sits inside the center on round screens and below the wheel on rectangular screens. Version 0.1.1 removes the added civil-time display; planetary time and its remaining duration stay visible.

## Phone location and offline use

The phone requests a low-accuracy position when the companion starts and when the watch asks for a refresh. The watch asks at startup, on reconnection, and each hour, with at least a minute between requests. There is no default city, manual city, or remote solar service.

If the watch has no usable location data, it retries while connected: the first three attempts are a minute apart, then it waits five minutes between attempts. This lets a restored permission or recovered phone service take effect without waiting for the next hour. A usable normal, polar, or unavailable-cycle record ends this recovery cadence; regular hourly refreshes continue. Failed outbox attempts also count toward the rate limit.

The phone saves its last successful coordinates and their original timestamp locally. If a later request fails, it calculates from that saved position and preserves the timestamp. Only solar event times, the sunrise weekday, location age, and status cross to the watch; coordinates do not. No application server receives the location.

The small status label shows the source and the age of the original fix, rounded down: `Phone 2m`, `Saved 3h`, or `Stale 1d`. A fix becomes stale after six hours. Ages use minutes, hours, days, then years. Stale coordinates can still produce a schedule, but they may describe a place the wearer has left. Polar and unavailable-cycle screens retain the same age label.

The phone sends the current sunrise-to-sunrise cycle and up to two following cycles in one message. The watch validates the entire message before replacing its schedule and saves it as one persistent record. An incomplete or older message cannot partially replace a good schedule. If location is unavailable but the watch still has a usable normal schedule, the watch retains that schedule and marks it saved. When the final supplied sunrise passes, the wheel stops showing a ruler and asks for a phone refresh.

With no location, the watch says `Needs phone`. Permission denial, timeouts, invalid fixes, and unavailable location have separate labels. Polar day, polar night, and a missing neighboring sunrise are shown as conditions, not converted into invented twelve-hour day/night periods. On a round watch, `No cycle` means a complete sunrise-to-sunrise cycle could not be calculated.

The solar equations come from the supplied original. Events are absolute UTC instants, rounded to the nearest second for transport. The planet order uses the phone's local weekday at the sunrise that begins each cycle. This handles midnight, daylight-saving transitions, and dates near the international date line without assuming each local day is 86,400 seconds. The phone's timezone must describe the intended civil calendar; coordinates alone do not provide a timezone. A refreshed phone fix updates the schedule after travel. The calculation does not account for local terrain or unusual atmospheric refraction.

## Build and test

Requires Pebble SDK 4.33.1, a compatible `pebble` CLI, Node.js, and a C compiler with AddressSanitizer and UndefinedBehaviorSanitizer. The checked-in PNG is the build input; ImageMagick is needed only to regenerate it from the included SVG.

```sh
make build
make icon  # optional: regenerate the 25×25 menu icon
```

Targets: basalt, diorite, emery, flint, chalk, and gabbro. The face refreshes once per second. It does not subscribe to the accelerometer or continuously request location. Frame logs include civil time, zero-based active hour (`-1` when unavailable), status, mode, drawing duration, and remaining heap. Drawing duration uses watch wall time; changing the clock during a fixture can distort that measurement.

`make test` runs the native boundary and decoder tests with sanitizers, 907 source/schedule comparisons, and 20 mocked phone scenarios. The solar suite covers both hemispheres, DST, leap day, year rollover, date-line locations, polar transitions, and invalid inputs. Phone tests cover permission failures and recovery, saved data, malformed cache, travel, bounded transport retries, and preserving the original fix timestamp. Recovery timing and very old fix labels also have native tests, including polar and missing-cycle records with a 4,104-hour-old location. After building, `make build` also runs the bundled companion's actual entry point to check startup, watch requests, denial, permission recovery, and saved-position delivery.

The native evidence runner and package validator are separate:

```sh
# Use the Python environment installed with pebble-tool (libpebble2 and pypng).
python test/package.py
python -m unittest discover -s test -p '*_test.py'
python test/emulator.py chalk --fresh
python test/package.py --evidence build/evidence
python test/source-rebuild.py
```

The SDK names the PBW after the checkout folder. The package validator resolves that name, including when the source ZIP is imported into a differently named folder. `--evidence` requires matching native captures for all six platforms and produces a local PBW/source ZIP review kit. It verifies every capture's dimensions and SHA-256, rejection and restart pixel comparisons, seven rulers, and natural sunrise, sunset, and midnight transitions. The source ZIP includes the reference, tests, icon source, and build inputs; it excludes build caches and captured evidence. The independent rebuild extracts that ZIP, runs the build checks again, and compares native code, resources, and the bundled phone companion.

The emulator installs the native payload from the unchanged production PBW directly. Its phone bridge has no registered companion bundle, so live emulator location cannot overwrite the fixtures. Captures cover explicit sunrise boundaries and a schedule calculated by the shipped solar code for a supplied test position. The phone companion also runs separately in a mocked host environment. Physical-phone permission behavior and real geolocation delivery still need a device check, as do outdoor readability and battery life. This version logs each native draw for diagnosis.

## Message contract

UUID: `70cc559e-2c8d-4b47-acec-46f1dce646c8`. Keys: `REQUEST=0`, `DATA=1`. `DATA` is one 72-byte, little-endian byte array. Schema version is 1.

| Offset | Field |
| --- | --- |
| 0–3 | Four bytes: version, status, location mode, error |
| 4, 8, 12 | Unsigned 32-bit generation time, original fix time, validity end |
| 16 | Signed 32-bit phone timezone offset in minutes, JavaScript convention |
| 20 | Unsigned 32-bit cycle count, zero to three |
| 24, 40, 56 | Four unsigned 32-bit fields per cycle: sunrise, sunset, next sunrise, Sunday-based weekday |

Status: 1 normal, 2 polar day, 3 polar night, 4 no complete solar cycle, 5 no location. Mode: 0 none, 1 phone, 2 saved. Error: 0 none, 1 denied, 2 unavailable, 3 timeout, 4 invalid fix. Unused cycle slots are zero. Non-normal records contain no cycles and expire after six hours. Native validation also checks event ordering and continuity, weekday range, generation time, location-source status, and validity bounds. It does not assume weekdays always advance by one: a sunrise close to civil midnight can move into the next calendar date.

For an explicit phone fixture:

```sh
TZ=America/Los_Angeles node test/fixtures.js 2026-09-06T06:12:00Z 37.7749 -122.4194 stale
```

This prints the schedule and its exact `DATA` payload. Its default coordinates are test fixtures only, not an application fallback.
