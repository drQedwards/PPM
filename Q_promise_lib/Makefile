# PMLL Promise / Continuation Library
CC      ?= gcc
CFLAGS  ?= -O2 -fPIC -Wall -Wextra -std=c11
CFLAGS  += -I. -I..
CPPFLAGS += -DPMLL_NO_MAIN

# AddressSanitizer (opt-in: make ASAN=1)
ifeq ($(ASAN),1)
CFLAGS += -fsanitize=address -fno-omit-frame-pointer -g
LDFLAGS += -fsanitize=address
endif

PMLL_SRC := ../PMLL.c
LIB_SRC  := qpromise.c
LIB_OBJ  := qpromise.o PMLL_lib.o

.PHONY: all clean test test-asan shared demo

all: shared test_qpromise

shared: libqpromise.so

libqpromise.so: $(LIB_SRC) qpromise.h ../PMLL.h $(PMLL_SRC)
	$(CC) $(CFLAGS) $(CPPFLAGS) -shared $(LIB_SRC) $(PMLL_SRC) -lm -o $@ $(LDFLAGS)

PMLL_lib.o: $(PMLL_SRC) ../PMLL.h
	$(CC) $(CFLAGS) $(CPPFLAGS) -c $(PMLL_SRC) -o $@

qpromise.o: qpromise.c qpromise.h ../PMLL.h
	$(CC) $(CFLAGS) $(CPPFLAGS) -c qpromise.c -o $@

test_qpromise: test_qpromise.c qpromise.c qpromise.h ../PMLL.h $(PMLL_SRC)
	$(CC) $(CFLAGS) $(CPPFLAGS) -g test_qpromise.c qpromise.c $(PMLL_SRC) -lm -o $@ $(LDFLAGS)

test: test_qpromise
	./test_qpromise

test-asan:
	$(MAKE) clean
	$(MAKE) ASAN=1 test

demo: qpromise_demo
qpromise_demo: Promises.c qpromise.c ../PMLL.c qpromise.h
	$(CC) $(CFLAGS) $(CPPFLAGS) -g Promises.c qpromise.c ../PMLL.c -lm -o $@ $(LDFLAGS)

# Legacy shared-object name used by older ctypes tests (same ABI as libqpromise.so)
q_promises.so: libqpromise.so
	cp -f libqpromise.so q_promises.so

clean:
	$(RM) libqpromise.so q_promises.so test_qpromise qpromise_demo \
	      qpromise.o PMLL_lib.o *.o
