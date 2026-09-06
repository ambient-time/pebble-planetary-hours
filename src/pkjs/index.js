/* Copyright 2026 Luke Steuber. MIT License. */
'use strict';
var app = require('./phone')({pebble: Pebble, geo: navigator.geolocation,
  storage: localStorage, now: function() { return Date.now(); }, setTimeout: setTimeout});
Pebble.addEventListener('ready', app.refresh);
Pebble.addEventListener('appmessage', app.refresh);
