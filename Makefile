.PHONY: install test report
install:
	python3 -m pip install -r requirements.txt
test:
	cd poker_lab && python3 -m unittest discover -s tests -v
report:
	python3 report/build_tables.py
	cd report && pdflatex -interaction=nonstopmode -halt-on-error poker_agent_report.tex
	cd report && pdflatex -interaction=nonstopmode -halt-on-error poker_agent_report.tex
