#include <3ds.h>
#include <malloc.h>
#include <dirent.h>
#include <sys/stat.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <strings.h>
#include <unistd.h>
#include "client.h"
#include "ui.h"

static Config config;
static char error[512];
static int exiting=0;
static int network=0;
static char connection[64]="Not tested";
static void present(void) {
    UiScreen *screens[2]={&ui_top,&ui_bottom};
    for(int i=0;i<2;i++) {
        unsigned char *out=gfxGetFramebuffer(i?GFX_BOTTOM:GFX_TOP,GFX_LEFT,NULL,NULL);
        UiScreen *s=screens[i];
        for(int y=0;y<240;y++) for(int x=0;x<s->width;x++) {
            const unsigned char *in=s->pixels+(y*s->width+x)*3;
            unsigned char *to=out+(x*240+239-y)*3;
            to[0]=in[2]; to[1]=in[1]; to[2]=in[0];
        }
    }
    gfxFlushBuffers(); gfxSwapBuffers(); gspWaitForVBlank();
}
static unsigned buttons(void) {
    if(!aptMainLoop()) { exiting=1; return KEY_START; }
    hidScanInput(); gspWaitForVBlank(); return hidKeysDown();
}
static unsigned wait_buttons(void) {
    unsigned keys=0; while(!(keys=buttons())) {} return keys;
}
static void message(const char *title,const char *body) {
    int page=0;
    while(!exiting) {
        ui_message(title,body,page); present();
        unsigned k=wait_buttons();
        if(k&KEY_START) exiting=1;
        if(k&KEY_DOWN && page<8) page++;
        if(k&KEY_UP && page>0) page--;
        if(k&KEY_TOUCH) { touchPosition t; hidTouchRead(&t); if(t.py>=210) k|=KEY_A; }
        if(k&(KEY_A|KEY_B|KEY_START)) break;
    }
}
static int call(const char *method,const char *path,const void *data,size_t length,Response *r) {
    return request(&config,method,path,data,length,r,error,sizeof(error));
}
static int edit_text(char *value,size_t capacity,const char *hint,int secret) {
    SwkbdState keyboard;
    swkbdInit(&keyboard,SWKBD_TYPE_QWERTY,2,(int)capacity-1);
    swkbdSetHintText(&keyboard,hint);
    swkbdSetInitialText(&keyboard,value);
    swkbdSetButton(&keyboard,SWKBD_BUTTON_LEFT,"Cancel",false);
    swkbdSetButton(&keyboard,SWKBD_BUTTON_RIGHT,"OK",true);
    if(secret) swkbdSetPasswordMode(&keyboard,SWKBD_PASSWORD_HIDE_DELAY);
    char input[64]={0};
    if(swkbdInputText(&keyboard,input,capacity)!=SWKBD_BUTTON_RIGHT) return 0;
    strcpy(value,input); return 1;
}
static void settings(int locked) {
    Config draft=config; int cursor=0;
    if(!draft.port) draft.port=8765;
    while(!exiting) {
        ui_settings(cursor,draft.host,draft.port,draft.token[0]!=0,connection,locked); present();
        unsigned k=wait_buttons();
        if(k&KEY_START) { exiting=1; return; }
        if(k&KEY_B) return;
        if(k&KEY_UP) cursor=(cursor+4)%5;
        if(k&KEY_DOWN) cursor=(cursor+1)%5;
        if(k&KEY_TOUCH) {
            touchPosition t; hidTouchRead(&t);
            if(t.py>=210) { if(t.px<103) return; k|=KEY_A; }
            else if(t.px>=12 && t.px<308 && t.py>=10 && t.py<200) { cursor=(t.py-10)/38; k|=KEY_A; }
        }
        if(!(k&KEY_A)) continue;
        if(cursor<3 && locked) { message("Trade recovery comes first","Finish or resolve the pending trade using the original bridge before changing its settings."); continue; }
        if(cursor==0) {
            if(edit_text(draft.host,sizeof(draft.host),"PC address, e.g. 192.168.1.50",0)) strcpy(connection,"Edited / not saved");
        } else if(cursor==1) {
            char value[16]; snprintf(value,sizeof(value),"%d",draft.port);
            if(edit_text(value,sizeof(value),"Bridge port, usually 8765",0)) {
                char *end; long port=strtol(value,&end,10);
                if(!*value || *end || port<1 || port>65535) message("Invalid port","Enter a number from 1 to 65535.");
                else { draft.port=(int)port; strcpy(connection,"Edited / not saved"); }
            }
        } else if(cursor==2) {
            if(edit_text(draft.token,sizeof(draft.token),"32-character token from bridge.cfg",1)) {
                for(char *c=draft.token;*c;c++) if(*c>='A' && *c<='F') *c+=32;
                strcpy(connection,"Edited / not saved");
            }
        } else if(cursor==3) {
            if(!config_valid(&draft)) { message("Check the connection details","Use an IPv4 address, a port from 1 to 65535, and the 32 hexadecimal characters from line 3 of the PC bridge.cfg."); continue; }
            if(!network) { message("Wi-Fi unavailable","Set up Wi-Fi in the 3DS System Settings, then restart PokeTrader."); continue; }
            ui_settings(cursor,draft.host,draft.port,1,"Testing connection...",locked); present();
            Response r; char protocol[64],mode[80];
            if(request(&draft,"GET","/v1/health",NULL,0,&r,error,sizeof(error))<0) {
                strcpy(connection,"Connection test failed"); response_free(&r); message("Could not reach the bridge",error); continue;
            }
            field(&r,0,protocol,sizeof(protocol)); field(&r,1,mode,sizeof(mode)); response_free(&r);
            if(strcmp(protocol,"PokeTrader/1") || (strcmp(mode,"LIVE") && strcmp(mode,"DEMO - NO SWITCH TRADE"))) {
                strcpy(connection,"Unexpected bridge response"); message("Wrong bridge response","Check the address and port. This must be a PokeTrader bridge."); continue;
            }
            if(!locked && config_save(APP_DIR "/bridge.cfg",&draft)<0) { message("Could not save settings","Settings were not activated. Check the SD card and retry."); continue; }
            config=draft;
            strcpy(connection,!strcmp(mode,"LIVE")?"Bridge tested / LIVE":"Bridge tested / DEMO");
            message("Connection successful",!strcmp(mode,"LIVE")?"Settings saved. Your 3DS can reach the PC bridge. Return Home and choose Trade. Switch trading still needs the dedicated adapter and live bridge setup.":"Settings saved. This bridge is in DEMO mode. It will not trade with a Switch.");
        } else {
            message("Bridge setup", "1. Connect the 3DS to home Wi-Fi in System Settings. Connect the Linux PC to the same LAN.\n\n2. On the PC, run the bridge pair command to create bridge.cfg.\n\n3. Copy that file to /3ds/PokeTrader/ on the SD card and restart this app. Or enter its three lines here: PC address, port, pairing token.\n\n4. Start the bridge on the PC, then choose Test & save here.\n\nLive trades need a dedicated Switch Wi-Fi adapter. Keep the PC's LAN connection on Ethernet or another adapter. Full commands are in the project README.");
        }
    }
}
static int home(int pending) {
    int cursor=0;
    while(!exiting) {
        ui_home(cursor,pending,config_valid(&config),connection); present();
        unsigned k=wait_buttons();
        if(k&(KEY_B|KEY_START)) { exiting=1; return 0; }
        if(k&(KEY_UP|KEY_DOWN)) cursor=1-cursor;
        if(k&KEY_TOUCH) {
            touchPosition t; hidTouchRead(&t);
            if(t.py>=210) { if(t.px<103) { exiting=1; return 0; } k|=KEY_A; }
            else if(t.px>=14 && t.px<306 && t.py>=49 && t.py<110) { cursor=0; k|=KEY_A; }
            else if(t.px>=14 && t.px<306 && t.py>=119 && t.py<180) { cursor=1; k|=KEY_A; }
        }
        if(k&KEY_A) {
            if(cursor==1) { settings(pending); if(!strstr(connection,"tested")) strcpy(connection,config_valid(&config)?"Not tested":"Set up your bridge in Settings"); }
            else if(!network) message("Wi-Fi unavailable","Set up Wi-Fi in System Settings, then restart this app.");
            else if(!config_valid(&config)) { message("Set up the bridge first","Open Settings to enter your PC bridge details and test the connection."); cursor=1; }
            else return 1;
        }
    }
    return 0;
}

