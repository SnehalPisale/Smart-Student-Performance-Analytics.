from app import app
import db
import repository as repo

with app.app_context():
    print("Database file:", app.config["DATABASE"])
    print("Students:", db.q("SELECT COUNT(*) c FROM students", one=True)["c"])
    print("Marks rows:", db.q("SELECT COUNT(*) c FROM marks", one=True)["c"])
    print("Attendance rows:", db.q("SELECT COUNT(*) c FROM attendance", one=True)["c"])
    print("Subjects (code, semester):",
          [(s["subject_code"], s["semester"]) for s in repo.list_subjects()])
    print("Student semesters:", sorted({s["semester"] for s in repo.list_students()}))