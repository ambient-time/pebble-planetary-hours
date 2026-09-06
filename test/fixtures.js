/* Copyright 2026 Luke Steuber. MIT License. */
'use strict';
var solar = require('../src/pkjs/solar');
// Usage: TZ=America/Los_Angeles node test/fixtures.js ISO LAT LON [phone|saved|stale|denied|timeout|missing]
var args = process.argv.slice(2), date = new Date(args[0] || '2026-09-06T06:12:00Z');
var mode = args[3] || 'phone', fix = {lat: Number(args[1] || 37.7749), lon: Number(args[2] || -122.4194), capturedAt: date.getTime()};
if (mode === 'stale') fix.capturedAt -= 86400000;
if (mode === 'saved') fix.capturedAt -= 3600000;
var nofix = ['missing', 'denied', 'timeout'].indexOf(mode) >= 0;
var error = mode === 'denied' ? 1 : mode === 'timeout' ? 3 : mode === 'saved' || mode === 'stale' ? 2 : 0;
var s = solar.schedule(date, nofix ? null : fix, mode === 'phone' ? 1 : 2, error);
console.log(JSON.stringify({nowEpoch: Math.floor(date.getTime() / 1000), localTime: date.toString(),
  schedule: s, payload: {DATA: solar.encode(s)}}, null, 2));
