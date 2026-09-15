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

static PrintConsole top,bottom;
static Config config;
static char error[512];
static int exiting=0;

static void screens(const char *title) {
    consoleSelect(&top); consoleClear();
    printf("PokeTrader | FRLG\n%s\n\n",title);
    consoleSelect(&bottom); consoleClear();
}
static unsigned buttons(void) {
    if(!aptMainLoop()) { exiting=1; return KEY_START; }
    hidScanInput(); unsigned keys=hidKeysDown();
    gfxFlushBuffers(); gfxSwapBuffers(); gspWaitForVBlank();
    return keys;
}
static unsigned wait_buttons(void) {
    unsigned keys=0; while(!(keys=buttons())) {} return keys;
}
static void message(const char *title,const char *body) {
    screens(title); consoleSelect(&top); printf("%s\n",body);
    consoleSelect(&bottom); printf("A / B: continue\nSTART: exit\n");
    while(!exiting) { unsigned k=wait_buttons(); if(k&KEY_START) exiting=1;
        if(k&(KEY_A|KEY_B|KEY_START)) break; }
}
static int call(const char *method,const char *path,const void *data,size_t length,Response *r) {
    return request(&config,method,path,data,length,r,error,sizeof(error));
}
static int load_config(void) {
    FILE *f=fopen(APP_DIR "/bridge.cfg","rb"); if(!f) return -1;
    char lines[3][128]; int ok=1;
    for(int i=0;i<3;i++) {
        if(!fgets(lines[i],sizeof(lines[i]),f)) { ok=0; break; }
        lines[i][strcspn(lines[i],"\r\n")]=0;
    }
    fclose(f);
    if(!ok || strlen(lines[0])>=sizeof(config.host) || strlen(lines[2])!=32 ||
       strspn(lines[2],"0123456789abcdef")!=32) return -1;
    strcpy(config.host,lines[0]); strcpy(config.token,lines[2]); config.port=atoi(lines[1]);
    return config.port>0 && config.port<65536?0:-1;
}

