#include "client.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <sys/stat.h>
#include <errno.h>

int read_save(const char *path, unsigned char **out, char *error, size_t capacity) {
    *out=NULL;
    FILE *f=fopen(path,"rb");
    if(!f) { snprintf(error,capacity,"Cannot open save file."); return -1; }
    unsigned char *data=malloc(SAVE_BYTES);
    if(!data) { fclose(f); return -1; }
    size_t n=fread(data,1,SAVE_BYTES,f);
    int extra=fgetc(f), failed=ferror(f); fclose(f);
    if(n!=SAVE_BYTES || extra!=EOF || failed) {
        free(data); snprintf(error,capacity,"Select a raw 128 KiB FRLG save. Export Virtual Console saves first; save states are unsupported."); return -1;
    }
    *out=data; return 0;
}
int durable_file(const char *path, const void *bytes, size_t count) {
    FILE *f=fopen(path,"wb"); if(!f) return -1;
    int ok=fwrite(bytes,1,count,f)==count;
    if(fflush(f)!=0) ok=0;
    if(fsync(fileno(f))!=0) ok=0;
    if(fclose(f)!=0) ok=0;
    return ok?0:-1;
}
static int read_line(FILE *f,char *out,size_t capacity) {
    size_t n=0; int c;
    while((c=fgetc(f))!=EOF && c!='\n') {
        if(c=='\r' || n+1>=capacity) return -1;
        out[n++]=(char)c;
    }
    out[n]=0; return c=='\n'?0:-1;
}
static int is_hex(const char *s,size_t n) {
    if(strlen(s)!=n) return 0;
    return strspn(s,"0123456789abcdef")==n;
}
int load_pending(Pending *p) {
    FILE *f=fopen(PENDING_PATH,"rb"); if(!f) return errno==ENOENT?0:-1;
    char slot[16]; memset(p,0,sizeof(*p));
    int ok=read_line(f,p->id,sizeof(p->id))==0 &&
        read_line(f,p->save_id,sizeof(p->save_id))==0 && read_line(f,slot,sizeof(slot))==0 &&
        read_line(f,p->path,sizeof(p->path))==0 && read_line(f,p->original_hash,sizeof(p->original_hash))==0;
    fclose(f);
    if(!ok || !is_hex(p->id,32) || !is_hex(p->save_id,32) || !is_hex(p->original_hash,64)) return -1;
    p->slot=atoi(slot);
    return p->slot>=0 && p->slot<420 && !strncmp(p->path,"sdmc:/",6)?1:-1;
}
int store_pending(const Pending *p) {
    char body[PATH_CAP+180];
    int n=snprintf(body,sizeof(body),"%s\n%s\n%d\n%s\n%s\n",p->id,p->save_id,p->slot,p->path,p->original_hash);
    if(n<0 || (size_t)n>=sizeof(body)) return -1;
    if(durable_file(PENDING_PATH ".new",body,n)<0) return -1;
    return rename(PENDING_PATH ".new",PENDING_PATH);
}
static int file_hash(const char *path,char out[65]) {
    unsigned char *data=NULL; char error[128];
    if(read_save(path,&data,error,sizeof(error))<0) return -1;
    sha256_hex(data,SAVE_BYTES,out); free(data); return 0;
}
int apply_result(const Pending *p,const void *result,const char *result_hash,char *error,size_t capacity) {
    char hash[65],old[PATH_CAP+64],temp[PATH_CAP+64],backup[128];
    sha256_hex(result,SAVE_BYTES,hash);
    if(strcmp(hash,result_hash)) { snprintf(error,capacity,"Downloaded save checksum mismatch."); return -1; }
    snprintf(old,sizeof(old),"%s.trade-old-%s",p->path,p->id);
    snprintf(temp,sizeof(temp),"%s.trade-new-%s",p->path,p->id);
    snprintf(backup,sizeof(backup),APP_DIR "/backup-%s.sav",p->id);
    if(file_hash(backup,hash)<0 || strcmp(hash,p->original_hash)) {
        snprintf(error,capacity,"Original backup is missing or changed. No save was overwritten."); return -1;
    }
    struct stat status;
    int exists=stat(p->path,&status)==0;
    if(exists) {
        if(file_hash(p->path,hash)<0) { snprintf(error,capacity,"Source save is unreadable; keep the backup for recovery."); return -1; }
        if(!strcmp(hash,result_hash)) return 0; /* Already applied before a dropped acknowledgement. */
        if(strcmp(hash,p->original_hash)) { snprintf(error,capacity,"Source save changed since selection. No overwrite. Keep the transaction for recovery."); return -1; }
        if(stat(old,&status)==0) { snprintf(error,capacity,"An earlier replacement backup exists. Check the save files before continuing."); return -1; }
    } else if(file_hash(old,hash)<0 || strcmp(hash,p->original_hash)) {
        snprintf(error,capacity,"Source is missing and no matching rename backup exists."); return -1;
    }
    if(durable_file(temp,result,SAVE_BYTES)<0 || file_hash(temp,hash)<0 || strcmp(hash,result_hash)) {
        snprintf(error,capacity,"Could not write and verify the new save. Check free SD space."); return -1;
    }
    if(exists && rename(p->path,old)<0) { snprintf(error,capacity,"Could not preserve the previous save."); return -1; }
    if(rename(temp,p->path)<0) { snprintf(error,capacity,"Replacement rename failed. Restart the app to recover; do not launch the game."); return -1; }
    if(file_hash(p->path,hash)<0 || strcmp(hash,result_hash)) { snprintf(error,capacity,"Final save verification failed. Keep all backup files."); return -1; }
    return 0;
}
