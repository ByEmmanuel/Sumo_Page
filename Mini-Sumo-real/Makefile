# Gelatina Nuclear -- atajos del ciclo de iteracion.

.PHONY: medir check sitio links limpiar ayuda

ayuda:
	@echo ""
	@echo "  make medir    Compila y mide el algoritmo actual contra los 4 rivales"
	@echo "  make check    Falla si hay codigo de control sin versionar"
	@echo "  make sitio    Regenera site/index.html desde versions/"
	@echo "  make links    Rehace los enlaces del controlador de Webots"
	@echo "  make limpiar  Borra los binarios del banco de pruebas"
	@echo ""

medir:
	@$(MAKE) --no-print-directory -C tests
	@./tests/build/harness --all --rounds 60 --version WORK --out runs/ultimo.json

check:
	@python3 tools/gnver.py check

sitio:
	@python3 tools/build_site.py

links:
	@$(MAKE) --no-print-directory -C webots/controllers/gelatina_nuclear links

limpiar:
	@$(MAKE) --no-print-directory -C tests clean
