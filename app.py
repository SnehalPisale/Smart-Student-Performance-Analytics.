"""Smart Student Performance Analytics & Prediction System - Flask routes."""
import re
import secrets
from functools import wraps

from flask import (Flask, abort, flash, g, jsonify, redirect, render_template, request,
                   session, url_for, Response)
from werkzeug.security import check_password_hash, generate_password_hash

import analytics
import db
import predictor
import reports
import repository as repo
import uploads
import validators as v
from config import Config

app = Flask(__name__)
app.config.from_object(Config)
app.teardown_appcontext(db.close_db)

with app.app_context():
    db.init_db()
    repo.ensure_default_admin()


# ---------------------------------------------------------------- security helpers
def csrf_token():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_hex(16)
    return session["csrf_token"]


app.jinja_env.globals["csrf_token"] = csrf_token


@app.before_request
def load_user_and_check_csrf():
    uid = session.get("user_id")
    g.user = repo.get_user(uid) if uid else None
    if request.method == "POST":
        sent = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token")
        if not sent or not secrets.compare_digest(sent, session.get("csrf_token", "")):
            abort(400, "Your session expired or the form was invalid. Go back and try again.")


@app.after_request
def security_headers(resp):
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("X-Frame-Options", "DENY")
    resp.headers.setdefault("Referrer-Policy", "same-origin")
    return resp


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if g.user is None:
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if g.user is None:
            return redirect(url_for("login", next=request.path))
        if g.user["role"] != "admin":
            abort(403)
        return view(*args, **kwargs)
    return wrapped


@app.errorhandler(400)
@app.errorhandler(403)
@app.errorhandler(404)
@app.errorhandler(413)
def http_error(err):
    messages = {413: "That file is larger than the 2 MB limit.",
                403: "Only administrators can open this page.",
                404: "That page does not exist."}
    msg = messages.get(err.code, getattr(err, "description", "Something went wrong."))
    return render_template("error.html", code=err.code, message=msg), err.code


# ---------------------------------------------------------------- auth
@app.route("/login", methods=["GET", "POST"])
def login():
    if g.user:
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        user = repo.get_user_by_email(request.form.get("email", "").strip())
        if user and check_password_hash(user["password_hash"], request.form.get("password", "")):
            session.clear()
            session["user_id"] = user["user_id"]
            nxt = request.args.get("next", "")
            if not nxt.startswith("/") or nxt.startswith("//"):
                nxt = url_for("dashboard")
            return redirect(nxt)
        flash("The email or password is incorrect.", "error")
    return render_template("login.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if g.user:
        return redirect(url_for("dashboard"))
    values, errors = {}, {}
    if request.method == "POST":
        values = {k: request.form.get(k, "").strip() for k in ("name", "email")}
        pw = request.form.get("password", "")
        if not values["name"]:
            errors["name"] = "Name is required."
        if not v.EMAIL_RE.fullmatch(values["email"]):
            errors["email"] = "Enter a valid email address."
        elif repo.get_user_by_email(values["email"]):
            errors["email"] = "An account with this email already exists."
        if len(pw) < 8:
            errors["password"] = "Use at least 8 characters."
        if pw != request.form.get("confirm", ""):
            errors["confirm"] = "Passwords do not match."
        if not errors:
            repo.create_user(values["name"], values["email"], generate_password_hash(pw), "teacher")
            flash("Account created. Sign in to continue.", "ok")
            return redirect(url_for("login"))
    return render_template("register.html", values=values, errors=errors)


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("login"))


# ---------------------------------------------------------------- dashboard
@app.route("/")
@login_required
def dashboard():
    return render_template("dashboard.html")


@app.route("/api/dashboard")
@login_required
def api_dashboard():
    return jsonify(analytics.dashboard_data())


# ---------------------------------------------------------------- students
STUDENT_FIELDS = [
    {"name": "usn", "label": "USN", "required": True},
    {"name": "name", "label": "Full name", "required": True},
    {"name": "gender", "label": "Gender", "options": v.GENDERS},
    {"name": "semester", "label": "Semester", "options": list(range(1, 9))},
    {"name": "section", "label": "Section", "required": True},
    {"name": "email", "label": "Email (optional)", "type": "email"},
]
SUBJECT_FIELDS = [
    {"name": "subject_code", "label": "Subject code", "required": True},
    {"name": "subject_name", "label": "Subject name", "required": True},
    {"name": "semester", "label": "Semester", "options": list(range(1, 9))},
    {"name": "credits", "label": "Credits", "options": list(range(1, 7))},
]


