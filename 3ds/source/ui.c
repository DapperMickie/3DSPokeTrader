#include "ui.h"
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
UiScreen ui_top={.width=400},ui_bottom={.width=320};
typedef struct { int advance,w,h,x,y; const unsigned char *data; } Glyph;
typedef struct { int ascent,height; Glyph glyph[95]; } Font;
static Font fonts[4];
static unsigned char *art,*font_data;
static size_t art_size;
static UiScreen *screen;
#define NAVY 0x384858u
#define MUTED 0x607080u
#define CREAM 0xF8F8E8u
#define MINT 0xB8E088u
#define CORAL 0xF8B870u
#define WHITE 0xFFFFFFu
static unsigned read32(const unsigned char *p) { return p[0]|p[1]<<8|p[2]<<16|(unsigned)p[3]<<24; }
static unsigned char *file(const char *dir,const char *name,size_t *size) {
    char path[1024]; snprintf(path,sizeof(path),"%s/%s",dir,name);
    FILE *f=fopen(path,"rb"); if(!f) return NULL;
    if(fseek(f,0,SEEK_END)) { fclose(f); return NULL; }
    long n=ftell(f); if(n<12 || n>4000000) { fclose(f); return NULL; }
    rewind(f); unsigned char *p=malloc((size_t)n);
    if(!p || fread(p,1,(size_t)n,f)!=(size_t)n) { free(p); fclose(f); return NULL; }
    fclose(f); *size=(size_t)n; return p;
}
void ui_close(void) { free(art); free(font_data); art=NULL; font_data=NULL; }
int ui_init(const char *directory) {
    size_t n=0; art=file(directory,"art.bin",&art_size); font_data=file(directory,"font.bin",&n);
    if(!art || !font_data || memcmp(art,"PTART01\0",8) || read32(art+8)!=772 || art_size<12+772*8 || memcmp(font_data,"PTFONT1\0",8) || read32(font_data+8)!=4) goto fail;
    for(int i=0;i<772;i++) { unsigned off=read32(art+12+i*8),len=read32(art+16+i*8); if(off>art_size || len>art_size-off || len%3) goto fail; }
    size_t pos=12;
    for(int i=0;i<4;i++) {
        if(pos+2>n) goto fail;
        fonts[i].ascent=font_data[pos++]; fonts[i].height=font_data[pos++];
        for(int j=0;j<95;j++) {
            if(pos+5>n) goto fail;
            Glyph *g=&fonts[i].glyph[j]; g->advance=font_data[pos++]; g->w=font_data[pos++]; g->h=font_data[pos++];
            g->x=(int8_t)font_data[pos++]; g->y=(int8_t)font_data[pos++];
            size_t bytes=(size_t)g->w*g->h; if(bytes>n-pos) goto fail;
            g->data=font_data+pos; pos+=bytes;
        }
    }
    return 0;
fail: ui_close(); return -1;
}
static void pixel(int x,int y,unsigned c,int a) {
    if(x<0 || y<0 || x>=screen->width || y>=240) return;
    unsigned char *p=screen->pixels+(y*screen->width+x)*3;
    for(int i=0;i<3;i++) p[i]=(unsigned char)((p[i]*(255-a)+((c>>(16-i*8))&255)*a)/255);
}
static void rect(int x,int y,int w,int h,unsigned c) { for(int j=y;j<y+h;j++) for(int i=x;i<x+w;i++) pixel(i,j,c,255); }
static void circle(int x,int y,int r,unsigned c) { for(int j=-r;j<=r;j++) for(int i=-r;i<=r;i++) if(i*i+j*j<=r*r) pixel(x+i,y+j,c,255); }
/* Square, stepped frames match the GBA menus and remain crisp at 1x. */
static void card(int x,int y,int w,int h,unsigned c) {
    rect(x+2,y,w-4,h,NAVY); rect(x,y+2,w,h-4,NAVY);
    rect(x+2,y+2,w-4,h-4,WHITE); rect(x+4,y+4,w-8,h-8,c);
}
static void cursor_frame(int x,int y,int w,int h) {
    unsigned red=0xD84838u;
    rect(x,y,10,3,red); rect(x,y,3,9,red);
    rect(x+w-10,y,10,3,red); rect(x+w-3,y,3,9,red);
    rect(x,y+h-3,10,3,red); rect(x,y+h-9,3,9,red);
    rect(x+w-10,y+h-3,10,3,red); rect(x+w-3,y+h-9,3,9,red);
}
static int width(const char *s,int f) { int n=0; for(;*s;s++) n+=fonts[f].glyph[(*s>=32 && *s<=126?*s:'?')-32].advance; return n; }
static void text(int x,int y,const char *s,int f,unsigned c,int max) {
    int start=x;
    for(;*s;s++) {
        Glyph *g=&fonts[f].glyph[(*s>=32 && *s<=126?*s:'?')-32];
        if(x+g->advance>start+max) break;
        for(int j=0;j<g->h;j++) for(int i=0;i<g->w;i++) pixel(x+g->x+i,y+fonts[f].ascent+g->y+j,c,g->data[j*g->w+i]);
        x+=g->advance;
    }
}
static void wrap(int x,int y,const char *s,int max,int lines,int skip,unsigned c) {
    char line[256]; int used=0,row=0;
    while(*s && row<skip+lines) {
        const char *end=s; while(*end && *end!=' ' && *end!='\n') end++;
        int len=(int)(end-s); if(len>120) len=120;
        char word[122]; memcpy(word,s,(size_t)len); word[len]=0;
        if(used && width(line,1)+width(word,1)+4>max) {
            if(row>=skip) text(x,y+(row-skip)*18,line,1,c,max);
            row++; used=0;
        }
        if(used) line[used++]=' ';
        if(used+len>=255) len=254-used;
        memcpy(line+used,s,(size_t)len); used+=len; line[used]=0; s+=len;
        if(*s=='\n') { if(row>=skip && row<skip+lines) text(x,y+(row-skip)*18,line,1,c,max); row++; used=0; s++; }
        else if(*s==' ') s++;
    }
    if(used && row>=skip && row<skip+lines) text(x,y+(row-skip)*18,line,1,c,max);
}
static void ball(int x,int y,int r,unsigned c) { circle(x,y,r,c); rect(x-r,y-2,2*r,4,NAVY); circle(x,y,r/3,NAVY); circle(x,y,r/6,CREAM); }
static void base(const char *section,const char *mode) {
    screen=&ui_top; rect(0,0,400,240,0x6898C8u);
    for(int y=0;y<240;y+=8) rect(0,y,400,3,0x80B0D8u);
    rect(0,0,400,36,0x3868A0u); rect(0,34,400,3,NAVY);
    ball(22,18,10,0xF87858u); text(40,8,"POKETRADER",2,WHITE,180);
    int demo=mode && (strstr(mode,"demo") || strstr(mode,"DEMO"));
    const char *badge=demo?"DEMO MODE":mode && *mode?"BRIDGE ONLINE":"FIRE / LEAF";
    text(251,12,badge,0,demo?0xF8D868u:WHITE,145);
    card(8,44,384,162,CREAM);
    rect(8,212,384,22,0x3868A0u); text(18,215,section,0,WHITE,365);
    screen=&ui_bottom; rect(0,0,320,240,0x80A8C8u);
    for(int y=0;y<240;y+=8) rect(0,y,320,3,0x98B8D0u);
    card(5,4,310,203,CREAM);
}
static void button(int x,int y,int w,const char *s,unsigned color) { card(x,y,w,30,color); text(x+(w-width(s,1))/2,y+6,s,1,NAVY,w-8); }
static void sprite(int dex,int shiny,int x,int y,int size) {
    if(dex<1 || dex>386) { ball(x+size/2,y+size/2,size/5,MUTED); return; }
    int index=dex-1+(shiny?386:0); unsigned off=read32(art+12+index*8),len=read32(art+16+index*8);
    uint16_t pixels[4096]={0}; unsigned pos=0;
    for(unsigned i=off;i<off+len;i+=3) { unsigned run=art[i],c=art[i+1]|art[i+2]<<8; if(run>4096-pos) return; while(run--) pixels[pos++]=(uint16_t)c; }
    for(int j=0;j<size;j++) for(int i=0;i<size;i++) { unsigned c=pixels[(j*64/size)*64+i*64/size]; if(c&0x8000) pixel(x+i,y+j,((c>>10&31)*255/31<<16)|((c>>5&31)*255/31<<8)|((c&31)*255/31),255); }
}
int ui_parse_pokemon(const char *line,UiPokemon *p) {
    char fields[14][128]; memset(p,0,sizeof(*p));
    for(int i=0;i<14;i++) {
        const char *end=strchr(line,'\t'); size_t n=end?(size_t)(end-line):strlen(line);
        if(n>=128 || (i<13 && !end) || (i==13 && end)) return -1;
        memcpy(fields[i],line,n); fields[i][n]=0; line=end?end+1:line+n;
    }
    int *values[]={&p->index,&p->dex,&p->shiny,&p->eligible,&p->level,&p->kind};
    for(int i=0;i<6;i++) { char *end; long v=strtol(fields[i],&end,10); if(!fields[i][0] || *end || v<0 || v>419) return -1; *values[i]=(int)v; }
    if(p->dex>386 || p->shiny>1 || p->eligible>1 || p->level>100 || p->kind>3) return -1;
    char *out[]={p->type[0],p->type[1],p->name,p->nickname,p->trainer,p->tid,p->nature,p->reason};
    size_t sizes[]={16,16,32,32,32,12,24,128};
    for(int i=0;i<8;i++) { if(strlen(fields[i+6])>=sizes[i]) return -1; strcpy(out[i],fields[i+6]); }
    return 0;
}
void ui_browser(const char *path,const UiEntry *entries,int count,int cursor) {
    base("01  /  CHOOSE A SAVE",NULL); screen=&ui_top;
    text(24,57,"WELCOME TO THE",3,NAVY,355); text(24,87,"POKEMON CABLE CLUB!",3,NAVY,355);
    wrap(24,139,"Choose a FireRed or LeafGreen save.\nEmulator save or exported VC save.\nClose the game before you continue.",350,4,0,NAVY);
    screen=&ui_bottom; text(14,8,"Save files",2,NAVY,200); text(14,33,path,0,MUTED,290);
    int first=cursor/4*4;
    for(int i=first;i<count && i<first+4;i++) {
        int y=53+(i-first)*35; card(10,y,300,31,i==cursor?MINT:WHITE);
        if(entries[i].directory) { rect(21,y+11,17,12,MUTED); rect(21,y+7,9,5,MUTED); }
        else { card(21,y+6,16,20,CORAL); rect(25,y+8,8,5,CREAM); }
        text(48,y+6,entries[i].name,1,NAVY,241);
    }
    if(!count) wrap(20,76,"No folders or 128 KiB saves here. Press B to go back.",280,4,0,MUTED);
    char label[64]; snprintf(label,sizeof(label),"%d / %d",count?cursor+1:0,count); text(206,10,label,0,MUTED,98);
    button(10,210,88,"B  Back",CREAM); button(108,210,202,"A  Open selection",CORAL);
}
int ui_grid_hit(int x,int y) { if(x<10 || x>=310 || y<42 || y>=207) return -1; return (y-42)/33*6+(x-10)/50; }
void ui_box(const UiPokemon *mons,int box,int cursor,const char *trainer,const char *mode) {
    const UiPokemon *p=&mons[cursor]; base("02  /  CHOOSE YOUR POKEMON",mode); screen=&ui_top;
    card(18,54,140,142,0xD8E8F0u);
    for(int y=60;y<190;y+=8) rect(24,y,128,2,0xC0D8E8u);
    sprite(p->kind==1?p->dex:0,p->shiny,24,61,128);
    char line[96]; snprintf(line,sizeof(line),"NO. %03d    %s",p->dex,p->shiny?"SHINY":""); text(172,55,line,0,NAVY,212);
    text(170,74,p->kind==0?"Empty slot":p->kind==2?"Egg":p->kind==3?"Invalid data":p->name,3,NAVY,217);
    text(172,106,p->nickname,1,MUTED,210);
    snprintf(line,sizeof(line),"Lv. %d   /   %s",p->level,p->nature); if(p->kind==1) text(172,130,line,1,NAVY,210);
    if(p->kind==1) { card(172,155,94,22,MINT); text(181,158,p->type[0],0,NAVY,78);
        if(strcmp(p->type[0],p->type[1])) { card(274,155,108,22,0xD9DDB7u); text(283,158,p->type[1],0,NAVY,94); }
    }
    snprintf(line,sizeof(line),"OT  %s  /  %s",p->trainer,p->tid); text(172,185,p->kind==1?line:p->reason,0,MUTED,211);
    screen=&ui_bottom;
    rect(10,40,300,167,0xA8D888u);
    for(int y=43;y<207;y+=8) rect(10,y,300,2,0x98C878u);
    for(int x=23;x<310;x+=50) for(int y=52;y<207;y+=33) { rect(x,y,2,5,0xB8E898u); rect(x-2,y+2,6,2,0xB8E898u); }
    snprintf(line,sizeof(line),"< L    BOX %02d    R >",box+1); text(12,10,line,1,NAVY,198); text(210,11,trainer,0,MUTED,100);
    for(int i=0;i<30;i++) { int x=10+i%6*50,y=42+i/6*33;
        if(i==cursor) { rect(x+2,y+2,43,26,0xE0F0B0u); cursor_frame(x,y,47,30); }
        if(mons[i].kind) sprite(mons[i].kind==1?mons[i].dex:0,mons[i].shiny,x+8,y-1,32);
        else circle(x+23,y+15,1,0x78A868u);
    }
    button(10,210,88,"B  Files",CREAM); button(108,210,202,p->eligible?"A  Select Pokemon":"Unavailable",p->eligible?CORAL:0xDCE5DCu);
}
void ui_status(const char *state,const char *detail,const char *received,const char *mode) {
    int prepared=!strcmp(state,"prepared"),done=!strcmp(state,"received"),running=!strcmp(state,"running");
    base("03  /  TRADE & SAVE",mode); screen=&ui_top;
    text(24,56,prepared?"LINK TRADE":done?"TRADE COMPLETE?":running?"COMMUNICATING...":"CHECK LINK STATUS",3,NAVY,355);
    for(int i=0;i<3;i++) { int x=70+i*130; card(x-25,103,50,48,i==2?CORAL:MINT); if(i<2) { rect(x+26,124,78,6,NAVY); rect(x+26,126,78,2,WHITE); } ball(x,127,12,0xE85848u); }
    text(49,158,"3DS",1,NAVY,65); text(174,158,"Bridge",1,NAVY,70); text(307,158,"Switch",1,NAVY,74);
    text(24,187,done?received:"Your original save has a backup.",1,NAVY,355);
    screen=&ui_bottom; text(16,10,prepared?"Start your exchange":done?"Has the Switch saved?":"Recovery is available",2,NAVY,290);
    const char *body=prepared?"Open the local trade room on Switch. Offer a Pokemon that will not evolve. Use a Kanto return Pokemon until your source has the National Pokedex. No Eggs or held mail.":done?"Confirm only after the Switch has saved and left the trade room. Then we can update the save on your SD card.":detail;
    wrap(16,44,body,285,6,0,NAVY);
    card(12,156,296,42,CREAM); text(22,161,"Safe to leave this screen",0,NAVY,274); text(22,177,"Recovery record kept on SD card.",0,MUTED,274);
    button(10,210,88,"B  Home",CREAM); button(108,210,202,prepared?"A  Start trade":done?"A  Switch saved":"A  Refresh status",CORAL);
}
void ui_message(const char *title,const char *body,int page) {
    base("POKETRADER  /  FRLG",NULL); screen=&ui_top;
    if(width(title,2)<=350) text(24,65,title,2,NAVY,350); else wrap(24,65,title,350,4,0,NAVY); ball(330,169,22,0xE85848u);
    screen=&ui_bottom; wrap(16,18,body,287,9,page*9,NAVY);
    text(16,184,"D-pad: scroll    START: exit",0,MUTED,287); button(10,210,300,"A / B  Continue",MINT);
}
void ui_home(int cursor,int pending,int configured,const char *connection) {
    base("CABLE CLUB  /  MAIN MENU",NULL); screen=&ui_top;
    text(24,55,"WELCOME TO THE CABLE CLUB",2,NAVY,352);
    sprite(6,0,28,86,96); sprite(3,0,276,86,96);
    ball(198,124,18,0xE85848u);
    text(145,155,"FIRE / LEAF",0,NAVY,120);
    text(24,184,connection,0,NAVY,352);
    screen=&ui_bottom; text(18,12,"What would you like to do?",2,NAVY,286);
    card(14,49,292,61,cursor==0?MINT:CREAM);
    text(28,56,pending?"RESUME TRADE":"TRADE",2,NAVY,262);
    text(28,83,pending?"Continue your saved exchange.":"Choose a save and a Pokemon.",0,NAVY,262);
    card(14,119,292,61,cursor==1?MINT:CREAM);
    text(28,126,"SETTINGS",2,NAVY,262);
    text(28,153,configured?"Bridge connection and setup.":"Connect your PC bridge here.",0,NAVY,262);
    text(18,187,"D-pad to choose / A to open",0,NAVY,284);
    button(10,210,88,"B  Exit",CREAM); button(108,210,202,"A  Open",CORAL);
}
void ui_settings(int cursor,const char *host,int port,int has_token,const char *connection,int locked) {
    base("CABLE CLUB  /  SETTINGS",NULL); screen=&ui_top;
    text(24,57,"BRIDGE CONNECTION",3,NAVY,352);
    const char *help=cursor==0?"Enter your PC's LAN IPv4 address.\nExample: 192.168.1.50\nUse the same home network as your 3DS.":cursor==1?"Use the port in the PC bridge config.\nThe default port is 8765.":cursor==2?"Enter the 32-character pairing token\nfrom line 3 of the PC's bridge.cfg.\nThe token is hidden on this screen.":cursor==3?"Test these settings, then save them.\nThis checks the PC bridge connection.\nIt does not test a Switch trade.":"Read the setup guide for the PC bridge\nand the 3DS Wi-Fi connection.";
    wrap(24,98,locked?"A trade is pending. Keep the same bridge\nand pairing token until it is resolved.\nConnection testing is still available.":help,350,4,0,NAVY);
    text(24,184,connection,0,NAVY,352);
    screen=&ui_bottom;
    char port_text[16]; snprintf(port_text,sizeof(port_text),"%d",port);
    const char *labels[]={"PC address","Port","Pairing token","Test & save","Setup help"};
    const char *values[]={*host?host:"Not set",port_text,has_token?"********":"Not set","",""};
    for(int i=0;i<5;i++) {
        int y=10+i*38; card(12,y,296,35,cursor==i?MINT:CREAM);
        text(22,y+8,labels[i],0,NAVY,130);
        text(150,y+8,values[i],0,MUTED,148);
    }
    button(10,210,88,"B  Home",CREAM); button(108,210,202,"A  Select",CORAL);
}