typedef UiEntry Entry;
static int compare_entries(const void *a,const void *b) {
    const Entry *x=a,*y=b;
    if(x->directory!=y->directory) return y->directory-x->directory;
    return strcasecmp(x->name,y->name);
}
static int browse(char selected[PATH_CAP]) {
    char current[PATH_CAP]="sdmc:/";
    while(!exiting) {
        DIR *dir=opendir(current);
        if(!dir) { message("Cannot open directory",current); return 0; }
        size_t count=0,capacity=64;
        Entry *entries=malloc(capacity*sizeof(*entries));
        if(!entries) { closedir(dir); return 0; }
        struct dirent *item;
        while((item=readdir(dir))) {
            if(!strcmp(item->d_name,".") || !strcmp(item->d_name,"..") ||
               strlen(item->d_name)>=256 || strpbrk(item->d_name,"\r\n\t")) continue;
            char path[PATH_CAP];
            if(snprintf(path,sizeof(path),"%s%s%s",current,current[strlen(current)-1]=='/'?"":"/",item->d_name)>=(int)sizeof(path)) continue;
            struct stat st; if(stat(path,&st)!=0) continue;
            /* Show all directories and all 128 KiB regular files, regardless of extension. */
            if(!S_ISDIR(st.st_mode) && (!S_ISREG(st.st_mode) || st.st_size!=SAVE_BYTES)) continue;
            if(count==capacity) {
                if(capacity>=4096) { message("Directory too large","Use a folder with fewer than 4096 eligible entries."); break; }
                Entry *grown=realloc(entries,capacity*2*sizeof(*entries));
                if(!grown) break;
                entries=grown; capacity*=2;
            }
            strcpy(entries[count].name,item->d_name); entries[count].directory=S_ISDIR(st.st_mode); count++;
        }
        closedir(dir); qsort(entries,count,sizeof(*entries),compare_entries);
        size_t cursor=0; int redraw=1,leave=0;
        while(!exiting && !leave) {
            if(redraw) {
                ui_browser(current,entries,(int)count,(int)cursor); present(); redraw=0;
            }
            unsigned k=wait_buttons();
            if(k&KEY_TOUCH) {
                touchPosition t; hidTouchRead(&t);
                if(t.py>=210) k|=t.px<103?KEY_B:KEY_A;
                else if(t.py>=53 && t.py<193) {
                    size_t picked=cursor/4*4+(t.py-53)/35;
                    if(picked<count) { cursor=picked; redraw=1; }
                }
            }
            if(k&KEY_START) exiting=1;
            if(k&KEY_UP && count) { cursor=(cursor+count-1)%count; redraw=1; }
            if(k&KEY_DOWN && count) { cursor=(cursor+1)%count; redraw=1; }
            if(k&KEY_B) {
                if(strcmp(current,"sdmc:/")) {
                    char *slash=strrchr(current,'/');
                    if(slash==current+5) slash[1]=0; else if(slash) *slash=0;
                    leave=1;
                } else { free(entries); return 0; }
            }
            if(k&KEY_A && count) {
                char path[PATH_CAP];
                if(snprintf(path,sizeof(path),"%s%s%s",current,current[strlen(current)-1]=='/'?"":"/",entries[cursor].name)>=(int)sizeof(path)) continue;
                if(entries[cursor].directory) { strcpy(current,path); leave=1; }
                else { strcpy(selected,path); free(entries); return 1; }
            }
        }
        free(entries);
    }
    return 0;
}