typedef struct { char name[256]; int directory; } Entry;
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
                screens("Choose a save file"); consoleSelect(&top);
                printf("%s\n\nRaw 128 KiB saves are shown.\nVC: export the save first.\nClose the game before trading.\n",current);
                consoleSelect(&bottom);
                if(!count) printf("No folders or 128 KiB saves here.\n");
                size_t first=cursor/18*18;
                for(size_t i=first;i<count && i<first+18;i++)
                    printf("%c%c %.34s\n",i==cursor?'>':' ',entries[i].directory?'/':' ',entries[i].name);
                printf("\nA: open  B: parent\nUP/DOWN: select  START: exit\n"); redraw=0;
            }
            unsigned k=wait_buttons();
            if(k&KEY_START) exiting=1;
            if(k&KEY_UP && count) { cursor=(cursor+count-1)%count; redraw=1; }
            if(k&KEY_DOWN && count) { cursor=(cursor+1)%count; redraw=1; }
            if(k&KEY_B) {
                if(strcmp(current,"sdmc:/")) {
                    char *slash=strrchr(current,'/');
                    if(slash==current+5) slash[1]=0; else if(slash) *slash=0;
                    leave=1;
                }
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
        char path[128],labels[30][100]; Response r;
        snprintf(path,sizeof(path),"/v1/saves/%s/boxes/%d",save_id,box);
        if(call("GET",path,NULL,0,&r)<0) { response_free(&r); message("Could not load box",error); return -1; }
        for(int i=0;i<30;i++) {
            field(&r,i,labels[i],sizeof(labels[i]));
            char *tab=strchr(labels[i],'\t'); if(tab) memmove(labels[i],tab+1,strlen(tab+1)+1);
        }
        response_free(&r); int redraw=1,change=0;
        while(!exiting && !change) {
            if(redraw) {
                screens("Choose a boxed Pokemon"); consoleSelect(&top);
                printf("%s\nTrainer: %s\nBox %d / 14, slot %d\n\n%s\n\n",mode,trainer,box+1,cursor+1,labels[cursor]);
                printf("On Switch, offer a non-evolving Pokemon.\nNo Eggs or mail in this version.\nUse a Kanto return Pokemon before\nunlocking your source National Pokedex.\n");
                consoleSelect(&bottom);
                for(int row=0;row<15;row++) {
                    int right=row+15;
                    printf("%c%02d %.14s",cursor==row?'>':' ',row+1,labels[row]);
                    printf("\x1b[%d;21H%c%02d %.14s\n",row+1,cursor==right?'>':' ',right+1,labels[right]);
                }
                printf("\nL/R: box   D-pad: slot\nA: select  B: files  START: exit\n"); redraw=0;
            }
            unsigned k=wait_buttons();
            if(k&KEY_START) exiting=1;
            if(k&KEY_B) return -1;
            if(k&KEY_UP) { cursor=(cursor+29)%30; redraw=1; }
            if(k&KEY_DOWN) { cursor=(cursor+1)%30; redraw=1; }
            if(k&(KEY_LEFT|KEY_RIGHT)) { cursor=(cursor+15)%30; redraw=1; }
            if(k&KEY_L) { box=(box+13)%14; change=1; }
            if(k&KEY_R) { box=(box+1)%14; change=1; }
            if(k&KEY_A && labels[cursor][0]!='(') return box*30+cursor;
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
            screens("Applying verified save"); consoleSelect(&top); printf("Keep the app open.\nPrevious save and backup are retained.\n");
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
        screens("Trade status"); consoleSelect(&top);
        printf("%s\n%s\n\n%s\n\n%s\n",mode,state,received,detail);
        consoleSelect(&bottom); printf("Transaction\n%s\n\n",p->id);
        if(!strcmp(state,"prepared")) printf("A: start trade\n");
        else if(!strcmp(state,"received")) printf("Check the Switch has saved and left\nthe trade room.\n\nA: confirm and update source save\n");
        else printf("A: refresh status\n");
        printf("B / START: exit; keep recovery record\n");
        unsigned k=0;
        if(!strcmp(state,"running")) {
            /* Poll every two seconds, while keeping exit responsive. */
            for(int frame=0;frame<120 && !(k&(KEY_A|KEY_B|KEY_START));frame++) k=buttons();
        } else k=wait_buttons();
        if(k&(KEY_B|KEY_START)) { exiting=1; return; }
        if(k&KEY_A && (!strcmp(state,"prepared") || !strcmp(state,"received"))) {
            snprintf(path,sizeof(path),"/v1/trades/%s/%s",p->id,!strcmp(state,"prepared")?"start":"confirm");
            if(call("POST",path,NULL,0,&r)<0) { response_free(&r); message("Transaction retained",error); return; }
            response_free(&r);
        }
    }
}

int main(void) {
    gfxInitDefault(); consoleInit(GFX_TOP,&top); consoleInit(GFX_BOTTOM,&bottom);
    mkdir("sdmc:/3ds",0777); mkdir(APP_DIR,0777);
    void *soc_buffer=memalign(0x1000,0x100000);
    int network=0;
    if(!soc_buffer || R_FAILED(socInit(soc_buffer,0x100000))) {
        message("Wi-Fi unavailable","Connect the 3DS to your LAN and restart."); goto done;
    }
    network=1;
    if(load_config()<0) { message("Pair the bridge first","Copy bridge.cfg to:\nsdmc:/3ds/PokeTrader/bridge.cfg\n\nGenerate it with the PC bridge pair command."); goto done; }
    while(!exiting) {
        Pending pending; int status=load_pending(&pending);
        if(status<0) { message("Recovery record unreadable","Keep pending.txt and all backups. Resolve this on the PC before starting a new trade."); break; }
        if(status==1) { recover(&pending); if(!exiting && access(PENDING_PATH,F_OK)==0) break; continue; }
        char selected[PATH_CAP]; if(!browse(selected)) break;
        unsigned char *data=NULL;
        if(read_save(selected,&data,error,sizeof(error))<0) { message("Cannot read save",error); continue; }
        screens("Reading save on bridge"); consoleSelect(&top); printf("Uploading a copy for validation...\n");
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
done:
    if(network) socExit();
    free(soc_buffer); gfxExit(); return 0;
}
