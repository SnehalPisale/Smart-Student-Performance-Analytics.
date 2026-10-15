"""Repository: every SQL statement lives here (database access layer)."""
from db import q, run, commit, get_db


# ---------- users ----------
def ensure_default_admin():
    from werkzeug.security import generate_password_hash
    if q("SELECT 1 FROM users LIMIT 1", one=True) is None:
        create_user("Administrator", "admin@college.edu",
                    generate_password_hash("admin123"), "admin")


def get_user(user_id):
    return q("SELECT * FROM users WHERE user_id = ?", (user_id,), one=True)


def get_user_by_email(email):
    return q("SELECT * FROM users WHERE email = ?", (email.lower(),), one=True)


def create_user(name, email, password_hash, role="teacher"):
    uid = run("INSERT INTO users(name,email,password_hash,role) VALUES (?,?,?,?)",
              (name, email.lower(), password_hash, role))
    commit()
    return uid


def list_users():
    return q("SELECT user_id,name,email,role,created_at FROM users ORDER BY created_at, name")


def set_user_role(user_id, role):
    run("UPDATE users SET role = ? WHERE user_id = ?", (role, user_id))
    commit()


def delete_user(user_id):
    run("DELETE FROM users WHERE user_id = ?", (user_id,))
    commit()


# ---------- students ----------
def list_students(search="", semester=None, section=None):
    sql, args = "SELECT * FROM students WHERE 1=1", []
    if search:
        sql += " AND (name LIKE ? OR usn LIKE ?)"
        args += [f"%{search}%", f"%{search}%"]
    if semester:
        sql += " AND semester = ?"
        args.append(semester)
    if section:
        sql += " AND section = ?"
        args.append(section)
    return q(sql + " ORDER BY semester, section, name", args)


def distinct_sections():
    return [r["section"] for r in q("SELECT DISTINCT section FROM students ORDER BY section")]


def distinct_semesters():
    return [r["semester"] for r in q("SELECT DISTINCT semester FROM students ORDER BY semester")]


def get_student(student_id):
    return q("SELECT * FROM students WHERE student_id = ?", (student_id,), one=True)


def get_student_by_usn(usn):
    return q("SELECT * FROM students WHERE usn = ?", (usn,), one=True)


def save_student(d, student_id=None):
    vals = (d["usn"], d["name"], d["gender"], d["semester"], d["section"], d["email"] or None)
    if student_id:
        run("UPDATE students SET usn=?,name=?,gender=?,semester=?,section=?,email=? "
            "WHERE student_id=?", vals + (student_id,))
    else:
        student_id = run("INSERT INTO students(usn,name,gender,semester,section,email) "
                         "VALUES (?,?,?,?,?,?)", vals)
    commit()
    return student_id


def delete_student(student_id):
    run("DELETE FROM students WHERE student_id = ?", (student_id,))
    commit()


# ---------- subjects ----------
def list_subjects(semester=None):
    if semester:
        return q("SELECT * FROM subjects WHERE semester=? ORDER BY subject_code", (semester,))
    return q("SELECT * FROM subjects ORDER BY semester, subject_code")


def get_subject(subject_id):
    return q("SELECT * FROM subjects WHERE subject_id = ?", (subject_id,), one=True)


def get_subject_by_code(code):
    return q("SELECT * FROM subjects WHERE subject_code = ?", (code,), one=True)


def save_subject(d, subject_id=None):
    vals = (d["subject_code"], d["subject_name"], d["semester"], d["credits"])
    if subject_id:
        run("UPDATE subjects SET subject_code=?,subject_name=?,semester=?,credits=? "
            "WHERE subject_id=?", vals + (subject_id,))
    else:
        subject_id = run("INSERT INTO subjects(subject_code,subject_name,semester,credits) "
                         "VALUES (?,?,?,?)", vals)
    commit()
    return subject_id


def delete_subject(subject_id):
    run("DELETE FROM subjects WHERE subject_id = ?", (subject_id,))
    commit()


