/* Copyright 2026 Luke Steuber. MIT License. */
'use strict';
// Exercise the built companion entry point, including its event registrations.
var assert = require('assert'), fs = require('fs'), vm = require('vm');
var file = process.argv[2] || 'build/pebble-js-app.js';
var events = {}, messages = [], saved = null, requests = 0, ok, fail;
var stamp = Date.parse('2026-09-06T16:24:20Z');
class Clock extends Date {
  constructor(value) { super(arguments.length ? value : stamp); }
  static now() { return stamp; }
}
var context = {
  console: console, Date: Clock,
  Pebble: {
    addEventListener: function(name, callback) { events[name] = callback; },
    removeEventListener: function() {},
    sendAppMessage: function(data, success) { messages.push(Buffer.from(data.DATA)); success(); }
  },
  localStorage: {
    getItem: function() { return saved; },
    setItem: function(key, value) { saved = value; }
  },
  navigator: {geolocation: {getCurrentPosition: function(success, failure, options) {
    requests++; ok = success; fail = failure;
    assert.strictEqual(options.enableHighAccuracy, false);
    assert.strictEqual(options.timeout, 15000);
  }}},
  setTimeout: function() { throw new Error('Unexpected transport retry'); }
};
vm.runInNewContext(fs.readFileSync(file, 'utf8'), context, {filename: file});
assert.deepStrictEqual(Object.keys(events).sort(), ['appmessage', 'ready']);
events.ready();
fail({code: 1});
assert.strictEqual(messages[0][1], 5);
assert.strictEqual(messages[0][3], 1);
assert.strictEqual(saved, null);
events.appmessage({payload: {REQUEST: 1}});
ok({coords: {latitude: 37.7749, longitude: -122.4194}, timestamp: stamp});
assert.strictEqual(messages[1].length, 72);
assert.strictEqual(messages[1][1], 1);
assert.strictEqual(messages[1][2], 1);
assert.strictEqual(messages[1].readUInt32LE(20), 3);
var fixed = messages[1].readUInt32LE(8);
stamp += 7 * 3600000;
events.appmessage({payload: {REQUEST: 1}});
fail({code: 3});
assert.strictEqual(messages[2][1], 1);
assert.strictEqual(messages[2][2], 2);
assert.strictEqual(messages[2].readUInt32LE(8), fixed);
assert.strictEqual(requests, 3);
console.log('Planetary built companion: ready/request wiring, denial, permission recovery and saved fix passed');
