#include "client.h"
#include <arpa/inet.h>
#include <sys/socket.h>
#include <sys/time.h>
#include <fcntl.h>
#include <poll.h>
#include <unistd.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include <strings.h>
#include <errno.h>

static int send_all(int fd, const void *data, size_t size) {
    const char *p=data;
    while(size) {
        struct pollfd wait={fd,POLLOUT,0};
        if(poll(&wait,1,20000)<=0) return -1;
        ssize_t n=send(fd,p,size,0);
        if(n<0 && (errno==EINTR || errno==EAGAIN || errno==EWOULDBLOCK)) continue;
        if(n<=0) return -1;
        p+=n; size-=(size_t)n;
    }
    return 0;
}
static ssize_t receive(int fd,void *data,size_t size) {
    for(;;) {
        struct pollfd wait={fd,POLLIN,0};
        if(poll(&wait,1,20000)<=0) return -1;
        ssize_t n=recv(fd,data,size,0);
        if(n<0 && (errno==EINTR || errno==EAGAIN || errno==EWOULDBLOCK)) continue;
        return n;
    }
}
void response_free(Response *r) { free(r->data); memset(r,0,sizeof(*r)); }
int field(const Response *r, unsigned index, char *out, size_t capacity) {
    if(!capacity) return -1;
    size_t start=0;
    for(unsigned i=0;i<index;i++) {
        while(start<r->size && r->data[start]!='\n') start++;
        if(start>=r->size) { out[0]=0; return -1; } start++;
    }
    size_t end=start;
    while(end<r->size && r->data[end]!='\n') end++;
    size_t n=end-start; if(n>=capacity) n=capacity-1;
    memcpy(out,r->data+start,n); out[n]=0;
    return 0;
}
int request(const Config *cfg, const char *method, const char *path,
            const void *body, size_t size, Response *out, char *error, size_t capacity) {
    memset(out,0,sizeof(*out));
    int fd=socket(AF_INET,SOCK_STREAM,0);
    if(fd<0) { snprintf(error,capacity,"Cannot open Wi-Fi socket."); return -1; }
    struct sockaddr_in addr={0}; addr.sin_family=AF_INET; addr.sin_port=htons(cfg->port);
    if(inet_pton(AF_INET,cfg->host,&addr.sin_addr)!=1) {
        snprintf(error,capacity,"bridge.cfg needs the PC's IPv4 address."); close(fd); return -1;
    }
    int flags=fcntl(fd,F_GETFL,0);
    if(flags<0 || fcntl(fd,F_SETFL,flags|O_NONBLOCK)<0) goto network_error;
    if(connect(fd,(struct sockaddr *)&addr,sizeof(addr))<0) {
        if(errno!=EINPROGRESS) goto network_error;
        struct pollfd wait={fd,POLLOUT,0};
        if(poll(&wait,1,10000)<=0) goto network_error;
#ifdef __3DS__
        /* On 3DS, SOC's SO_ERROR query can fail after poll has already
           completed a successful handshake. Closing at that point sends a
           reset before the HTTP request. poll reports connection failures in
           revents, and send_all remains the final connection check. */
        if(!(wait.revents&POLLOUT) || (wait.revents&(POLLERR|POLLHUP|POLLNVAL)))
            goto network_error;
#else
        int code=0; socklen_t len=sizeof(code);
        if(getsockopt(fd,SOL_SOCKET,SO_ERROR,&code,&len)<0 || code) goto network_error;
#endif
    }
    /* libctru has no SO_RCVTIMEO/SO_SNDTIMEO. Keep the socket nonblocking
       and bound every wait with poll on both the 3DS and native builds. */
    char header[1024];
    int length=snprintf(header,sizeof(header),
        "%s %s HTTP/1.0\r\nHost: %s:%d\r\nAuthorization: Bearer %s\r\n"
        "Content-Type: application/octet-stream\r\nContent-Length: %lu\r\nConnection: close\r\n\r\n",
        method,path,cfg->host,cfg->port,cfg->token,(unsigned long)size);
    if(length<0 || (size_t)length>=sizeof(header)) goto network_error;
    if(send_all(fd,header,length)<0 || (size && send_all(fd,body,size)<0)) goto network_error;
    char response_header[8192]; size_t used=0;
    while(used<sizeof(response_header)-1) {
        if(receive(fd,response_header+used,1)!=1) goto network_error;
        used++; response_header[used]=0;
        if(used>=4 && !memcmp(response_header+used-4,"\r\n\r\n",4)) break;
    }
    if(used==sizeof(response_header)-1) goto network_error;
    if(sscanf(response_header,"HTTP/%*s %d",&out->status)!=1) goto network_error;
    long bytes=-1; int lengths=0;
    char *line=strstr(response_header,"\r\n");
    while(line && line[2] && line[2]!='\r') {
        line+=2;
        if(!strncasecmp(line,"Content-Length:",15)) { bytes=strtol(line+15,NULL,10); lengths++; }
        if(!strncasecmp(line,"Transfer-Encoding:",18)) goto network_error;
        line=strstr(line,"\r\n");
    }
    if(lengths!=1 || bytes<0 || bytes>SAVE_BYTES) goto network_error;
    out->data=malloc((size_t)bytes+1); if(!out->data) goto network_error;
    while(out->size<(size_t)bytes) {
        ssize_t n=receive(fd,out->data+out->size,(size_t)bytes-out->size);
        if(n<0 && errno==EINTR) continue;
        if(n<=0) goto network_error;
        out->size+=(size_t)n;
    }
    out->data[out->size]=0; close(fd);
    if(out->status!=200) {
        snprintf(error,capacity,"Bridge %d: %.*s",out->status,(int)(capacity>30?capacity-30:0),out->data);
        return -1;
    }
    return 0;
network_error:
    close(fd); response_free(out);
    snprintf(error,capacity,"Bridge connection failed. Check Wi-Fi, bridge.cfg and the PC. Any pending trade is retained.");
    return -1;
}
