// Copyright 2026 Luke Steuber. MIT License.
#include <pebble.h>
#include "planetary.h"
static int max_int(int a,int b) { return a>b?a:b; }

static Window *s_window;
static Layer *s_layer;
static PHSchedule s_schedule;
static bool s_have_schedule,s_connected,s_refresh_failed;
static uint32_t s_last_request;
static uint8_t s_recovery_tries;
static const int PERSIST_SCHEDULE=701;
static GPoint s_points[12];
static GPath s_path={.points=s_points,.rotation=0,.offset={0,0}};
#ifdef PBL_COLOR
static const uint32_t s_rgb[7]={0x8a93a8,0xf5b441,0xff6b5c,0xffd06a,0x7ce0c0,0xaab6ff,0xcfe8ff};
#endif

static GPoint polar(int cx,int cy,int r,int angle) {
  return GPoint(cx+(int32_t)sin_lookup(angle)*r/TRIG_MAX_RATIO,
    cy-(int32_t)cos_lookup(angle)*r/TRIG_MAX_RATIO);
}
static void wedge(GContext *ctx,int cx,int cy,int radius,int index) {
  const int inner=radius*52/100;
  for(int k=0;k<5;k++) s_points[k]=polar(cx,cy,radius,(index*4+k)*TRIG_MAX_ANGLE/96);
  for(int k=0;k<5;k++) s_points[k+5]=polar(cx,cy,inner,(index*4+4-k)*TRIG_MAX_ANGLE/96);
  s_path.num_points=10;gpath_draw_filled(ctx,&s_path);
}
static GColor planet_color(int p) {
#ifdef PBL_COLOR
  return GColorFromHEX(s_rgb[p]);
#else
  (void)p;return GColorWhite;
#endif
}
#ifdef PBL_COLOR
static void soften(GContext *ctx,GRect b,int cx,int cy,int r) {
  static const uint8_t bayer[4][4]={{0,8,2,10},{12,4,14,6},{3,11,1,9},{15,7,13,5}};
  GBitmap *fb=graphics_capture_frame_buffer(ctx);if(!fb)return;
  int inner=r*52/100;
  for(int y=0;y<b.size.h;y++) {
    GBitmapDataRowInfo row=gbitmap_get_data_row_info(fb,y);
    for(int px=row.min_x;px<=row.max_x;px++) {
      int dx=px-cx,dy=y-cy,d=dx*dx+dy*dy;
      if(d<inner*inner || d>r*r)continue;
      uint8_t old=row.data[px],result=0xc0;int alpha=px>=cx?20:10;
      for(int channel=0;channel<3;channel++) {
        int value=((old>>(channel*2))&3)*85*alpha/100;
        value+=(channel==0?18:channel==1?9:4)*(100-alpha)/100;
        int base=value/85,remainder=value%85;
        if(remainder*16>bayer[y%4][px%4]*85 && base<3)base++;
        result|=(uint8_t)(base<<(channel*2));
      }
      row.data[px]=result;
    }
  }
  graphics_release_frame_buffer(ctx,fb);
}
#endif
static GPoint glyph_point(int cx,int cy,int scale,int x,int y) {
  return GPoint(cx+x*scale/10,cy+y*scale/10);
}
static void line(GContext *ctx,int cx,int cy,int scale,int x1,int y1,int x2,int y2) {
  graphics_draw_line(ctx,glyph_point(cx,cy,scale,x1,y1),glyph_point(cx,cy,scale,x2,y2));
}
static void circle(GContext *ctx,int cx,int cy,int scale,int dx,int dy,int radius) {
  graphics_draw_circle(ctx,glyph_point(cx,cy,scale,dx,dy),max_int(1,radius*scale/10));
}
static void symbol(GContext *ctx,int cx,int cy,int size,int planet,GColor ink,GColor paper) {
  graphics_context_set_stroke_color(ctx,ink);graphics_context_set_fill_color(ctx,ink);
  graphics_context_set_stroke_width(ctx,size>=16?2:1);
  switch(planet) {
    case 0: // Saturn: cross and hooked stem.
      line(ctx,cx,cy,size,-4,-9,-4,9);line(ctx,cx,cy,size,-8,-5,1,-5);
      line(ctx,cx,cy,size,-4,1,0,-2);line(ctx,cx,cy,size,0,-2,4,-1);
      line(ctx,cx,cy,size,4,-1,5,3);line(ctx,cx,cy,size,5,3,2,9);break;
    case 1: // Jupiter: curved upper stroke meeting the cross.
      line(ctx,cx,cy,size,-6,-5,-3,-8);line(ctx,cx,cy,size,-3,-8,1,-7);
      line(ctx,cx,cy,size,1,-7,2,-3);line(ctx,cx,cy,size,2,-3,-5,3);
      line(ctx,cx,cy,size,-5,3,7,3);line(ctx,cx,cy,size,5,-9,5,9);break;
    case 2:
      circle(ctx,cx,cy,size,-2,2,6);line(ctx,cx,cy,size,2,-2,8,-8);
      line(ctx,cx,cy,size,2,-8,8,-8);line(ctx,cx,cy,size,8,-8,8,-2);break;
    case 3:
      circle(ctx,cx,cy,size,0,0,8);graphics_fill_circle(ctx,GPoint(cx,cy),max_int(1,size/6));break;
    case 4:
      circle(ctx,cx,cy,size,0,-3,6);line(ctx,cx,cy,size,0,3,0,10);
      line(ctx,cx,cy,size,-4,7,4,7);break;
    case 5:
      circle(ctx,cx,cy,size,0,-1,5);line(ctx,cx,cy,size,0,4,0,10);
      line(ctx,cx,cy,size,-4,7,4,7);line(ctx,cx,cy,size,-5,-11,-4,-7);
      line(ctx,cx,cy,size,-4,-7,0,-6);line(ctx,cx,cy,size,0,-6,4,-7);
      line(ctx,cx,cy,size,4,-7,5,-11);break;
    case 6: // Crescent, facing the same way as the reference.
      graphics_fill_circle(ctx,GPoint(cx,cy),size);
      graphics_context_set_fill_color(ctx,paper);
      graphics_fill_circle(ctx,GPoint(cx-size*4/10,cy-size/10),size*9/10);break;
    default:break;
  }
  graphics_context_set_stroke_width(ctx,1);
}
static const char *fix_label(uint32_t now) {
  static char label[30];
  ph_fix_label(s_have_schedule?&s_schedule:NULL,now,s_refresh_failed || !s_connected,label,sizeof(label));
  return label;
}
static const char *state_label(uint32_t now,bool round) {
  if(!s_have_schedule) return round?"Needs phone":"Needs phone location";
  if(s_schedule.status==PH_NO_LOCATION) {
    if(s_schedule.error==1)return round?"Denied":"Location denied";
    if(s_schedule.error==3)return round?"Timed out":"Location timed out";
    if(s_schedule.error==2)return round?"Unavailable":"Location unavailable";
    if(s_schedule.error==4)return round?"Bad fix":"Invalid location fix";
    return round?"Needs phone":"Needs phone location";
  }
  if(now>=s_schedule.valid_until)return round?"Reconnect":"Reconnect phone";
  if(s_schedule.status==PH_POLAR_DAY)return "Polar day";
  if(s_schedule.status==PH_POLAR_NIGHT)return "Polar night";
  if(s_schedule.status==PH_SOLAR_GAP)return round?"No cycle":"Solar cycle unavailable";
  return fix_label(now);
}
static void text(GContext *ctx,const char *label,GRect bounds,GColor color,bool large) {
  graphics_context_set_text_color(ctx,color);
  graphics_draw_text(ctx,label,fonts_get_system_font(large?FONT_KEY_GOTHIC_18:FONT_KEY_GOTHIC_14),
    bounds,GTextOverflowModeTrailingEllipsis,GTextAlignmentCenter,NULL);
}
static void draw(Layer *layer,GContext *ctx) {
  time_t begin;uint16_t begin_ms;time_ms(&begin,&begin_ms);
  time_t epoch=time(NULL);struct tm tm=*localtime(&epoch);uint32_t now=(uint32_t)epoch;
  GRect b=layer_get_bounds(layer);bool round=PBL_IF_ROUND_ELSE(true,false);
  int cx=b.size.w/2,r=b.size.w/2-3,cy=round?b.size.h/2:r+2,inner=r*52/100;
  PHActive active=ph_active(s_have_schedule?&s_schedule:NULL,now);
  GColor background=GColorBlack;
  graphics_context_set_fill_color(ctx,background);graphics_fill_rect(ctx,b,0,GCornerNone);
  graphics_context_set_antialiased(ctx,true);
  if(active.hour>=0) {
#ifdef PBL_COLOR
    for(int i=0;i<24;i++) {
      graphics_context_set_fill_color(ctx,planet_color(ph_planet(active.weekday,i)));wedge(ctx,cx,cy,r,i);
    }
    soften(ctx,b,cx,cy,r);
#endif
    graphics_context_set_fill_color(ctx,planet_color(active.planet));wedge(ctx,cx,cy,r,active.hour);
    for(int i=0;i<24;i++) {
      GPoint p=polar(cx,cy,r*76/100,(i*2+1)*TRIG_MAX_ANGLE/48);
      int glyph_size=max_int(5,r*5/100);bool selected=i==active.hour;
      GColor ink=selected?GColorBlack:planet_color(ph_planet(active.weekday,i));
      symbol(ctx,p.x,p.y,glyph_size,ph_planet(active.weekday,i),ink,selected?planet_color(active.planet):background);
      graphics_context_set_stroke_color(ctx,PBL_IF_COLOR_ELSE(GColorBlack,GColorDarkGray));
      graphics_draw_line(ctx,polar(cx,cy,r*52/100,i*TRIG_MAX_ANGLE/24),polar(cx,cy,r,i*TRIG_MAX_ANGLE/24));
    }
    symbol(ctx,cx,cy-inner*20/100,max_int(11,inner*32/100),active.planet,planet_color(active.planet),background);
    char remaining[16];snprintf(remaining,sizeof(remaining),"%lum left",(unsigned long)((active.remaining+59)/60));
    text(ctx,remaining,GRect(cx-r/2,cy+inner*(round?10:14)/100,r,18),GColorWhite,false);
  } else {
    // No synthetic ruler is shown until a real solar cycle is available.
    graphics_context_set_stroke_color(ctx,PBL_IF_COLOR_ELSE(GColorDarkGray,GColorWhite));
    graphics_draw_circle(ctx,GPoint(cx,cy),r*52/100);
    text(ctx,state_label(now,true),GRect(cx-inner+2,cy-12,inner*2-4,20),GColorWhite,false);
    if(round)text(ctx,fix_label(now),GRect(cx-inner+2,cy+6,inner*2-4,18),GColorWhite,false);
  }
  graphics_context_set_stroke_color(ctx,PBL_IF_COLOR_ELSE(GColorDarkGray,GColorWhite));
  graphics_draw_circle(ctx,GPoint(cx,cy),r);
  const char *status=fix_label(now);
  char civil[9];strftime(civil,sizeof(civil),clock_is_24h_style()?"%H:%M":"%I:%M",&tm);
  if(round) {
    // Give "Saved 59m" and "Stale 171d" their full width. The visible glyphs
    // remain inside the inner disc even though the layout box is wider.
    if(active.hour>=0)text(ctx,status,GRect(cx-inner*80/100,cy+inner*36/100,inner*160/100,18),GColorWhite,false);
    text(ctx,civil,GRect(cx-26,cy-inner+2,52,18),GColorWhite,false);
  } else {
    char footer[40];snprintf(footer,sizeof(footer),"%s  %s",civil,status);
    text(ctx,footer,GRect(0,cy+r+1,b.size.w,b.size.h-cy-r),GColorWhite,false);
  }
  time_t end;uint16_t end_ms;time_ms(&end,&end_ms);
  APP_LOG(APP_LOG_LEVEL_INFO,"Planetary time=%02d:%02d:%02d status=%d active=%d mode=%d frame_ms=%ld free=%lu",
    tm.tm_hour,tm.tm_min,tm.tm_sec,s_have_schedule?s_schedule.status:0,active.hour,s_schedule.mode,
    (long)((end-begin)*1000+end_ms-begin_ms),(unsigned long)heap_bytes_free());
}
static void request(void) {
  uint32_t now=(uint32_t)time(NULL);
  if(!s_connected)return;
  if(s_last_request && now>=s_last_request && now-s_last_request<60)return;
  // Rate-limit failed outbox attempts too; a busy bridge must not spin at 1Hz.
  s_last_request=now;
  if(!ph_usable_data(s_have_schedule?&s_schedule:NULL,now) && s_recovery_tries<3)s_recovery_tries++;
  DictionaryIterator *iter;
  if(app_message_outbox_begin(&iter)!=APP_MSG_OK)return;
  dict_write_uint8(iter,MESSAGE_KEY_REQUEST,1);
  app_message_outbox_send();
}
static void inbox(DictionaryIterator *iter,void *context) {
  (void)context;Tuple *tuple=dict_find(iter,MESSAGE_KEY_DATA);PHSchedule candidate;
  uint32_t now=(uint32_t)time(NULL);
  if(!tuple || tuple->type!=TUPLE_BYTE_ARRAY || !ph_decode(tuple->value->data,tuple->length,now,&candidate) ||
    (s_have_schedule && candidate.generated<s_schedule.generated)) {
    APP_LOG(APP_LOG_LEVEL_WARNING,"Planetary schedule rejected");return;
  }
  if(candidate.status==PH_NO_LOCATION && s_have_schedule && s_schedule.status==PH_NORMAL && now<s_schedule.valid_until) {
    s_refresh_failed=true;APP_LOG(APP_LOG_LEVEL_INFO,"Planetary schedule accepted status=5 retained=1");
  } else {
    s_schedule=candidate;s_have_schedule=true;s_refresh_failed=false;
    int written=persist_write_data(PERSIST_SCHEDULE,tuple->value->data,PH_WIRE_SIZE);
    APP_LOG(APP_LOG_LEVEL_INFO,"Planetary schedule accepted status=%d count=%d persisted=%d",candidate.status,candidate.count,written==PH_WIRE_SIZE);
  }
  if(ph_usable_data(s_have_schedule?&s_schedule:NULL,now))s_recovery_tries=0;
  if(s_layer)layer_mark_dirty(s_layer);
}
static void connection(bool connected) {
  s_connected=connected;
  if(connected)request();
  if(s_layer)layer_mark_dirty(s_layer);
}
static void tick(struct tm *tm,TimeUnits changed) {
  (void)changed;if(s_layer)layer_mark_dirty(s_layer);
  if((tm->tm_min==0 && tm->tm_sec==0) || ph_retry_due(s_have_schedule?&s_schedule:NULL,
      (uint32_t)time(NULL),s_last_request,s_recovery_tries,s_connected))request();
}
static void load(Window *window) {
  s_layer=layer_create(layer_get_bounds(window_get_root_layer(window)));if(!s_layer)return;
  layer_set_update_proc(s_layer,draw);layer_add_child(window_get_root_layer(window),s_layer);
  tick_timer_service_subscribe(SECOND_UNIT,tick);
}
static void unload(Window *window) {
  (void)window;tick_timer_service_unsubscribe();if(s_layer)layer_destroy(s_layer);s_layer=NULL;
}
int main(void) {
  uint8_t wire[PH_WIRE_SIZE];
  if(persist_get_size(PERSIST_SCHEDULE)==PH_WIRE_SIZE && persist_read_data(PERSIST_SCHEDULE,wire,sizeof(wire))==PH_WIRE_SIZE)
    s_have_schedule=ph_decode(wire,sizeof(wire),(uint32_t)time(NULL),&s_schedule);
  s_window=window_create();if(!s_window)return 1;
  app_message_register_inbox_received(inbox);app_message_open(256,64);
  connection_service_subscribe((ConnectionHandlers){.pebble_app_connection_handler=connection});
  s_connected=connection_service_peek_pebble_app_connection();
  window_set_window_handlers(s_window,(WindowHandlers){.load=load,.unload=unload});
  window_stack_push(s_window,false);request();app_event_loop();
  connection_service_unsubscribe();app_message_deregister_callbacks();window_destroy(s_window);return 0;
}
