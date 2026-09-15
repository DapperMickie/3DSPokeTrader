/* Offscreen captures use the same renderer and assets as the 3DS executable. */
#include "ui.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
static void capture(const char *name) {
    UiScreen *screens[]={&ui_top,&ui_bottom};
    for(int i=0;i<2;i++) {
        char path[256]; snprintf(path,sizeof(path),"docs/screenshots/%s-%s.ppm",name,i?"bottom":"top");
        FILE *f=fopen(path,"wb"); assert(f); fprintf(f,"P6\n%d 240\n255\n",screens[i]->width);
        assert(fwrite(screens[i]->pixels,3,(size_t)screens[i]->width*240,f)==(size_t)screens[i]->width*240); fclose(f);
    }
}
int main(void) {
    assert(ui_init("3ds/romfs/ui")==0);
    assert(ui_grid_hit(10,42)==0); assert(ui_grid_hit(309,206)==29);
    assert(ui_grid_hit(310,206)==-1); assert(ui_grid_hit(20,207)==-1);
    UiPokemon mons[30]={0};
    assert(ui_parse_pokemon("0\t25\t0\t1\t42\t1\tELECTRIC\tELECTRIC\tPikachu\tSPARKY\tRED\t12345\tJolly\t",&mons[0])==0);
    assert(ui_parse_pokemon("broken",&mons[1])==-1);
    assert(ui_parse_pokemon("1\t999\t0\t1\t42\t1\tELECTRIC\tELECTRIC\tPikachu\tSPARKY\tRED\t12345\tJolly\t",&mons[1])==-1);
    UiEntry entries[]={{"FireRed.sav",0},{"LeafGreen.sav",0},{"VC exports",1},{"Emulator saves",1}};
    ui_browser("sdmc:/Pokemon/",entries,4,0); capture("01-save-browser");
    int species[]={25,6,9,3,133,143,59,131,94,149,130,65,38,123,36,68,76,103,134,135,136,144,145,146};
    for(int i=1;i<24;i++) { mons[i]=mons[0]; mons[i].dex=species[i]; }
    ui_box(mons,0,0,"RED","live"); capture("02-pokemon-box");
    ui_status("prepared","","","live"); capture("03-start-trade");
    ui_status("received","","Eevee / Lv. 25","live"); capture("04-confirm-save");
    ui_status("uncertain","The connection ended before the bridge could confirm the result. Check the Switch and resolve this trade on the bridge before starting another.","","live"); capture("05-recovery");
    ui_message("Save updated","The received Pokemon is in the selected box slot.\n\nEmulator: load the in-game save, not an old state.\nVC export: import this save back into the title.\n\nBackups remain on your SD card.",0); capture("06-complete");
    ui_home(0,0,0,"Set up your bridge in Settings"); capture("07-home");
    ui_settings(0,"192.168.1.50",8765,1,"Not tested",0); capture("08-settings");
    ui_settings(3,"192.168.1.50",8765,1,"Bridge tested / LIVE",0); capture("09-connected");
    ui_home(0,1,1,"Bridge tested / LIVE"); capture("10-resume-home");
    ui_close(); puts("UI parsing, hit targets and ten screen captures passed."); return 0;
}
