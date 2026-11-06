# Out-of-tree build of gspca_ov519 with the Vista IM (OV519 + OV7670) changes.
obj-m := gspca_ov519.o
gspca_ov519-y := ov519.o
KVER ?= $(shell uname -r)
KDIR ?= /lib/modules/$(KVER)/build

all:
	$(MAKE) -C $(KDIR) M=$(CURDIR) modules

clean:
	$(MAKE) -C $(KDIR) M=$(CURDIR) clean

# Regenerate the register tables from Creative's INF (not distributed).
tables:
	python3 gen_tables.py $(INF) > creative_tables.h
