#include "client.h"
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <errno.h>
#include <unistd.h>
#include <arpa/inet.h>
int config_valid(const Config *c) {
    struct in_addr ip;
    return memchr(c->host,0,sizeof(c->host)) && inet_pton(AF_INET,c->host,&ip)==1 &&
        c->port>0 && c->port<=65535 && c->token[32]==0 &&
        strspn(c->token,"0123456789abcdef")==32;
}
int config_load(const char *path,Config *out) {
    FILE *f=fopen(path,"rb"); if(!f) return -1;
    char lines[3][128]; int ok=1;
    for(int i=0;i<3;i++) {
        if(!fgets(lines[i],sizeof(lines[i]),f)) { ok=0; break; }
        lines[i][strcspn(lines[i],"\r\n")]=0;
    }
    fclose(f); if(!ok || strlen(lines[0])>=64 || strlen(lines[2])!=32) return -1;
    Config c={0}; char *end;
    long port=strtol(lines[1],&end,10);
    if(!lines[1][0] || *end || port<1 || port>65535) return -1;
    strcpy(c.host,lines[0]); strcpy(c.token,lines[2]); c.port=(int)port;
    if(!config_valid(&c)) return -1;
    *out=c; return 0;
}
int config_save(const char *path,const Config *c) {
    char temp[PATH_CAP],backup[PATH_CAP],body[128];
    if(!config_valid(c) ||
       snprintf(temp,sizeof(temp),"%s.new",path)>=(int)sizeof(temp) ||
       snprintf(backup,sizeof(backup),"%s.bak",path)>=(int)sizeof(backup)) return -1;
    int n=snprintf(body,sizeof(body),"%s\n%d\n%s\n",c->host,c->port,c->token);
    if(durable_file(temp,body,(size_t)n)<0) return -1;
    Config check;
    if(config_load(temp,&check)<0 || strcmp(c->host,check.host) || strcmp(c->token,check.token) || c->port!=check.port) return -1;
    /* The FAT-backed 3DS filesystem may reject rename(new, existing). Move
       the old config aside so the verified file is renamed into a free path. */
    if(unlink(backup)<0 && errno!=ENOENT) return -1;
    int had_old=rename(path,backup)==0;
    if(!had_old && errno!=ENOENT) return -1;
    if(rename(temp,path)<0) {
        if(had_old) rename(backup,path);
        return -1;
    }
    if(config_load(path,&check)<0 || strcmp(c->host,check.host) ||
       strcmp(c->token,check.token) || c->port!=check.port) {
        unlink(path);
        if(had_old) rename(backup,path);
        return -1;
    }
    if(had_old) unlink(backup);
    return 0;
}
