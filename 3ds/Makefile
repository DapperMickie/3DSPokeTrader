ifeq ($(strip $(DEVKITARM)),)
$(error Set DEVKITPRO and DEVKITARM to your devkitPro installation)
endif
include $(DEVKITARM)/3ds_rules

TARGET := PokeTrader
ARCH := -march=armv6k -mtune=mpcore -mfloat-abi=hard -mtp=soft
CFLAGS := -std=gnu11 -O2 -g -Wall -Wextra -Werror -mword-relocations -ffunction-sections $(ARCH) -Iinclude -I$(CTRULIB)/include -D__3DS__
LDFLAGS := -specs=3dsx.specs $(ARCH) -Wl,-Map,$(TARGET).map -Wl,--gc-sections
LIBS := -L$(CTRULIB)/lib -lctru -lm
OBJECTS := $(patsubst source/%.c,build/%.o,$(wildcard source/*.c))

.PHONY: all cia clean
all: $(TARGET).3dsx $(TARGET).cia

build:
	mkdir -p build

build/%.o: source/%.c include/client.h | build
	$(CC) $(CFLAGS) -MMD -MP -c $< -o $@

$(TARGET).elf: $(OBJECTS)
	$(CC) $(LDFLAGS) $(OBJECTS) $(LIBS) -o $@

$(TARGET).smdh:
	smdhtool --create "PokeTrader" "FRLG save exchange" "PokeTrader contributors" $(CTRULIB)/default_icon.png $@

$(TARGET).3dsx: $(TARGET).elf $(TARGET).smdh $(wildcard romfs/ui/*)
	3dsxtool $< $@ --smdh=$(TARGET).smdh --romfs=romfs

# Package the same ELF as an installable HOME Menu application.  The 3DSX
# and CIA formats are two different containers, so the CIA is built directly
# from the ELF rather than by renaming/converting the 3DSX.
$(TARGET).cia: $(TARGET).elf $(TARGET).smdh cia.rsf $(wildcard romfs/ui/*)
	makerom -f cia -o $@ -target t -exefslogo -elf $(TARGET).elf \
		-rsf cia.rsf -icon $(TARGET).smdh \
		-romfs romfs

clean:
	rm -rf build $(TARGET).elf $(TARGET).map $(TARGET).3dsx $(TARGET).smdh $(TARGET).cia

-include build/*.d