# ---------- marks & attendance (callers commit) ----------
def upsert_marks(student_id, subject_id, i1, i2, asg, final, overwrite=True):
    if overwrite:
        upd = ("internal1=excluded.internal1, internal2=excluded.internal2, "
               "assignment=excluded.assignment, final_mark=excluded.final_mark")
    else:  # blank cells in an upload keep the existing value
        upd = ("internal1=COALESCE(excluded.internal1, marks.internal1), "
               "internal2=COALESCE(excluded.internal2, marks.internal2), "
               "assignment=COALESCE(excluded.assignment, marks.assignment), "
               "final_mark=COALESCE(excluded.final_mark, marks.final_mark)")
    run("INSERT INTO marks(student_id,subject_id,internal1,internal2,assignment,final_mark) "
        "VALUES (?,?,?,?,?,?) ON CONFLICT(student_id,subject_id) DO UPDATE SET " + upd,
        (student_id, subject_id, i1, i2, asg, final))


def upsert_attendance(student_id, subject_id, held, attended):
    run("INSERT INTO attendance(student_id,subject_id,classes_held,classes_attended) "
        "VALUES (?,?,?,?) ON CONFLICT(student_id,subject_id) DO UPDATE SET "
        "classes_held=excluded.classes_held, classes_attended=excluded.classes_attended",
        (student_id, subject_id, held, attended))


def entry_sheet(subject_id):
    return q("""
        SELECT st.student_id, st.usn, st.name,
               m.mark_id, m.internal1, m.internal2, m.assignment, m.final_mark,
               a.attendance_id, a.classes_held, a.classes_attended
        FROM subjects sub
        JOIN students st ON st.semester = sub.semester
        LEFT JOIN marks m ON m.student_id = st.student_id AND m.subject_id = sub.subject_id
        LEFT JOIN attendance a ON a.student_id = st.student_id AND a.subject_id = sub.subject_id
        WHERE sub.subject_id = ?
        ORDER BY st.section, st.name""", (subject_id,))


def student_subject_rows(student_id):
    return q("""
        SELECT sub.subject_code, sub.subject_name, sub.credits,
               m.internal1, m.internal2, m.assignment, m.final_mark,
               a.classes_held, a.classes_attended
        FROM marks m
        JOIN subjects sub ON sub.subject_id = m.subject_id
        LEFT JOIN attendance a ON a.student_id = m.student_id AND a.subject_id = m.subject_id
        WHERE m.student_id = ? ORDER BY sub.subject_code""", (student_id,))


# ---------- predictions ----------
def save_predictions(rows, timestamp):
    get_db().executemany(
        "INSERT INTO predictions(student_id,predicted_score,risk_level,predicted_at) "
        "VALUES (?,?,?,?)", [(sid, score, risk, timestamp) for sid, score, risk in rows])
    commit()


def last_run_time():
    row = q("SELECT MAX(predicted_at) AS t FROM predictions", one=True)
    return row["t"] if row else None


def latest_predictions():
    return q("""
        SELECT p.prediction_id, p.student_id, p.predicted_score, p.risk_level, p.predicted_at,
               s.usn, s.name, s.semester, s.section
        FROM predictions p JOIN students s ON s.student_id = p.student_id
        WHERE p.prediction_id = (SELECT MAX(prediction_id) FROM predictions
                                 WHERE student_id = p.student_id)
        ORDER BY CASE p.risk_level WHEN 'High' THEN 0 WHEN 'Medium' THEN 1 ELSE 2 END,
                 p.predicted_score""")


def prediction_history(student_id=None, limit=500):
    sql = """SELECT p.prediction_id, p.student_id, p.predicted_score, p.risk_level,
                    p.predicted_at, s.usn, s.name
             FROM predictions p JOIN students s ON s.student_id = p.student_id"""
    args = []
    if student_id:
        sql += " WHERE p.student_id = ?"
        args.append(student_id)
    return q(sql + " ORDER BY p.predicted_at DESC, s.name LIMIT ?", args + [limit])


def run_summary():
    return q("""
        SELECT predicted_at, COUNT(*) AS students, ROUND(AVG(predicted_score),1) AS avg_score,
               SUM(risk_level='High') AS high, SUM(risk_level='Medium') AS medium,
               SUM(risk_level='Low') AS low
        FROM predictions GROUP BY predicted_at ORDER BY predicted_at""")