@app.route("/students")
@login_required
def students():
    q = request.args.get("q", "").strip()
    sem = request.args.get("semester", type=int)
    sec = request.args.get("section", "").strip()
    return render_template("students.html", students=repo.list_students(q, sem, sec),
                           q=q, sem=sem, sec=sec, sections=repo.distinct_sections(),
                           semesters=range(1, 9))


@app.route("/students/new", methods=["GET", "POST"])
@app.route("/students/<int:sid>/edit", methods=["GET", "POST"])
@login_required
def student_form(sid=None):
    student = repo.get_student(sid) if sid else None
    if sid and not student:
        abort(404)
    values, errors = (dict(student) if student else {"gender": "Male", "semester": 1}), {}
    if request.method == "POST":
        values, errors = v.validate_student(request.form, sid)
        if not errors:
            repo.save_student(values, sid)
            flash("Student saved.", "ok")
            return redirect(url_for("students"))
    return render_template("form.html", title="Edit student" if sid else "Add student",
                           fields=STUDENT_FIELDS, values=values, errors=errors,
                           cancel=url_for("students"))


@app.route("/students/<int:sid>")
@login_required
def student_detail(sid):
    student = repo.get_student(sid)
    if not student:
        abort(404)
    rows = []
    for r in repo.student_subject_rows(sid):
        d = dict(r)
        parts = [d[k] for k in ("internal1", "internal2", "assignment")]
        d["internal_score"] = (round(0.35 * parts[0] + 0.35 * parts[1] + 0.30 * parts[2], 1)
                               if None not in parts else None)
        d["attendance_pct"] = (round(d["classes_attended"] / d["classes_held"] * 100, 1)
                               if d["classes_held"] else None)
        rows.append(d)
    history = repo.prediction_history(sid, limit=1)
    return render_template("student_detail.html", student=student, rows=rows,
                           latest=history[0] if history else None)


@app.route("/students/<int:sid>/delete", methods=["POST"])
@admin_required
def student_delete(sid):
    if repo.get_student(sid):
        repo.delete_student(sid)
        flash("Student and all linked records deleted.", "ok")
    return redirect(url_for("students"))


@app.route("/api/students/<int:sid>/history")
@login_required
def api_student_history(sid):
    rows = reversed(repo.prediction_history(sid))
    return jsonify([{"at": r["predicted_at"], "score": r["predicted_score"],
                     "risk": r["risk_level"]} for r in rows])


# ---------------------------------------------------------------- subjects
@app.route("/subjects")
@login_required
def subjects():
    return render_template("subjects.html", subjects=repo.list_subjects())


@app.route("/subjects/new", methods=["GET", "POST"])
@app.route("/subjects/<int:sid>/edit", methods=["GET", "POST"])
@login_required
def subject_form(sid=None):
    subject = repo.get_subject(sid) if sid else None
    if sid and not subject:
        abort(404)
    values, errors = (dict(subject) if subject else {"semester": 1, "credits": 3}), {}
    if request.method == "POST":
        values, errors = v.validate_subject(request.form, sid)
        if not errors:
            repo.save_subject(values, sid)
            flash("Subject saved.", "ok")
            return redirect(url_for("subjects"))
    return render_template("form.html", title="Edit subject" if sid else "Add subject",
                           fields=SUBJECT_FIELDS, values=values, errors=errors,
                           cancel=url_for("subjects"))


@app.route("/subjects/<int:sid>/delete", methods=["POST"])
@admin_required
def subject_delete(sid):
    if repo.get_subject(sid):
        repo.delete_subject(sid)
        flash("Subject and its marks and attendance deleted.", "ok")
    return redirect(url_for("subjects"))


# ---------------------------------------------------------------- users (admin)
@app.route("/users")
@admin_required
def users():
    return render_template("users.html", users=repo.list_users())


@app.route("/users/<int:uid>/role", methods=["POST"])
@admin_required
def user_role(uid):
    role = request.form.get("role")
    if role not in ("admin", "teacher") or uid == g.user["user_id"] or not repo.get_user(uid):
        flash("That change is not allowed.", "error")
    else:
        repo.set_user_role(uid, role)
        flash("Role updated.", "ok")
    return redirect(url_for("users"))


@app.route("/users/<int:uid>/delete", methods=["POST"])
@admin_required
def user_delete(uid):
    if uid == g.user["user_id"]:
        flash("You cannot delete your own account.", "error")
    elif repo.get_user(uid):
        repo.delete_user(uid)
        flash("User deleted.", "ok")
    return redirect(url_for("users"))


# ---------------------------------------------------------------- data entry & upload
ENTRY_FIELDS = ("internal1", "internal2", "assignment", "final_mark",
                "classes_held", "classes_attended")


