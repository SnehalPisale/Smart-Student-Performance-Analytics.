import numpy as np

import db
import predictor
import repository as repo
from app import app

FINAL_SEMS = {1, 2, 3, 4}   # semesters that get final marks
RUN_PREDICTION = True

FIELDS = ("internal1", "internal2", "assignment", "final_mark")


def clip(x, lo=0, hi=100):
    return float(np.clip(x, lo, hi))


def main():
    with app.app_context():
        filled_m = filled_a = 0
        for sub in repo.list_subjects():
            sheet = repo.entry_sheet(sub["subject_id"])
            existing_held = [r["classes_held"] for r in sheet if r["classes_held"] is not None]
            held = existing_held[0] if existing_held else int(
                np.random.default_rng(sub["subject_id"]).integers(40, 49))

            for r in sheet:
                sid = r["student_id"]
                s = np.random.default_rng(sid)
                ability = clip(s.normal(62, 15), 20, 95)
                att_base = clip(80 + 0.6 * (ability - 62) + s.normal(0, 9), 40, 100)
                n = np.random.default_rng(sid * 1000 + sub["subject_id"])

                i1 = clip(ability + n.normal(0, 8))
                i2 = clip(ability + n.normal(0, 8))
                asg = clip(ability + 8 + n.normal(0, 10))
                gen_att = min(held, int(round(held * clip(att_base + n.normal(0, 5), 30, 100) / 100)))
                att_used = r["classes_attended"] if r["classes_attended"] is not None else gen_att
                final = None
                if sub["semester"] in FINAL_SEMS:
                    final = clip(0.6 * (i1 + i2) / 2 + 0.1 * asg + 0.3 * ability
                                 + 0.25 * (att_used / held * 100 - 75) + n.normal(0, 5))

                new = {"internal1": round(i1, 1), "internal2": round(i2, 1),
                       "assignment": round(asg, 1),
                       "final_mark": None if final is None else round(final, 1)}
                cur = {k: r[k] for k in FIELDS}
                merged = {k: cur[k] if cur[k] is not None else new[k] for k in FIELDS}

                if merged != cur:
                    repo.upsert_marks(sid, sub["subject_id"], merged["internal1"],
                                      merged["internal2"], merged["assignment"],
                                      merged["final_mark"])
                    filled_m += 1

                if r["classes_held"] is None:
                    repo.upsert_attendance(sid, sub["subject_id"], held, gen_att)
                    filled_a += 1

        db.commit()
        print(f"Filled marks for {filled_m} rows, attendance for {filled_a} rows.")

        if RUN_PREDICTION:
            info = predictor.run_prediction()
            print(f"Model: {info['method']}  R2={info['r2']}  MAE={info['mae']}")
            print("Risk split:", info["counts"])


if __name__ == "__main__":
    main()