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

.PHONY: all
all: $(TARGET).3dsx

build:
	mkdir -p build

build/%.o: source/%.c include/client.h | build
	$(CC) $(CFLAGS) -MMD -MP -c $< -o $@

$(TARGET).elf: $(OBJECTS)
	$(CC) $(LDFLAGS) $(OBJECTS) $(LIBS) -o $@

$(TARGET).smdh:
	smdhtool --create "PokeTrader" "FRLG save exchange" "PokeTrader contributors" $(CTRULIB)/default_icon.png $@

$(TARGET).3dsx: $(TARGET).elf $(TARGET).smdh
	3dsxtool $< $@ --smdh=$(TARGET).smdh

-include build/*.d