@app.route("/entry", methods=["GET", "POST"])
@login_required
def entry():
    subject_list = repo.list_subjects()
    subject_id = request.values.get("subject_id", type=int)
    subject = repo.get_subject(subject_id) if subject_id else None
    rows = [dict(r) for r in repo.entry_sheet(subject_id)] if subject else []

    if subject and request.method == "POST":
        problems, parsed = [], []
        for r in rows:
            raw = {f: request.form.get(f"{f}_{r['student_id']}", "") for f in ENTRY_FIELDS}
            vals, errs = v.parse_entry_row(raw, r["name"])
            problems += errs
            parsed.append((r, vals, raw))
        if problems:
            for r, _vals, raw in parsed:
                r.update(raw)
            flash(f"{len(problems)} problem(s) found. Nothing was saved.", "error")
            return render_template("entry.html", subjects=subject_list, subject=subject,
                                   rows=rows, problems=problems[:15])
        for r, vals, _raw in parsed:
            has_marks = any(vals[k] is not None for k in ("internal1", "internal2",
                                                           "assignment", "final_mark"))
            if has_marks or r["mark_id"]:
                repo.upsert_marks(r["student_id"], subject_id, vals["internal1"], vals["internal2"],
                                  vals["assignment"], vals["final_mark"], overwrite=True)
            if vals["classes_held"] is not None:
                repo.upsert_attendance(r["student_id"], subject_id, vals["classes_held"],
                                       vals["classes_attended"])
        db.commit()
        flash(f"Saved marks and attendance for {subject['subject_code']}.", "ok")
        return redirect(url_for("entry", subject_id=subject_id))
    return render_template("entry.html", subjects=subject_list, subject=subject,
                           rows=rows, problems=[])


@app.route("/upload", methods=["GET", "POST"])
@login_required
def upload():
    result = None
    if request.method == "POST":
        result = uploads.handle(request.files.get("file"), request.form.get("kind"), app.config)
    return render_template("upload.html", kinds=uploads.KINDS, result=result,
                           selected=request.form.get("kind", "marks"))


@app.route("/upload/sample/<kind>")
@login_required
def upload_sample(kind):
    if kind not in uploads.KINDS:
        abort(404)
    return Response(uploads.KINDS[kind]["sample"], mimetype="text/csv",
                    headers={"Content-Disposition": f"attachment; filename=sample_{kind}.csv"})


# ---------------------------------------------------------------- analytics
@app.route("/analytics")
@login_required
def analytics_page():
    return render_template("analytics.html", semesters=repo.distinct_semesters(),
                           sections=repo.distinct_sections())


@app.route("/api/analytics")
@login_required
def api_analytics():
    return jsonify(analytics.analytics_data(request.args.get("semester", type=int),
                                            request.args.get("section") or None))


# ---------------------------------------------------------------- prediction
@app.route("/prediction")
@login_required
def prediction():
    risk = request.args.get("risk", "")
    rows = analytics.prediction_table()
    if risk in ("Low", "Medium", "High"):
        rows = [r for r in rows if r["risk_level"] == risk]
    return render_template("prediction.html", rows=rows, risk=risk,
                           info=predictor.load_model_info())


@app.route("/prediction/run", methods=["POST"])
@login_required
def prediction_run():
    try:
        info = predictor.run_prediction()
        flash(f"Prediction finished for {info['students']} students: "
              f"{info['counts']['High']} high risk, {info['counts']['Medium']} medium risk.", "ok")
    except ValueError as exc:
        flash(str(exc), "error")
    nxt = request.form.get("next", "")
    return redirect(nxt if nxt in ("/", "/prediction", "/alerts") else url_for("prediction"))


@app.route("/alerts")
@login_required
def alerts():
    rows = [r for r in analytics.prediction_table() if r["risk_level"] in ("High", "Medium")]
    return render_template("alerts.html", rows=rows, info=predictor.load_model_info())


@app.route("/history")
@login_required
def history():
    sid = request.args.get("student_id", type=int)
    return render_template("history.html", runs=repo.run_summary(),
                           records=repo.prediction_history(sid, limit=200), sid=sid,
                           students=repo.list_students())


@app.route("/api/history/runs")
@login_required
def api_history_runs():
    return jsonify([dict(r) for r in repo.run_summary()])


# ---------------------------------------------------------------- reports
@app.route("/reports")
@login_required
def reports_page():
    return render_template("reports.html", datasets=reports.DATASETS)


@app.route("/export/<kind>/<fmt>")
@login_required
def export(kind, fmt):
    if kind not in reports.DATASETS or fmt not in ("csv", "xlsx", "pdf"):
        abort(404)
    return reports.export(kind, fmt)


if __name__ == "__main__":
    app.run(debug=True)
