/* Copyright 2026 Luke Steuber. MIT License. */
'use strict';
var solar = require('./solar');
var CACHE = 'planetary-hours.location.v1';
function companion(env) {
  var busy = false, sending = false, pending = null, attempts = 0;
  function now() { return env.now(); }
  function valid(f) {
    return f && f.version === 1 && solar.coordinates(f.lat, f.lon) &&
      typeof f.capturedAt === 'number' && isFinite(f.capturedAt) &&
      f.capturedAt > 0 && f.capturedAt <= now() + 300000;
  }
  function saved() {
    try { var f = JSON.parse(env.storage.getItem(CACHE)); return valid(f) ? f : null; }
    catch (e) { return null; }
  }
  function pump() {
    if (sending || !pending) return;
    sending = true;
    var item = pending; pending = null;
    env.pebble.sendAppMessage({DATA: item}, function() {
      sending = false; attempts = 0; pump();
    }, function() {
      sending = false;
      // Keep the newest update if one arrived while the previous send was busy.
      if (pending) { attempts = 0; pump(); return; }
      if (++attempts >= 3) { attempts = 0; return; }
      pending = item; sending = true;
      env.setTimeout(function() { sending = false; pump(); }, attempts * 1500);
    });
  }
  function deliver(f, mode, error) {
    var plan = solar.schedule(new Date(now()), f, mode, error);
    pending = solar.encode(plan); pump();
  }
  function failure(code) { busy = false; var f = saved(); deliver(f, f ? 2 : 0, code); }
  function refresh() {
    if (busy) return;
    busy = true;
    if (!env.geo || typeof env.geo.getCurrentPosition !== 'function') { failure(2); return; }
    try {
      env.geo.getCurrentPosition(function(p) {
        var f = {version: 1, lat: p && p.coords && p.coords.latitude,
          lon: p && p.coords && p.coords.longitude, capturedAt: p && p.timestamp};
        if (!valid(f)) { failure(4); return; }
        busy = false;
        try { env.storage.setItem(CACHE, JSON.stringify(f)); } catch (e) { /* The current fix still works. */ }
        deliver(f, 1, 0);
      }, function(e) { failure(e && e.code >= 1 && e.code <= 3 ? e.code : 2); },
      {enableHighAccuracy: false, timeout: 15000, maximumAge: 3600000});
    } catch (e) { failure(2); }
  }
  return {refresh: refresh};
}
module.exports = companion;
