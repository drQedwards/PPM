CC      := gcc
CFLAGS  := -O2 -fPIC -Wall -Wextra
TARGET  := q_promises.so

# Shared library from Q_promises.c
$(TARGET): Q_promises.c Q_promises.h
	$(CC) $(CFLAGS) -shared Q_promises.c -o $@

# Standalone test binary from Promises.c
test_promises: Promises.c
	$(CC) $(CFLAGS) -o $@ $<

test: test_promises
	./test_promises

install: $(TARGET)
	mkdir -p ~/.pypm/plugins
	cp $(TARGET) ~/.pypm/plugins/

clean:
	$(RM) $(TARGET) test_promises

.PHONY: test install clean
