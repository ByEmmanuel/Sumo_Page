# Controlador de Gelatina Nuclear para Webots.
#
# strategy.c, strategy.h, params.h y sumo_types.h son ENLACES SIMBOLICOS a
# ../../../algorithms/. Asi el algoritmo vive en un solo sitio -el que versiona
# la bitacora- y Webots lo compila sin rutas relativas fragiles.
# Si los enlaces se pierden (copia a Windows, zip, etc.):  make links

C_SOURCES = main.c hal_webots.c strategy.c
CFLAGS   += -std=c99 -Wall -Wextra -O2

links:
	ln -sf ../../../algorithms/strategy.c   strategy.c
	ln -sf ../../../algorithms/strategy.h   strategy.h
	ln -sf ../../../algorithms/params.h     params.h
	ln -sf ../../../algorithms/sumo_types.h sumo_types.h

.PHONY: links

# El bloque de Webots solo se activa si WEBOTS_HOME existe, para que
# 'make links' siga funcionando en una maquina sin Webots instalado.
ifeq ($(strip $(WEBOTS_HOME)),)
  $(warning WEBOTS_HOME sin definir: solo esta disponible el objetivo 'links')
else
  space :=
  space +=
  WEBOTS_HOME_PATH ?= $(subst $(space),\ ,$(strip $(subst \,/,$(WEBOTS_HOME))))
  include $(WEBOTS_HOME_PATH)/resources/Makefile.include
endif