static int select_pokemon(const char *save_id,const char *trainer,const char *mode) {
    int box=0,cursor=0;
    while(!exiting) {
        char path[128],line[1024]; UiPokemon mons[30]; Response r;
        snprintf(path,sizeof(path),"/v1/saves/%s/boxes/%d/details",save_id,box);
        if(call("GET",path,NULL,0,&r)<0) { response_free(&r); message("Could not load box",error); return -1; }
        int valid=1;
        for(int i=0;i<30;i++) {
            field(&r,i,line,sizeof(line));
            if(ui_parse_pokemon(line,&mons[i])<0 || mons[i].index!=box*30+i) valid=0;
        }
        response_free(&r);
        if(!valid) { message("Invalid box response","Update the PC bridge to version 0.2 or later."); return -1; }
        int redraw=1,change=0;
        while(!exiting && !change) {
            if(redraw) { ui_box(mons,box,cursor,trainer,mode); present(); redraw=0; }
            unsigned k=wait_buttons();
            if(k&KEY_TOUCH) {
                touchPosition t; hidTouchRead(&t); int hit=ui_grid_hit(t.px,t.py);
                if(hit>=0) { cursor=hit; redraw=1; }
                else if(t.py>=210) k|=t.px<103?KEY_B:KEY_A;
                else if(t.py<35) k|=t.px<100?KEY_L:KEY_R;
            }
            if(k&KEY_START) exiting=1;
            if(k&KEY_B) return -1;
            if(k&KEY_UP) { cursor=(cursor+24)%30; redraw=1; }
            if(k&KEY_DOWN) { cursor=(cursor+6)%30; redraw=1; }
            if(k&KEY_LEFT) { cursor=cursor/6*6+(cursor%6+5)%6; redraw=1; }
            if(k&KEY_RIGHT) { cursor=cursor/6*6+(cursor%6+1)%6; redraw=1; }
            if(k&KEY_L) { box=(box+13)%14; change=1; }
            if(k&KEY_R) { box=(box+1)%14; change=1; }
            if(k&KEY_A) {
                if(mons[cursor].eligible) return box*30+cursor;
                message("Cannot select this slot",mons[cursor].reason); redraw=1;
            }
        }
    }
    return -1;
}

