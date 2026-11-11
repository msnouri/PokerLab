"""Measure rendered-image recognition + policy, excluding human review/capture.

Run from the repo root: python -m desktop.benchmark --frames 20
This is an in-domain integration benchmark, not real-client recognition proof.
"""
import argparse
import json
import platform
import statistics
import time
from pathlib import Path

from .model import Advisor
from .practice import PracticeTable
from .render import render_table,standard_profile
from .vision import Reader,tesseract_path


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--frames",type=int,default=20)
    parser.add_argument("--output",type=Path)
    args=parser.parse_args()
    if not 1<=args.frames<=200:
        parser.error("Use 1–200 frames.")
    if not tesseract_path():
        parser.error("Install the optional Tesseract engine to benchmark number recognition.")
    table=PracticeTable(seed=20261111)
    reader=Reader(standard_profile());advisor=Advisor()
    snapshots=[]
    for _ in range(100):
        while table.view()["pending"] and len(snapshots)<args.frames:
            snapshots.append(table.view())
            table.act("call")
        if len(snapshots)>=args.frames:
            break
        table.new_hand()
    timings=[];failures=[];streets={}
    for i,view in enumerate(snapshots):
        image=render_table(view)
        start=time.perf_counter()
        result=reader.read(image)
        values=result["values"];expected=view["observation"]
        errors=dict(result["errors"])
        if (values.get("hole_1"),values.get("hole_2")) != view["hole"]:
            errors["hole"]="Wrong or unread hole cards"
        if tuple(values.get(f"board_{j}") for j in range(1,6) if values.get(f"board_{j}")) != view["board"]:
            errors["board"]="Wrong or unread board"
        for key in ("pot","stack","to_call","bet","min_raise_to","max_raise_to"):
            if key not in values or values[key]!=expected[key]:
                errors[key]=f"Expected {expected[key]}, got {values.get(key)}"
        # Only issue advice when the independently checked image-derived fields
        # agree with the engine. Context/history remains engine-derived here.
        if not errors:
            data={**expected,**{k:values[k] for k in ("pot","stack","to_call","bet","min_raise_to","max_raise_to")},
                  "hole":(values["hole_1"],values["hole_2"]),
                  "board":tuple(values[f"board_{j}"] for j in range(1,6) if values[f"board_{j}"])}
            advisor.recommend(data)
        else:
            failures.append({"frame":i,"errors":errors})
        timings.append((time.perf_counter()-start)*1000)
        street=str(len(view["board"]));streets[street]=streets.get(street,0)+1
    report={"platform":platform.platform(),"python":platform.python_version(),"frames":len(timings),
            "scope":"Bundled table artwork; exact crops; engine supplies history/context. Excludes screen capture and human review. Not a Mac or external-client benchmark.",
            "street_board_counts":streets,"fully_correct_frames":len(timings)-len(failures),
            "median_pipeline_ms":round(statistics.median(timings),2),"max_pipeline_ms":round(max(timings),2),
            "failures":failures}
    content=json.dumps(report,indent=2)+"\n"
    if args.output:
        args.output.write_text(content)
    print(content)
    raise SystemExit(bool(failures))


if __name__=="__main__":
    main()
