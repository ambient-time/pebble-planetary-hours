/* Copyright 2026 Luke Steuber. MIT License.
 * Solar terms and sunrise equation from the supplied Planetary Hours source.
 * Events use UTC instants; the ruler's weekday uses the phone's civil timezone.
 */
'use strict';
var DEG = Math.PI / 180, DAY = 86400000, WIRE_SIZE = 72;
function finite(v) { return typeof v === 'number' && isFinite(v); }
function coordinates(lat, lon) {
  return finite(lat) && finite(lon) && lat >= -90 && lat <= 90 && lon >= -180 && lon <= 180;
}
function terms(date) {
  var jd = date.getTime() / DAY + 2440587.5, T = (jd - 2451545) / 36525;
  var L0 = (280.46646 + T * (36000.76983 + T * 0.0003032)) % 360;
  if (L0 < 0) L0 += 360;
  var M = 357.52911 + T * (35999.05029 - 0.0001537 * T);
  var e = 0.016708634 - T * (0.000042037 + 0.0000001267 * T), mr = M * DEG;
  var C = Math.sin(mr) * (1.914602 - T * (0.004817 + 0.000014 * T)) +
    Math.sin(2 * mr) * (0.019993 - 0.000101 * T) + Math.sin(3 * mr) * 0.000289;
  var omega = 125.04 - 1934.136 * T;
  var lambda = L0 + C - 0.00569 - 0.00478 * Math.sin(omega * DEG);
  var seconds = 21.448 - T * (46.815 + T * (0.00059 - T * 0.001813));
  var obliq = (23 + (26 + seconds / 60) / 60 + 0.00256 * Math.cos(omega * DEG)) * DEG;
  var decl = Math.asin(Math.sin(obliq) * Math.sin(lambda * DEG)) / DEG;
  var y = Math.tan(obliq / 2); y *= y;
  var lr = L0 * DEG;
  var eq = 4 / DEG * (y * Math.sin(2 * lr) - 2 * e * Math.sin(mr) +
    4 * e * y * Math.sin(mr) * Math.cos(2 * lr) - 0.5 * y * y * Math.sin(4 * lr) -
    1.25 * e * e * Math.sin(2 * mr));
  return {declination: decl, equationOfTime: eq, longitude: (lambda % 360 + 360) % 360};
}
function events(date, lat, lon) {
  if (!coordinates(lat, lon) || !finite(date.getTime())) throw new Error('Invalid solar input');
  var day = Date.UTC(date.getUTCFullYear(), date.getUTCMonth(), date.getUTCDate());
  var t = terms(new Date(day + DAY / 2)), dec = t.declination * DEG, phi = lat * DEG;
  var cosH = (Math.sin(-0.833 * DEG) - Math.sin(phi) * Math.sin(dec)) / (Math.cos(phi) * Math.cos(dec));
  if (cosH < -1) return {status: 2};
  if (cosH > 1) return {status: 3};
  if (!finite(cosH)) return {status: 4};
  var h = Math.acos(cosH) / DEG, noon = 720 - 4 * lon - t.equationOfTime;
  return {status: 1, rise: day + (noon - 4 * h) * 60000, set: day + (noon + 4 * h) * 60000};
}
function epoch(ms) {
  var n = Math.round(ms / 1000);
  if (!finite(ms) || n < 1 || n > 4294967295) throw new Error('Time outside supported range');
  return n;
}
function schedule(now, fix, mode, error) {
  var stamp = now.getTime(), generated = epoch(stamp);
  var out = {version: 1, status: 5, mode: 0, error: error || 0, generated: generated,
    fix: 0, validUntil: generated + 21600, timezone: now.getTimezoneOffset(), cycles: []};
  if (!fix) return out;
  if (!coordinates(fix.lat, fix.lon) || !finite(fix.capturedAt) || fix.capturedAt > stamp + 300000) {
    throw new Error('Invalid location fix');
  }
  out.fix = epoch(fix.capturedAt); out.mode = mode === 2 ? 2 : 1;
  var base = Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate()), pairs = [];
  for (var d = -3; d <= 5; d++) pairs.push(events(new Date(base + d * DAY), fix.lat, fix.lon));
  for (var i = 0; i < pairs.length - 1; i++) {
    var p = pairs[i], next = pairs[i + 1];
    if (p.status !== 1 || next.status !== 1 || !(epoch(p.rise) <= generated && generated < epoch(next.rise))) continue;
    for (var j = i; j < pairs.length - 1 && out.cycles.length < 3; j++) {
      p = pairs[j]; next = pairs[j + 1];
      if (p.status !== 1 || next.status !== 1 || !(p.rise < p.set && p.set < next.rise)) break;
      out.cycles.push({rise: epoch(p.rise), set: epoch(p.set), nextRise: epoch(next.rise),
        weekday: new Date(p.rise).getDay()});
    }
    if (out.cycles.length) {
      out.status = 1; out.validUntil = out.cycles[out.cycles.length - 1].nextRise;
      return out;
    }
  }
  // Around a polar transition, a missing neighboring event is not a 24-hour day.
  out.status = events(now, fix.lat, fix.lon).status;
  if (out.status === 1) out.status = 4;
  return out;
}
function encode(s) {
  var bytes = [], i;
  for (i = 0; i < WIRE_SIZE; i++) bytes.push(0);
  function put(offset, value) {
    value = value >>> 0;
    for (var b = 0; b < 4; b++) bytes[offset + b] = (value >>> (b * 8)) & 255;
  }
  bytes[0] = 1; bytes[1] = s.status; bytes[2] = s.mode; bytes[3] = s.error;
  put(4, s.generated); put(8, s.fix); put(12, s.validUntil); put(16, s.timezone); put(20, s.cycles.length);
  s.cycles.forEach(function(c, n) {
    var o = 24 + n * 16; put(o, c.rise); put(o + 4, c.set); put(o + 8, c.nextRise); put(o + 12, c.weekday);
  });
  return bytes;
}
module.exports = {terms: terms, events: events, schedule: schedule, encode: encode, coordinates: coordinates};
