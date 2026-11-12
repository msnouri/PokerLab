.PHONY: install test report gui lab test-gui test-research research-report library-benchmark
install:
	python3 -m pip install -r requirements.txt
test:
	cd poker_lab && python3 -m unittest discover -s tests -v
gui:
	python3 -m desktop
lab:
	python3 -m desktop --lab
library-benchmark:
	cd poker_lab && python3 -m pokerlab.library.benchmark --deals 4000 --workers 4
test-gui:
	QT_QPA_PLATFORM=offscreen python3 -m unittest discover -s desktop/tests -v
test-research:
	PYTHONPATH=poker_lab python3 -m unittest discover -s poker_lab/tests_research -v
research-report:
	python3 research/build_report.py
	cd research && pdflatex -interaction=nonstopmode -halt-on-error poker_research_report.tex
	cd research && pdflatex -interaction=nonstopmode -halt-on-error poker_research_report.tex
report:
	python3 report/build_tables.py
	cd report && pdflatex -interaction=nonstopmode -halt-on-error poker_agent_report.tex
	cd report && pdflatex -interaction=nonstopmode -halt-on-error poker_agent_report.tex