static void recover(Pending *p) {
    char path[128];
    while(!exiting) {
        Response r;
        snprintf(path,sizeof(path),"/v1/trades/%s",p->id);
        if(call("GET",path,NULL,0,&r)<0) {
            int missing=r.status==404; response_free(&r);
            if(missing) {
                char body[80]; int n=snprintf(body,sizeof(body),"%s\n%d\n",p->save_id,p->slot);
                if(call("PUT",path,body,n,&r)<0) {
                    int rejected=r.status==400; response_free(&r);
                    if(rejected) remove(PENDING_PATH); /* Validation failed before any trade could start. */
                    message(rejected?"Selection rejected":"Transaction retained",error); return;
                }
            } else { message("Transaction retained",error); return; }
        }
        char state[32],detail[512],received[128],mode[80],result_hash[65];
        field(&r,0,state,sizeof(state)); field(&r,1,detail,sizeof(detail));
        field(&r,2,received,sizeof(received)); field(&r,3,mode,sizeof(mode));
        field(&r,4,result_hash,sizeof(result_hash)); response_free(&r);
        if(!strcmp(state,"ready") || !strcmp(state,"applied")) {
            ui_message("Applying verified save","Keep the app open. Previous save and backup are retained.",0); present();
            snprintf(path,sizeof(path),"/v1/trades/%s/result",p->id);
            if(call("GET",path,NULL,0,&r)<0) { response_free(&r); message("Download failed",error); return; }
            if(r.size!=SAVE_BYTES || strlen(result_hash)!=64) {
                response_free(&r); message("Invalid result","The bridge returned an invalid save response."); return;
            }
            if(apply_result(p,r.data,result_hash,error,sizeof(error))<0) {
                response_free(&r); message("Save not replaced",error); return;
            }
            response_free(&r);
            snprintf(path,sizeof(path),"/v1/trades/%s/applied",p->id);
            if(call("POST",path,NULL,0,&r)<0) { response_free(&r); message("Save written; acknowledgement pending",error); return; }
            response_free(&r);
            if(remove(PENDING_PATH)!=0) { message("Save written","Could not clear pending record. Recovery is safe to repeat."); return; }
            message("Save updated","The received Pokemon is in the selected box slot.\n\nEmulator: load the in-game save, not an old state.\nVC export: import this save back into the title.\n\nBackups remain on your SD card.");
            return;
        }
        if(!strcmp(state,"cancelled")) { remove(PENDING_PATH); message("Cancelled","The bridge operator confirmed that no trade occurred."); return; }
        ui_status(state,detail,received,mode); present();
        unsigned k=0;
        if(!strcmp(state,"running")) {
            /* Poll every two seconds, while keeping exit responsive. */
            for(int frame=0;frame<120 && !(k&(KEY_A|KEY_B|KEY_START|KEY_TOUCH));frame++) k=buttons();
        } else k=wait_buttons();
        if(k&KEY_TOUCH) { touchPosition t; hidTouchRead(&t); if(t.py>=210) k|=t.px<103?KEY_B:KEY_A; }
        if(k&KEY_START) { exiting=1; return; }
        if(k&KEY_B) return;
        if(k&KEY_A && (!strcmp(state,"prepared") || !strcmp(state,"received"))) {
            snprintf(path,sizeof(path),"/v1/trades/%s/%s",p->id,!strcmp(state,"prepared")?"start":"confirm");
            if(call("POST",path,NULL,0,&r)<0) { response_free(&r); message("Transaction retained",error); return; }
            response_free(&r);
        }
    }
}

