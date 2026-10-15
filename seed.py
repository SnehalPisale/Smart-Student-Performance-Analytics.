"""Reset the database and fill it with realistic demo data.

Usage:  python seed.py
Sem 3 students have final marks (completed term, used to train the model).
Sem 5 students have internals only (term in progress, the model predicts these).
"""
import numpy as np
from werkzeug.security import generate_password_hash

import db
import predictor
import repository as repo
from app import app

FIRST = ["Aarav", "Ananya", "Rohan", "Diya", "Karthik", "Meera", "Nikhil", "Priya", "Rahul",
         "Sneha", "Varun", "Kavya", "Arjun", "Ishita", "Manoj", "Divya", "Sanjay", "Pooja",
         "Harsha", "Lakshmi", "Tejas", "Riya", "Suresh", "Anjali", "Vivek", "Nandini"]
LAST = ["Rao", "Shetty", "Gowda", "Nair", "Iyer", "Hegde", "Patil", "Kulkarni", "Reddy",
        "Bhat", "Menon", "Kamath", "Naik", "Joshi"]
SUBJECTS = {
    3: [("CS301", "Data Structures", 4), ("CS302", "Discrete Mathematics", 3),
        ("CS303", "Digital Logic Design", 4), ("CS304", "Computer Organization", 3),
        ("CS305", "Object Oriented Programming", 3)],
    5: [("CS501", "Database Management Systems", 4), ("CS502", "Operating Systems", 4),
        ("CS503", "Computer Networks", 3), ("CS504", "Software Engineering", 3),
        ("CS505", "Machine Learning", 4)],
}


def clip(x, lo=0, hi=100):
    return float(np.clip(x, lo, hi))


def main():
    rng = np.random.default_rng(7)
    with app.app_context():
        db.reset_db()
        repo.create_user("Administrator", "admin@college.edu", generate_password_hash("admin123"), "admin")
        repo.create_user("Prof. Meenakshi", "teacher@college.edu", generate_password_hash("teacher123"), "teacher")

        subject_ids = {}
        for sem, items in SUBJECTS.items():
            for code, name, credits in items:
                subject_ids[code] = repo.save_subject(
                    {"subject_code": code, "subject_name": name, "semester": sem, "credits": credits})

        used, n = set(), 0
        for sem, year in ((3, 24), (5, 23)):
            for i in range(30):
                while True:
                    name = f"{rng.choice(FIRST)} {rng.choice(LAST)}"
                    if name not in used:
                        used.add(name)
                        break
                n += 1
                usn = f"1AB{year}CS{n:03d}"
                sid = repo.save_student({
                    "usn": usn, "name": name, "gender": str(rng.choice(["Male", "Female"], p=[.52, .48])),
                    "semester": sem, "section": "A" if i < 15 else "B",
                    "email": f"{name.split()[0].lower()}.{usn.lower()}@college.edu"})
                ability = clip(rng.normal(62, 15), 20, 95)
                att_base = clip(80 + 0.6 * (ability - 62) + rng.normal(0, 9), 40, 100)
                for code, _name, _cr in SUBJECTS[sem]:
                    i1 = clip(ability + rng.normal(0, 8)); i2 = clip(ability + rng.normal(0, 8))
                    asg = clip(ability + 8 + rng.normal(0, 10))
                    held = int(rng.integers(40, 49))
                    attended = int(round(held * clip(att_base + rng.normal(0, 5), 30, 100) / 100))
                    final = None
                    if sem == 3:
                        final = clip(0.6 * (i1 + i2) / 2 + 0.1 * asg + 0.3 * ability
                                     + 0.25 * (attended / held * 100 - 75) + rng.normal(0, 5))
                    repo.upsert_marks(sid, subject_ids[code], round(i1, 1), round(i2, 1),
                                      round(asg, 1), None if final is None else round(final, 1))
                    repo.upsert_attendance(sid, subject_ids[code], held, attended)
        db.commit()
        info = predictor.run_prediction()
        print(f"Seeded {n} students. Model: {info['method']}  R2={info['r2']}  MAE={info['mae']}")
        print("Risk split:", info["counts"])
        print("Logins -> admin@college.edu / admin123   teacher@college.edu / teacher123")


if __name__ == "__main__":
    main()
