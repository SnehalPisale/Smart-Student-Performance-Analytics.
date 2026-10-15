import csv
import numpy as np
import repository as repo
from app import app

FINAL_SEMS = {3}   # semesters that also get final marks

def clip(x, lo=0, hi=100):
    return float(np.clip(x, lo, hi))

with app.app_context():
    marks_rows, att_rows = [], []
    for sub in repo.list_subjects():
        sheet = repo.entry_sheet(sub["subject_id"])
        held_existing = [r["classes_held"] for r in sheet if r["classes_held"] is not None]
        held = held_existing[0] if held_existing else int(
            np.random.default_rng(sub["subject_id"]).integers(40, 49))
        for r in sheet:
            sid = r["student_id"]
            s = np.random.default_rng(sid)
            ability = clip(s.normal(62, 15), 20, 95)
            att = clip(80 + 0.6 * (ability - 62) + s.normal(0, 9), 40, 100)
            n = np.random.default_rng(sid * 1000 + sub["subject_id"])
            i1 = clip(ability + n.normal(0, 8))
            i2 = clip(ability + n.normal(0, 8))
            asg = clip(ability + 8 + n.normal(0, 10))
            attended = min(held, int(round(held * clip(att + n.normal(0, 5), 30, 100) / 100)))
            final = ""
            if sub["semester"] in FINAL_SEMS:
                final = round(clip(0.6 * (i1 + i2) / 2 + 0.1 * asg + 0.3 * ability
                                   + 0.25 * (attended / held * 100 - 75) + n.normal(0, 5)), 1)

            has_marks = any(r[k] is not None for k in
                            ("internal1", "internal2", "assignment", "final_mark"))
            if not has_marks:
                marks_rows.append([r["usn"], sub["subject_code"], round(i1, 1),
                                   round(i2, 1), round(asg, 1), final])
            if r["classes_held"] is None:
                att_rows.append([r["usn"], sub["subject_code"], held, attended])

    with open("marks.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["usn", "subject_code", "internal1", "internal2", "assignment", "final_mark"])
        w.writerows(marks_rows)

    with open("attendance.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["usn", "subject_code", "classes_held", "classes_attended"])
        w.writerows(att_rows)

    print("marks.csv:", len(marks_rows), "rows | attendance.csv:", len(att_rows), "rows")