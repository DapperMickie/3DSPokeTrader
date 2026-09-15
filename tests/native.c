/* Native checks for code shared verbatim with the 3DS build. */
#include "client.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <sys/stat.h>
#include <sys/socket.h>
#include <sys/wait.h>
#include <arpa/inet.h>
#include <unistd.h>

static void test_hash(void) {
    char hash[65]; sha256_hex("",0,hash);
    assert(!strcmp(hash,"e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"));
    sha256_hex("abc",3,hash);
    assert(!strcmp(hash,"ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"));
    char *million=malloc(1000000); memset(million,'a',1000000); sha256_hex(million,1000000,hash); free(million);
    assert(!strcmp(hash,"cdc76e5c9914fb9281a1c7e284d73e67f1809a48a497200e046d39ccc7112cd0"));
}
static void test_files(void) {
    char directory[]="/tmp/poketrader-native-XXXXXX";
    assert(mkdtemp(directory)); assert(chdir(directory)==0);
    mkdir("sdmc:",0700); mkdir("sdmc:/3ds",0700); mkdir(APP_DIR,0700);
    Pending p={0},loaded;
    memset(p.id,'a',32); memset(p.save_id,'b',32); p.slot=49;
    strcpy(p.path,"sdmc:/my game.sav");
    unsigned char *original=calloc(1,SAVE_BYTES),*result=malloc(SAVE_BYTES);
    memset(result,1,SAVE_BYTES); sha256_hex(original,SAVE_BYTES,p.original_hash);
    assert(store_pending(&p)==0); assert(load_pending(&loaded)==1);
    assert(!strcmp(p.id,loaded.id)); assert(!strcmp(p.path,loaded.path)); assert(loaded.slot==49);
    char backup[256]; snprintf(backup,sizeof(backup),APP_DIR "/backup-%s.sav",p.id);
    assert(durable_file(backup,original,SAVE_BYTES)==0);
    assert(durable_file(p.path,original,SAVE_BYTES)==0);
    char hash[65],error[256]; sha256_hex(result,SAVE_BYTES,hash);
    assert(apply_result(&p,result,hash,error,sizeof(error))==0);
    /* Dropped acknowledgement: applying again must not repeat a rename. */
    assert(apply_result(&p,result,hash,error,sizeof(error))==0);
    unsigned char *read=NULL;
    assert(read_save(p.path,&read,error,sizeof(error))==0); assert(!memcmp(read,result,SAVE_BYTES)); free(read);
    /* Changed source is never overwritten, even with a valid old backup. */
    result[0]=3; assert(durable_file(p.path,result,SAVE_BYTES)==0); result[0]=1;
    assert(apply_result(&p,result,hash,error,sizeof(error))<0);
    /* Restart between old-save rename and new-save rename. */
    assert(unlink(p.path)==0);
    assert(apply_result(&p,result,hash,error,sizeof(error))==0);
    /* Corrupt result body fails before touching the source. */
    result[0]=2; assert(apply_result(&p,result,hash,error,sizeof(error))<0);
    free(original); free(result);
    printf("Native save recovery fixtures: %s\n",directory);
}
static void test_http(int truncated) {
    int listener=socket(AF_INET,SOCK_STREAM,0); assert(listener>=0);
    struct sockaddr_in addr={0}; addr.sin_family=AF_INET; addr.sin_addr.s_addr=htonl(INADDR_LOOPBACK);
    assert(bind(listener,(struct sockaddr *)&addr,sizeof(addr))==0); assert(listen(listener,1)==0);
    socklen_t size=sizeof(addr); assert(getsockname(listener,(struct sockaddr *)&addr,&size)==0);
    pid_t child=fork(); assert(child>=0);
    if(!child) {
        int peer=accept(listener,NULL,NULL); assert(peer>=0);
        char incoming[2048]={0}; size_t n=0;
        while(n<sizeof(incoming)-1 && !strstr(incoming,"\r\n\r\n")) { assert(read(peer,incoming+n,1)==1); n++; }
        assert(strstr(incoming,"Authorization: Bearer aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\r\n"));
        const char *header="HTTP/1.0 200 OK\r\nContent-Length: 17\r\n\r\n";
        assert(write(peer,header,strlen(header))==(ssize_t)strlen(header));
        const char *body="received\n\nEEVEE\n\n";
        assert(strlen(body)==17);
        for(size_t i=0;i<(truncated?5:strlen(body));i++) assert(write(peer,body+i,1)==1);
        close(peer); close(listener); _exit(0);
    }
    Config cfg={"127.0.0.1",ntohs(addr.sin_port),"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"};
    Response response; char error[256],value[64];
    int status=request(&cfg,"GET","/v1/health",NULL,0,&response,error,sizeof(error));
    if(truncated) assert(status<0);
    else { assert(status==0); assert(field(&response,1,value,sizeof(value))==0); assert(!strcmp(value,""));
        assert(field(&response,2,value,sizeof(value))==0); assert(!strcmp(value,"EEVEE")); }
    response_free(&response); close(listener); int code; waitpid(child,&code,0); assert(code==0);
}
int main(void) {
    test_hash(); test_files(); test_http(0); test_http(1);
    puts("Native SHA-256, journal, replacement recovery and HTTP checks passed."); return 0;
}
