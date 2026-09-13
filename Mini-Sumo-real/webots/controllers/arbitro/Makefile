C_SOURCES = arbitro.c
CFLAGS   += -std=c99 -Wall -Wextra -O2
ifeq ($(strip $(WEBOTS_HOME)),)
  $(warning WEBOTS_HOME sin definir: este controlador solo compila dentro de Webots)
else
  empty :=
  space := $(empty) $(empty)
  WEBOTS_HOME_PATH ?= $(subst $(space),\ ,$(strip $(subst \,/,$(WEBOTS_HOME))))
  include $(WEBOTS_HOME_PATH)/resources/Makefile.include
endif
