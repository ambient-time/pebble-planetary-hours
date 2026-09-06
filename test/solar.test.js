/* Copyright 2026 Luke Steuber. MIT License. */
'use strict';
var assert = require('assert'), fs = require('fs'), vm = require('vm'), path = require('path');
var solar = require('../src/pkjs/solar');
var html = fs.readFileSync(path.join(__dirname, '../reference/source.html'), 'utf8');
var start = html.indexOf('(function (root) {', html.indexOf('/* Astro:'));
var end = html.indexOf('</script>', start), sandbox = {};
vm.runInNewContext(html.slice(start, end), sandbox);
var original = sandbox.Astro, checks = 0;
function near(a,b) { assert(Math.abs(a-b)<1.1, a+' versus '+b); checks++; }
var places = [[37.7749,-122.4194],[-33.86,151.2],[0,0],[64.14,-21.94],
  [1.87,-157.4],[-13.76,-172.1],[66.5,25],[89,0],[-89,0],[0,180],[0,-180]];
var dates = ['2026-03-20','2026-06-21','2026-09-22','2026-12-21','2028-02-29','2038-01-20','2026-12-31'];
dates.forEach(function(iso) {
  var d = new Date(iso+'T12:00:00Z'), a = solar.terms(d), b = original.solarTerms(d);
  Object.keys(a).forEach(function(k) { assert(Math.abs(a[k]-b[k])<1e-10); checks++; });
  places.forEach(function(p) {
    var e = solar.events(d,p[0],p[1]), rise = original.sunrise(d,p[0],p[1]), set = original.sunset(d,p[0],p[1]);
    if (rise) { near(e.rise,rise.getTime()); near(e.set,set.getTime()); }
    else assert(e.status===2 || e.status===3);
  });
});
var zones = ['America/Los_Angeles','Pacific/Kiritimati','Pacific/Apia','Asia/Kolkata','Europe/London','UTC'];
zones.forEach(function(zone) {
  process.env.TZ=zone;
  ['2026-03-08T09:59:00Z','2026-03-08T10:01:00Z','2026-11-01T08:59:00Z','2026-11-01T09:01:00Z',
    '2026-01-01T00:01:00Z','2028-02-29T23:59:00Z'].forEach(function(iso) {
    var d = new Date(iso);
    places.slice(0,7).forEach(function(p) {
      var plan = solar.schedule(d,{lat:p[0],lon:p[1],capturedAt:d.getTime()},1,0);
      if(plan.status!==1) { assert([2,3,4].indexOf(plan.status)>=0);return; }
      assert(plan.cycles.length>0 && plan.cycles.length<=3);
      assert(plan.cycles[0].rise<=plan.generated && plan.generated<plan.cycles[0].nextRise);
      plan.cycles.forEach(function(c,i) {
        assert(c.rise<c.set && c.set<c.nextRise);
        assert.strictEqual(c.weekday,new Date(c.rise*1000).getDay());
        if(i)assert.strictEqual(plan.cycles[i-1].nextRise,c.rise);
        checks++;
      });
      assert.strictEqual(plan.validUntil,plan.cycles[plan.cycles.length-1].nextRise);
      var wire = solar.encode(plan);assert.strictEqual(wire.length,72);
      assert(wire.every(function(v) { return Number.isInteger(v) && v>=0 && v<=255; }));
      assert.strictEqual(Buffer.from(wire).readInt32LE(16),d.getTimezoneOffset());
      // The rounded sunrise is the single boundary shared by both phone and watch.
      var next = plan.cycles[0].nextRise;
      [-1,0,1].forEach(function(delta) {
        var n = new Date((next+delta)*1000), s = solar.schedule(n,{lat:p[0],lon:p[1],capturedAt:n.getTime()},1,0);
        assert.strictEqual(s.cycles[0].rise,delta<0?plan.cycles[0].rise:next);
      });
    });
  });
});
process.env.TZ='America/Los_Angeles';
var beforeSunrise = new Date('2026-09-06T12:00:00Z');
var previous = solar.schedule(beforeSunrise,{lat:37.7749,lon:-122.4194,capturedAt:beforeSunrise.getTime()},1,0);
assert.strictEqual(beforeSunrise.getDay(),0);assert.strictEqual(previous.cycles[0].weekday,6);
process.env.TZ='UTC';
var crossing=new Date('2026-01-01T12:00:00Z');
var discontinuity=solar.schedule(crossing,{lat:0,lon:90,capturedAt:+crossing},1,0);
assert.strictEqual(discontinuity.cycles[0].weekday,3);
assert.strictEqual(discontinuity.cycles[1].weekday,5);
assert.strictEqual(solar.events(new Date('2026-06-21'),90,0).status,2);
assert.strictEqual(solar.events(new Date('2026-12-21'),90,0).status,3);
assert.strictEqual(solar.events(new Date('2026-06-21'),-90,0).status,3);
var gapFound = false;
for(var day=1;day<=31;day++) {
  var date=new Date(Date.UTC(2026,4,day,12)), plan=solar.schedule(date,{lat:69.65,lon:18.96,capturedAt:date.getTime()},1,0);
  if(plan.status===4)gapFound=true;
}
assert(gapFound,'Polar transition must not fabricate an unequal-hour cycle');
[[NaN,0],[Infinity,0],[91,0],[0,181],['37',0]].forEach(function(p) {
  assert.throws(function() { solar.events(new Date(),p[0],p[1]); });
});
assert.throws(function() { solar.events(new Date('invalid'),0,0); });
assert.throws(function() { solar.schedule(new Date(),{lat:0,lon:0,capturedAt:Date.now()+3600000},1,0); });
var missing=solar.schedule(new Date('2026-09-06'),null,0,1);
assert.strictEqual(missing.status,5);assert.strictEqual(missing.fix,0);assert.strictEqual(missing.cycles.length,0);
console.log('Planetary solar: '+checks+' source and schedule checks passed; DST, date line, leap day, polar and invalid-input checks passed');
