# TOEFL iBT practice generator: every command in one place.  `make help` lists them.
# Windows: install make (`winget install ezwinports.make` or `choco install make`) and run from any shell.

ifeq ($(OS),Windows_NT)
PY ?= python
else
PY ?= python3
endif
CLAUDE ?= claude
PORT   ?= 8765
LEVEL  ?=
COUNT  ?=
ID     ?= latest
HOME_FLAG := $(if $(filter 1 yes true,$(HE)),--home-edition,)
# Tools Claude may use non-interactively while generating / grading (no prompts in -p mode).
CLAUDE_FLAGS ?= --permission-mode acceptEdits --allowedTools Read Write Edit Glob Grep Agent Skill "Bash(python tools/*)" "Bash(python3 tools/*)"

.PHONY: help setup setup-speech sample test bank next practice weakest take serve audio validate grade regrade report trends list publish import export check

help:            ## show this help
	@$(PY) -c "import re;[print(f'  make {m[0]:<14} {m[1]}') for m in re.findall(r'^([a-z-]+):.*?## (.*)$$', open('Makefile').read(), re.M)]"

setup:           ## install Python deps (web runner, TTS, reports, trends)
	$(PY) -m pip install -r requirements.txt

setup-speech:    ## install Whisper for speaking transcription (~500 MB model download on first use)
	$(PY) -m pip install -r requirements-speech.txt

sample:          ## try the bundled sample test (no Claude needed to take it)
	$(PY) tools/tts.py sample-mini
	$(PY) server/app.py --test sample-mini --port $(PORT) --open $(HOME_FLAG)

test:            ## generate a full adaptive test with Claude, then open it   [LEVEL=easy|medium|hard|mixed] [HE=1 Home Edition rules]
	$(CLAUDE) -p "/toefl-generate full $(LEVEL)" $(CLAUDE_FLAGS)
	$(PY) server/app.py --test latest --port $(PORT) --open $(HOME_FLAG)

bank:            ## pre-generate several full tests: make bank N=5 [LEVEL=hard] [PAR=2]
	$(PY) tools/bank.py $(or $(N),3) $(if $(LEVEL),--level $(LEVEL),) --parallel $(or $(PAR),1)

next:            ## open the next full test you haven't taken yet   [HE=1]
	$(PY) server/app.py --test next --port $(PORT) --open $(HOME_FLAG)

practice:        ## practice one task/section: make practice TASK=interview [COUNT=3] [LEVEL=hard]
	$(CLAUDE) -p "/toefl-practice $(TASK) $(COUNT) $(LEVEL)" $(CLAUDE_FLAGS)
	$(PY) server/app.py --test latest --port $(PORT) --open

weakest:         ## practice set aimed at your most frequent mistakes
	$(CLAUDE) -p "/toefl-practice weakest" $(CLAUDE_FLAGS)
	$(PY) server/app.py --test latest --port $(PORT) --open

take:            ## (re)take a saved test: make take ID=<test_id>   [HE=1 Home Edition rules]
	$(PY) server/app.py --test $(ID) --port $(PORT) --open $(HOME_FLAG)

serve:           ## open the start page (choose / load / import tests, past results)
	$(PY) server/app.py --port $(PORT) --open $(HOME_FLAG)

audio:           ## (re)render TTS audio for a test: make audio ID=<test_id>
	$(PY) tools/tts.py $(if $(filter latest,$(ID)),,$(ID))

validate:        ## validate a test file: make validate ID=<test_id>
	$(PY) tools/validate.py $(ID)

grade:           ## grade an attempt (auto-runs on submit): make grade ID=<attempt_id|latest>
	$(PY) tools/pipeline.py grade $(ID)

regrade:         ## redo transcription + Claude grading for an attempt
	$(PY) tools/pipeline.py grade $(ID) --force

report:          ## re-render the PDF for an attempt
	$(PY) tools/pipeline.py report $(ID)

trends:          ## progress PDF: score history, error trends, predicted band, study plan
	$(CLAUDE) -p "/toefl-trends" $(CLAUDE_FLAGS)

list:            ## list local + library tests
	$(PY) tools/library.py list

publish:         ## save a test to library/ to share it: make publish ID=<test_id> [AUTHOR=name]
	$(PY) tools/library.py publish $(ID) $(if $(AUTHOR),--author "$(AUTHOR)",)

import:          ## load a test file someone shared: make import FILE=path/to/test.json
	$(PY) tools/library.py import "$(FILE)"

export:          ## export a test as one JSON file: make export ID=<test_id>
	$(PY) tools/library.py export $(ID)

check:           ## sanity check: validate library tests and grade a synthetic attempt offline
	$(PY) tools/validate.py $(notdir $(patsubst %/,%,$(dir $(wildcard library/*/test.json))))
	$(PY) tools/selftest.py