int main(void) {
    gfxInitDefault();
    if(R_FAILED(romfsInit()) || ui_init("romfs:/ui")<0) {
        consoleInit(GFX_TOP,NULL); printf("PokeTrader UI assets could not load.\nReinstall the complete .3dsx file.\nSTART: exit\n");
        while(aptMainLoop()) { hidScanInput(); if(hidKeysDown()&KEY_START) break; gspWaitForVBlank(); }
        romfsExit(); gfxExit(); return 1;
    }
    mkdir("sdmc:/3ds",0777); mkdir(APP_DIR,0777);
    void *soc_buffer=memalign(0x1000,0x100000);
    if(!soc_buffer || R_FAILED(socInit(soc_buffer,0x100000))) {
        message("Wi-Fi unavailable","Connect the 3DS to your LAN in System Settings and restart. You can still open the app settings.");
    }
    else network=1;
    if(config_load(APP_DIR "/bridge.cfg",&config)<0) { memset(&config,0,sizeof(config)); config.port=8765; strcpy(connection,"Set up your bridge in Settings"); }
    while(!exiting) {
        Pending pending; int status=load_pending(&pending);
        if(!home(status!=0)) break;
        if(status<0) { message("Recovery record unreadable","Keep pending.txt and all backups. Resolve this on the PC before starting a new trade."); continue; }
        if(status==1) { recover(&pending); continue; }
        char selected[PATH_CAP]; if(!browse(selected)) continue;
        unsigned char *data=NULL;
        if(read_save(selected,&data,error,sizeof(error))<0) { message("Cannot read save",error); continue; }
        ui_message("Reading save on bridge","Uploading a copy for validation...",0); present();
        Response r;
        if(call("POST","/v1/saves",data,SAVE_BYTES,&r)<0) { response_free(&r); free(data); message("Save rejected",error); continue; }
        char save_id[33],trainer[64],mode[80],warning[160];
        field(&r,0,save_id,sizeof(save_id)); field(&r,2,trainer,sizeof(trainer));
        field(&r,4,warning,sizeof(warning)); field(&r,5,mode,sizeof(mode)); response_free(&r);
        if(warning[0]) message("Save validation",warning);
        int slot=select_pokemon(save_id,trainer,mode);
        if(slot<0) { free(data); continue; }
        memset(&pending,0,sizeof(pending));
        sha256_hex(data,SAVE_BYTES,pending.original_hash);
        /* Fresh transaction ID; save hashes are used only for content identity. */
        unsigned char entropy[64]={0};
        uint64_t ticks=svcGetSystemTick(); memcpy(entropy,&ticks,sizeof(ticks));
        memcpy(entropy+8,pending.original_hash,48); memcpy(entropy+56,&slot,sizeof(slot));
        char id_hash[65]; sha256_hex(entropy,sizeof(entropy),id_hash);
        memcpy(pending.id,id_hash,32); pending.id[32]=0;
        strcpy(pending.save_id,save_id); strcpy(pending.path,selected); pending.slot=slot;
        char backup[128]; snprintf(backup,sizeof(backup),APP_DIR "/backup-%s.sav",pending.id);
        if(access(backup,F_OK)==0 || durable_file(backup,data,SAVE_BYTES)<0) {
            free(data); message("Backup failed","Check free SD space. No trade was started."); continue;
        }
        free(data);
        if(store_pending(&pending)<0) { message("Recovery record failed","No trade was started. Check SD storage."); break; }
        recover(&pending);
    }
    if(network) socExit();
    free(soc_buffer); ui_close(); romfsExit(); gfxExit(); return 0;
}
