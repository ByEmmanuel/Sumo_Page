# Banco de pruebas nativo. No necesita Webots.
CC      ?= gcc
CFLAGS  ?= -std=c99 -O2 -Wall -Wextra -Wshadow -I../algorithms
LDFLAGS ?= -lm
BUILD   := build

all: $(BUILD)/harness

$(BUILD)/harness: harness.c ../algorithms/strategy.c ../algorithms/strategy.h \
                  ../algorithms/params.h ../algorithms/sumo_types.h
	@mkdir -p $(BUILD)
	$(CC) $(CFLAGS) harness.c ../algorithms/strategy.c -o $@ $(LDFLAGS)

run: $(BUILD)/harness
	./$(BUILD)/harness --all --rounds 50

clean:
	rm -rf $(BUILD)

.PHONY: all run clean
