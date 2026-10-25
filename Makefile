# Whole-project tasks (run from the repository root). Backend-only tasks live in backend/Makefile.
.PHONY: help check build qa-admin qa deploy rehearse panel

help:
	@echo "panel      the one-click local panel (start / stop / status / logs ...): scripts/panel.sh, or double-click run-local.command"
	@echo "check      backend (ruff + tests) and front end (typecheck + lint + unit tests): what must be green before a release"
	@echo "build      build the front end (typecheck, vite, postbuild checks and size budgets)"
	@echo "qa         browser checks of the public site in Chromium and WebKit (needs the server on :5300 with demo content)"
	@echo "qa-admin   browser checks of the admin (starts the separate QA instance on :5310 if needed)"
	@echo "rehearse   rehearse install / update / failed updates / restore drill in a throw-away folder"
	@echo "deploy     make deploy HOST=ssh-host [URL=https://...]   (see deploy/README.md)"

panel:
	@scripts/panel.sh

check:
	$(MAKE) -C backend check
	cd frontend && npm run check

build:
	cd frontend && npm run build

qa:
	cd frontend && npm run qa

qa-admin:
	scripts/qa-instance.sh start
	cd frontend && npm run qa:admin

rehearse:
	deploy/rehearse.sh

deploy:
	@test -n "$(HOST)" || (echo "usage: make deploy HOST=ssh-host [URL=https://your.domain]"; exit 2)
	deploy/deploy.sh $(HOST) $(if $(URL),--url $(URL))
