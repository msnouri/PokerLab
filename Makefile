.PHONY: install test report gui test-gui
install:
	python3 -m pip install -r requirements.txt
test:
	cd poker_lab && python3 -m unittest discover -s tests -v
gui:
	python3 -m desktop
test-gui:
	QT_QPA_PLATFORM=offscreen python3 -m unittest discover -s desktop/tests -v
report:
	python3 report/build_tables.py
	cd report && pdflatex -interaction=nonstopmode -halt-on-error poker_agent_report.tex
	cd report && pdflatex -interaction=nonstopmode -halt-on-error poker_agent_report.tex
