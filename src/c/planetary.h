// Copyright 2026 Luke Steuber. MIT License.
#ifndef PLANETARY_H
#define PLANETARY_H
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <string.h>
#include <stdio.h>
#define PH_WIRE_SIZE 72
#define PH_STALE_SECONDS 21600u
enum { PH_NORMAL=1, PH_POLAR_DAY, PH_POLAR_NIGHT, PH_SOLAR_GAP, PH_NO_LOCATION };
typedef struct { uint32_t rise,set,next_rise,weekday; } PHCycle;
typedef struct {
  uint8_t status,mode,error,count;
  uint32_t generated,fix,valid_until;
  int32_t timezone;
  PHCycle cycles[3];
} PHSchedule;
typedef struct { int hour,planet,weekday; uint32_t remaining; } PHActive;
static uint32_t ph_u32(const uint8_t *p) {
  return (uint32_t)p[0]|((uint32_t)p[1]<<8)|((uint32_t)p[2]<<16)|((uint32_t)p[3]<<24);
}
static bool ph_decode(const uint8_t *wire,size_t size,uint32_t now,PHSchedule *out) {
  if(!wire || !out || size!=PH_WIRE_SIZE || wire[0]!=1) return false;
  PHSchedule s; memset(&s,0,sizeof(s));
  s.status=wire[1];s.mode=wire[2];s.error=wire[3];
  s.generated=ph_u32(wire+4);s.fix=ph_u32(wire+8);s.valid_until=ph_u32(wire+12);
  s.timezone=(int32_t)ph_u32(wire+16);
  uint32_t count=ph_u32(wire+20);
  if(s.status<PH_NORMAL || s.status>PH_NO_LOCATION || s.mode>2 || s.error>4 || count>3 ||
    s.timezone < -840 || s.timezone > 840 || !s.generated ||
    (uint64_t)s.generated > (uint64_t)now+300 || s.valid_until<=s.generated ||
    (uint64_t)s.valid_until>(uint64_t)s.generated+4*86400) return false;
  s.count=(uint8_t)count;
  if(s.status==PH_NO_LOCATION) {
    if(s.mode!=0 || s.fix!=0 || count!=0) return false;
  } else if(!s.mode || !s.fix || (uint64_t)s.fix>(uint64_t)s.generated+300) return false;
  if((s.status==PH_NORMAL)!=(count>0)) return false;
  for(uint32_t i=0;i<3;i++) {
    const uint8_t *p=wire+24+i*16;
    PHCycle c={ph_u32(p),ph_u32(p+4),ph_u32(p+8),ph_u32(p+12)};
    if(i>=count) { if(c.rise||c.set||c.next_rise||c.weekday) return false; continue; }
    if(c.weekday>6 || !c.rise || c.rise>=c.set || c.set>=c.next_rise ||
      c.next_rise-c.rise>2*86400 || c.set-c.rise<12 || c.next_rise-c.set<12) return false;
    // Sunrise can cross civil midnight in the phone's timezone. Validate each
    // supplied weekday independently rather than inventing a +1 calendar rule.
    if(i && c.rise!=s.cycles[i-1].next_rise) return false;
    s.cycles[i]=c;
  }
  if(count && (s.cycles[0].rise>s.generated || s.cycles[0].next_rise<=s.generated ||
    s.valid_until!=s.cycles[count-1].next_rise)) return false;
  *out=s;return true;
}
static PHActive ph_active(const PHSchedule *s,uint32_t now) {
  PHActive a={-1,-1,-1,0};
  static const uint8_t start[7]={3,6,2,5,1,4,0};
  if(!s || s->status!=PH_NORMAL || s->count>3 || now>=s->valid_until) return a;
  for(int i=0;i<s->count;i++) {
    const PHCycle *c=&s->cycles[i];
    if(c->weekday>6 || c->rise>=c->set || c->set>=c->next_rise) return a;
    if(now<c->rise || now>=c->next_rise) continue;
    bool day=now<c->set;uint32_t begin=day?c->rise:c->set,end=day?c->set:c->next_rise;
    uint32_t span=end-begin,part=(uint32_t)((uint64_t)(now-begin)*12/span);
    a.hour=(int)part+(day?0:12);a.weekday=c->weekday;a.planet=(start[c->weekday]+a.hour)%7;
    a.remaining=begin+(uint32_t)(((uint64_t)(part+1)*span+11)/12)-now;
    return a;
  }
  return a;
}
static int ph_planet(int weekday,int hour) {
  static const uint8_t start[7]={3,6,2,5,1,4,0};
  return weekday<0||weekday>6||hour<0||hour>23 ? -1 : (start[weekday]+hour)%7;
}
static bool ph_usable_data(const PHSchedule *s,uint32_t now) {
  if(!s || now>=s->valid_until)return false;
  if(s->status==PH_NORMAL)return ph_active(s,now).hour>=0;
  return s->status>=PH_POLAR_DAY && s->status<=PH_SOLAR_GAP;
}
static bool ph_retry_due(const PHSchedule *s,uint32_t now,uint32_t last,uint8_t tries,bool connected) {
  if(!connected || ph_usable_data(s,now))return false;
  uint32_t delay=tries<3?60:300;
  return !last || now<last || now-last>=delay;
}
static void ph_fix_label(const PHSchedule *s,uint32_t now,bool saved,char *label,size_t size) {
  if(!s || !s->fix) { snprintf(label,size,"No location");return; }
  uint32_t age=now>=s->fix?now-s->fix:0;
  bool stale=now<s->fix || age>PH_STALE_SECONDS;
  char unit=age>=365*86400u?'y':age>=86400?'d':age>=3600?'h':'m';
  uint32_t count=age/(unit=='y'?365*86400u:unit=='d'?86400:unit=='h'?3600:60);
  const char *source=stale?"Stale":s->mode==2 || saved?"Saved":"Phone";
  snprintf(label,size,"%s %lu%c",source,(unsigned long)count,unit);
}
#endif
