// Copyright 2026 Luke Steuber. MIT License.
#include <assert.h>
#include <stdio.h>
#include "../src/c/planetary.h"
static void put(uint8_t *w,int off,uint32_t value) {
  for(int b=0;b<4;b++)w[off+b]=(uint8_t)(value>>(b*8));
}
static void fixture(uint8_t *w,uint32_t rise,int weekday) {
  memset(w,0,PH_WIRE_SIZE);w[0]=1;w[1]=1;w[2]=1;
  put(w,4,rise+3600);put(w,8,rise+3000);put(w,12,rise+3*86400);
  put(w,16,420);put(w,20,3);
  for(int i=0;i<3;i++) {
    int off=24+16*i;put(w,off,rise+i*86400);put(w,off+4,rise+i*86400+14*3600);
    put(w,off+8,rise+(i+1)*86400);put(w,off+12,(weekday+i)%7);
  }
}
int main(void) {
  uint8_t w[PH_WIRE_SIZE],bad[PH_WIRE_SIZE];PHSchedule s;
  const uint32_t rise=1788670800u;
  fixture(w,rise,6);assert(ph_decode(w,sizeof(w),rise+3600,&s));
  assert(s.timezone==420 && s.count==3 && s.fix==rise+3000);
  assert(ph_active(&s,rise-1).hour==-1);
  for(int day=0;day<3;day++) {
    uint32_t start=rise+day*86400;
    for(int hour=0;hour<24;hour++) {
      uint32_t base=hour<12?start:start+14*3600;
      uint32_t span=hour<12?14*3600:10*3600;
      uint32_t boundary=base+(uint64_t)(hour%12)*span/12;
      PHActive a=ph_active(&s,boundary);
      assert(a.hour==hour && a.planet==ph_planet((6+day)%7,hour));
      assert(a.remaining==span/12);
      if(hour)assert(ph_active(&s,boundary-1).hour==hour-1);
    }
  }
  assert(ph_active(&s,rise+3*86400).hour==-1);
  assert(ph_planet(0,0)==3 && ph_planet(1,0)==6 && ph_planet(6,0)==0);
  for(int d=0;d<7;d++)for(int h=0;h<24;h++)assert(ph_planet(d,h)==(ph_planet(d,0)+h)%7);
  assert(ph_planet(-1,0)==-1 && ph_planet(7,0)==-1 && ph_planet(0,24)==-1);
  // Reject malformed messages without changing the destination value.
  assert(!ph_decode(w,71,rise+3600,&s));assert(!ph_decode(NULL,72,rise+3600,&s));
  const int offsets[]={0,1,2,3,4,8,12,16,20,24,28,32,36,40,52};
  const uint32_t values[]={2,6,3,5,0,0,rise+6*86400,9999,4,rise+14*3600,rise,rise,7,rise+1,7};
  for(size_t i=0;i<sizeof(offsets)/sizeof(offsets[0]);i++) {
    memcpy(bad,w,sizeof(w));
    if(offsets[i]<4)bad[offsets[i]]=(uint8_t)values[i];else put(bad,offsets[i],values[i]);
    PHSchedule old=s;assert(!ph_decode(bad,sizeof(bad),rise+3600,&s));assert(!memcmp(&s,&old,sizeof(s)));
  }
  assert(!ph_decode(w,sizeof(w),rise,&s)); // Generation more than five minutes ahead.
  memcpy(bad,w,sizeof(w));put(bad,52,1); // A real sunrise may cross civil midnight.
  assert(ph_decode(bad,sizeof(bad),rise+3600,&s));
  assert(ph_active(&s,rise+86400).planet==ph_planet(1,0));
  for(int state=2;state<=5;state++) {
    memset(bad,0,sizeof(bad));bad[0]=1;bad[1]=state;bad[2]=state==5?0:2;
    put(bad,4,rise);put(bad,8,state==5?0:rise-7200);put(bad,12,rise+21600);
    assert(ph_decode(bad,sizeof(bad),rise,&s));assert(ph_active(&s,rise+1).hour==-1);
    put(bad,24,1);assert(!ph_decode(bad,sizeof(bad),rise,&s));
  }
  // Seconds beyond signed 32-bit time remain valid on the wire and in the math.
  fixture(w,2200000000u,0);assert(ph_decode(w,sizeof(w),2200003600u,&s));
  assert(ph_active(&s,2200000000u).hour==0);
  // Unequal periods need not divide evenly into twelve integer seconds.
  fixture(w,rise,0);put(w,28,rise+14*3600+7);assert(ph_decode(w,sizeof(w),rise+3600,&s));
  uint32_t previous=0;
  for(uint32_t t=rise;t<rise+86400;t++) {
    PHActive a=ph_active(&s,t);assert(a.hour>=0 && a.hour<=23 && a.remaining>0);
    assert((uint32_t)a.hour>=previous);previous=(uint32_t)a.hour;
  }
  s.cycles[0].set=s.cycles[0].rise;assert(ph_active(&s,rise).hour==-1);
  s.count=255;assert(ph_active(&s,rise).hour==-1);
  // Failed first-time location retries briefly at one minute, then every five.
  assert(ph_retry_due(NULL,rise,0,0,true));
  assert(!ph_retry_due(NULL,rise+59,rise,1,true));
  assert(ph_retry_due(NULL,rise+60,rise,1,true));
  assert(!ph_retry_due(NULL,rise+299,rise,3,true));
  assert(ph_retry_due(NULL,rise+300,rise,3,true));
  assert(!ph_retry_due(NULL,rise+3600,rise,3,false));
  fixture(w,rise,6);assert(ph_decode(w,sizeof(w),rise+3600,&s));
  assert(ph_usable_data(&s,rise+3600));
  assert(!ph_retry_due(&s,rise+3600,rise,3,true));
  assert(ph_retry_due(&s,rise+3*86400,rise,3,true));
  s.status=PH_NO_LOCATION;assert(ph_retry_due(&s,rise+300,rise,3,true));
  char label[30];ph_fix_label(NULL,rise,false,label,sizeof(label));assert(!strcmp(label,"No location"));
  for(int state=PH_POLAR_DAY;state<=PH_SOLAR_GAP;state++) {
    s.status=state;s.count=0;s.fix=rise-4104u*3600;s.valid_until=rise+21600;s.mode=2;
    assert(ph_usable_data(&s,rise));assert(!ph_retry_due(&s,rise+3600,rise,3,true));
    ph_fix_label(&s,rise,false,label,sizeof(label));assert(!strcmp(label,"Stale 171d"));
    assert(strlen(label)<=10);
  }
  s.fix=rise-7*3600;ph_fix_label(&s,rise,false,label,sizeof(label));assert(!strcmp(label,"Stale 7h"));
  s.fix=rise-3*3600;ph_fix_label(&s,rise,false,label,sizeof(label));assert(!strcmp(label,"Saved 3h"));
  s.mode=1;ph_fix_label(&s,rise,false,label,sizeof(label));assert(!strcmp(label,"Phone 3h"));
  s.fix=1;ph_fix_label(&s,rise,false,label,sizeof(label));assert(strlen(label)<=10);
  puts("Planetary native math: boundary sweep, seven rulers, wire rejection and overflow checks passed");
  return 0;
}
