# Source reference

`source.html` is Luke Steuber's supplied Planetary Hours HTML. The reference is retained for provenance and numerical comparison; it is not loaded by the Pebble watchface.

Original route: [Planetary Hours](https://datapoems.io/clocks/planetary-hours/). Supplied screenshot: `CleanShot 2026-09-05 at 23.12.15@2x.png`. The screenshot is a visual reference, not a claim about native Pebble output.

Source SHA-256: `80c6dff4a2799a42e53ada54cb5de60cc29ed17368aa970c3ab2b4c5c368ea51`.

The native port preserves the 24 equal-angle sectors, 52% inner radius, seven planetary colors and symbols, Chaldean order, and unequal daylight/night division. It uses the original Astro solar equations with absolute sunrise-cycle selection and the phone's sunrise weekday. The source's default city is not used. Location comes from the phone, with an explicitly labeled last-good cache; polar conditions remain explicit. Native custom symbols, static dithering, and compact status text adapt the web rendering to Pebble.

Copyright 2026 Luke Steuber. MIT License; see the project license.
