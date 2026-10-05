/* Copyright 2026 Luke Steuber. MIT License. */
'use strict';
var assert=require('assert'), create=require('../src/pkjs/phone');
var clock=Date.parse('2026-09-06T06:12:00Z'), tests=0;
function harness(stored) {
  var h={clock:clock,stored:stored||null,sends:[],timers:[],requests:0,writes:0};
  h.app=create({now:function(){return h.clock;},storage:{
    getItem:function(){if(h.storageError)throw Error('storage');return h.stored;},
    setItem:function(key,value){if(h.storageError)throw Error('storage');h.stored=value;h.writes++;}
  },geo:{getCurrentPosition:function(ok,fail,options){h.requests++;h.ok=ok;h.fail=fail;h.options=options;}},
  pebble:{sendAppMessage:function(data,ok,fail){h.sends.push({wire:Buffer.from(data.DATA),ok:ok,fail:fail});}},
  setTimeout:function(fn,delay){h.timers.push({fn:fn,delay:delay});}});
  h.fix=function(lat,lon,when){h.ok({coords:{latitude:lat,longitude:lon},timestamp:when===undefined?h.clock:when});};
  return h;
}
function check(fn){fn();tests++;}
check(function(){
  var h=harness();h.app.refresh();h.app.refresh();assert.strictEqual(h.requests,1);
  assert.deepStrictEqual(h.options,{enableHighAccuracy:false,timeout:15000,maximumAge:3600000});
  h.fix(37.7749,-122.4194);assert.strictEqual(h.writes,1);
  assert.strictEqual(h.sends[0].wire[1],1);assert.strictEqual(h.sends[0].wire[2],1);
  assert.strictEqual(h.sends[0].wire.readUInt32LE(8),clock/1000);
});
check(function(){
  var h=harness();h.app.refresh();h.fail({code:1});var w=h.sends[0].wire;
  assert.strictEqual(w[1],5);assert.strictEqual(w[2],0);assert.strictEqual(w[3],1);assert.strictEqual(w.readUInt32LE(8),0);
  assert.strictEqual(h.writes,0);
});
var cached=JSON.stringify({version:1,lat:37.7749,lon:-122.4194,capturedAt:clock-86400000});
check(function(){
  var h=harness(cached);h.app.refresh();h.fail({code:3});var w=h.sends[0].wire;
  assert.strictEqual(w[1],1);assert.strictEqual(w[2],2);assert.strictEqual(w[3],3);
  assert.strictEqual(w.readUInt32LE(8),(clock-86400000)/1000);assert.strictEqual(h.stored,cached);
});
['{bad','null',JSON.stringify({version:2,lat:0,lon:0,capturedAt:clock}),
  JSON.stringify({version:1,lat:999,lon:0,capturedAt:clock}),
  JSON.stringify({version:1,lat:0,lon:0,capturedAt:clock+3600000})].forEach(function(cache){
  check(function(){var h=harness(cache);h.app.refresh();h.fail({code:2});assert.strictEqual(h.sends[0].wire[1],5);});
});
check(function(){
  var h=harness(cached);h.app.refresh();h.fix(NaN,0);assert.strictEqual(h.sends[0].wire[2],2);
  assert.strictEqual(h.sends[0].wire[3],4);assert.strictEqual(h.writes,0);
});
check(function(){
  var h=harness();h.app.refresh();h.fix(0,0,clock+3600000);assert.strictEqual(h.sends[0].wire[1],5);
  assert.strictEqual(h.sends[0].wire[3],4);
});
check(function(){
  var h=harness();h.storageError=true;h.app.refresh();h.fix(-33.86,151.2);
  assert.strictEqual(h.sends[0].wire[1],1);assert.strictEqual(h.writes,0);
});
check(function(){
  var h=harness();h.app.refresh();h.fail({code:1});
  h.sends[0].fail();assert.strictEqual(h.timers.length,1);h.timers.shift().fn();
  h.sends[1].fail();assert.strictEqual(h.timers.length,1);h.timers.shift().fn();
  h.sends[2].fail();assert.strictEqual(h.sends.length,3);assert.strictEqual(h.timers.length,0);
});
check(function(){
  var h=harness();h.app.refresh();h.fail({code:1});h.app.refresh();h.fix(0,0);
  assert.strictEqual(h.sends.length,1);h.sends[0].fail();
  assert.strictEqual(h.sends.length,2);assert.strictEqual(h.sends[1].wire[1],1);h.sends[1].ok();
});
check(function(){
  var h=harness();h.app.refresh();h.fail({code:1});h.sends[0].fail();
  h.app.refresh();h.fix(0,0);h.timers.shift().fn();
  assert.strictEqual(h.sends[1].wire[1],1);h.sends[1].ok();
});
check(function(){
  process.env.TZ='America/Los_Angeles';var h=harness();h.app.refresh();h.fix(37.7749,-122.4194);h.sends[0].ok();
  var first=h.sends[0].wire;process.env.TZ='Asia/Tokyo';h.clock+=7200000;h.app.refresh();h.fix(35.6762,139.6503);
  var second=h.sends[1].wire;assert.notStrictEqual(first.readInt32LE(16),second.readInt32LE(16));
  assert.notStrictEqual(first.readUInt32LE(24),second.readUInt32LE(24));
  assert.strictEqual(second.readUInt32LE(8),h.clock/1000);
});
check(function(){
  var h=harness();h.app.refresh();h.fix(37.7749,-122.4194,clock-3600000);
  assert.strictEqual(h.sends[0].wire.readUInt32LE(8),(clock-3600000)/1000);
});
check(function(){
  var h=harness();h.app.refresh();h.fail({code:1});h.sends[0].ok();
  h.clock+=60000;h.app.refresh();h.fix(37.7749,-122.4194);
  assert.strictEqual(h.sends[1].wire[1],1);assert.strictEqual(h.sends[1].wire[3],0);
});
[
  ['2026-06-21T12:00:00Z',89,0,2],
  ['2026-12-21T12:00:00Z',89,0,3],
  ['2026-05-17T12:00:00Z',69.65,18.96,4]
].forEach(function(fixture){check(function(){
  process.env.TZ='UTC';var stamp=Date.parse(fixture[0]), captured=stamp-4104*3600000;
  var old=JSON.stringify({version:1,lat:fixture[1],lon:fixture[2],capturedAt:captured});
  var h=harness(old);h.clock=stamp;h.app.refresh();h.fail({code:3});
  var w=h.sends[0].wire;assert.strictEqual(w[1],fixture[3]);assert.strictEqual(w[2],2);
  assert.strictEqual(w[3],3);assert.strictEqual(w.readUInt32LE(8),captured/1000);
  assert.strictEqual(h.writes,0);assert.strictEqual(h.stored,old);
});});
[undefined, null, new Date(clock-60000)].forEach(function(stamp){check(function(){
  var h=harness();h.app.refresh();h.ok({coords:{latitude:37.7749,longitude:-122.4194},timestamp:stamp});
  assert.strictEqual(h.sends[0].wire[2],1);
  assert.strictEqual(h.sends[0].wire.readUInt32LE(8),stamp instanceof Date?(clock-60000)/1000:clock/1000);
});});
['bad',NaN,0].forEach(function(stamp){check(function(){
  var h=harness();h.app.refresh();h.ok({coords:{latitude:0,longitude:0},timestamp:stamp});
  assert.strictEqual(h.sends[0].wire[3],4);assert.strictEqual(h.writes,0);
});});
console.log('Planetary phone: '+tests+' mocked permission, cache, travel, transport and retry scenarios passed');
