#ifndef POKETRADER_CLIENT_H
#define POKETRADER_CLIENT_H
#include <stddef.h>
#include <stdint.h>

#define SAVE_BYTES 131072
#define PATH_CAP 768
#define APP_DIR "sdmc:/3ds/PokeTrader"
#define PENDING_PATH APP_DIR "/pending.txt"

typedef struct { char host[64]; int port; char token[33]; } Config;
typedef struct { unsigned char *data; size_t size; int status; } Response;
typedef struct {
    char id[33], save_id[33], original_hash[65];
    int slot;
    char path[PATH_CAP];
} Pending;

int request(const Config *, const char *method, const char *path,
            const void *body, size_t size, Response *, char *error, size_t error_size);
void response_free(Response *);
int field(const Response *, unsigned index, char *out, size_t capacity);
void sha256_hex(const void *, size_t, char out[65]);
int read_save(const char *path, unsigned char **out, char *error, size_t capacity);
int durable_file(const char *path, const void *bytes, size_t count);
int load_pending(Pending *);
int store_pending(const Pending *);
int apply_result(const Pending *, const void *result, const char *result_hash,
                 char *error, size_t capacity);
#endif
