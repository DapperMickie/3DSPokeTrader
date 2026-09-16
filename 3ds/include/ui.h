#ifndef UI_H
#define UI_H
#include <stddef.h>
typedef struct { unsigned char pixels[400*240*3]; int width; } UiScreen;
typedef struct { int index,dex,shiny,eligible,level,kind; char type[2][16],name[32],nickname[32],trainer[32],tid[12],nature[24],reason[128]; } UiPokemon;
typedef struct { char name[256]; int directory; } UiEntry;
extern UiScreen ui_top,ui_bottom;
int ui_init(const char *directory);
void ui_close(void);
int ui_parse_pokemon(const char *line, UiPokemon *p);
void ui_browser(const char *path,const UiEntry *entries,int count,int cursor);
void ui_box(const UiPokemon *mons,int box,int cursor,const char *trainer,const char *mode);
void ui_status(const char *state,const char *detail,const char *received,const char *mode);
void ui_trade_art(const char *offered,const char *received);
void ui_status_frame(const char *state,const char *detail,const char *received,const char *mode,unsigned elapsed_ms);
void ui_message(const char *title,const char *body,int page);
void ui_home(int cursor,int pending,int configured,const char *connection);
void ui_settings(int cursor,const char *host,int port,int has_token,const char *connection,int locked);
int ui_grid_hit(int x,int y);
#endif
