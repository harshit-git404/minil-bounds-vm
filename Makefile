CC ?= gcc
CFLAGS ?= -O2 -std=c11 -Wall -Wextra
PYTHON ?= python3

VM_SRC = vm/vm.c
VM_HDR = vm/vm.h

VM_GOTO = vm/minil-vm-goto
VM_SWITCH = vm/minil-vm-switch
VM_DIRECT = vm/minil-vm-direct
VM_COUNT = vm/minil-vm-count
VM_DEFAULT = vm/minil-vm

# Experimental decomposition & ablation builds
VM_DECOMP_GOTO = vm/minil-vm-decomp-goto
VM_DECOMP_SWITCH = vm/minil-vm-decomp-switch
VM_DECOMP_DIRECT = vm/minil-vm-decomp-direct
VM_OPT3 = vm/minil-vm-opt3

.PHONY: all vm test clean env experiments decomp_experiments

all: vm env

experiments: vm env
	$(PYTHON) scripts/run_timing_harness.py

decomp_experiments: vm env
	$(PYTHON) scripts/run_decomposition.py

vm: $(VM_DEFAULT) $(VM_GOTO) $(VM_SWITCH) $(VM_DIRECT) $(VM_COUNT) $(VM_DECOMP_GOTO) $(VM_DECOMP_SWITCH) $(VM_DECOMP_DIRECT) $(VM_OPT3)

$(VM_GOTO): $(VM_SRC) $(VM_HDR)
	$(CC) $(CFLAGS) -DDISPATCH=GOTO $(VM_SRC) -o $(VM_GOTO)

$(VM_SWITCH): $(VM_SRC) $(VM_HDR)
	$(CC) $(CFLAGS) -DDISPATCH=SWITCH $(VM_SRC) -o $(VM_SWITCH)

$(VM_DIRECT): $(VM_SRC) $(VM_HDR)
	$(CC) $(CFLAGS) -DDISPATCH=DIRECT $(VM_SRC) -o $(VM_DIRECT)

$(VM_COUNT): $(VM_SRC) $(VM_HDR)
	$(CC) $(CFLAGS) -DDISPATCH=GOTO -DCOUNT $(VM_SRC) -o $(VM_COUNT)

$(VM_DECOMP_GOTO): $(VM_SRC) $(VM_HDR)
	$(CC) $(CFLAGS) -DDISPATCH=GOTO -DEXPERIMENTAL_DECOMP $(VM_SRC) -o $(VM_DECOMP_GOTO)

$(VM_DECOMP_SWITCH): $(VM_SRC) $(VM_HDR)
	$(CC) $(CFLAGS) -DDISPATCH=SWITCH -DEXPERIMENTAL_DECOMP $(VM_SRC) -o $(VM_DECOMP_SWITCH)

$(VM_DECOMP_DIRECT): $(VM_SRC) $(VM_HDR)
	$(CC) $(CFLAGS) -DDISPATCH=DIRECT -DEXPERIMENTAL_DECOMP $(VM_SRC) -o $(VM_DECOMP_DIRECT)

$(VM_OPT3): $(VM_SRC) $(VM_HDR)
	$(CC) -O3 -std=c11 -Wall -Wextra -DDISPATCH=GOTO $(VM_SRC) -o $(VM_OPT3)

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
