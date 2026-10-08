PY_INC  := $(shell python3 -c 'import sysconfig, os; print(sysconfig.get_paths()["include"])')
PY_LIB  := $(shell python3-config --ldflags)
CFLAGS  := -O2 -fPIC -I$(PY_INC) -Wall -Wextra
LDFLAGS := -shared $(PY_LIB)
TARGET  := panda.so

$(TARGET): Panda.c Panda_py.c Panda_py.h
	$(CC) $(CFLAGS) Panda.c Panda_py.c $(LDFLAGS) -o $@

install: $(TARGET)
	mkdir -p ~/.pypm/plugins
	cp $(TARGET) ~/.pypm/plugins/

clean:
	$(RM) $(TARGET)
