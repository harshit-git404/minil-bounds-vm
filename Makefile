CC ?= gcc
CFLAGS ?= -O2 -std=c11 -Wall -Wextra
PYTHON ?= python3

VM_SRC = vm/vm.c
VM_HDR = vm/vm.h

VM_GOTO = vm/minil-vm-goto
VM_SWITCH = vm/minil-vm-switch
VM_COUNT = vm/minil-vm-count
VM_DEFAULT = vm/minil-vm

.PHONY: all vm test clean env

all: vm env

vm: $(VM_DEFAULT) $(VM_GOTO) $(VM_SWITCH) $(VM_COUNT)

$(VM_GOTO): $(VM_SRC) $(VM_HDR)
	$(CC) $(CFLAGS) -DDISPATCH=GOTO $(VM_SRC) -o $(VM_GOTO)

$(VM_SWITCH): $(VM_SRC) $(VM_HDR)
	$(CC) $(CFLAGS) -DDISPATCH=SWITCH $(VM_SRC) -o $(VM_SWITCH)

$(VM_COUNT): $(VM_SRC) $(VM_HDR)
	$(CC) $(CFLAGS) -DDISPATCH=GOTO -DCOUNT $(VM_SRC) -o $(VM_COUNT)

$(VM_DEFAULT): $(VM_GOTO)
	cp $(VM_GOTO) $(VM_DEFAULT)

env:
	$(PYTHON) scripts/collect_env.py results/env.json "$(CFLAGS)"

test: vm
	$(PYTHON) tests/run_tests.py

clean:
	rm -f vm/minil-vm*
	find . -type d -name "__pycache__" -exec rm -rf {} +
	rm -f tests/*.mbc tests/*/*.mbc
