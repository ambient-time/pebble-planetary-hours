# Source reference

`source.html` is the HTML of my original [Planetary Hours](https://datapoems.io/clocks/planetary-hours/)
web clock. It is kept for provenance and numerical comparison; the Pebble
watchface does not load it.

Source SHA-256: `80c6dff4a2799a42e53ada54cb5de60cc29ed17368aa970c3ab2b4c5c368ea51`.

The native port keeps the 24 equal-angle sectors, the 52% inner radius, the
seven planetary colors and symbols, Chaldean order, and the unequal division
of daylight and night. It uses the original solar equations, choosing the
sunrise cycle by absolute time and the planet order by the phone's weekday at
sunrise. The web clock's default city is not used: location comes from the
phone, with a clearly labeled last good fix, and polar conditions are shown as
they are. Custom drawn symbols, fixed dithering and short status text adapt the
web rendering to Pebble.

Copyright 2026 Luke Steuber. MIT License; see the project license.
