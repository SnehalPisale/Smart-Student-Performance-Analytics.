"""Descriptive analytics with Pandas / NumPy. Returns JSON-safe structures."""
import numpy as np
import pandas as pd
from flask import current_app

import repository as repo
from db import get_db


def _f(x, nd=1):
    try:
        if x is None or pd.isna(x):
            return None
        return round(float(x), nd)
    except (TypeError, ValueError):
        return None


def load_frame():
    """One row per student x subject with marks and attendance."""
    sql = """
        SELECT st.student_id, st.usn, st.name, st.gender, st.semester, st.section,
               sub.subject_id, sub.subject_code, sub.subject_name,
               m.internal1, m.internal2, m.assignment, m.final_mark,
               a.classes_held, a.classes_attended
        FROM marks m
        JOIN students st ON st.student_id = m.student_id
        JOIN subjects sub ON sub.subject_id = m.subject_id
        LEFT JOIN attendance a ON a.student_id = m.student_id AND a.subject_id = m.subject_id"""
    df = pd.read_sql_query(sql, get_db())
    held = df["classes_held"].where(df["classes_held"] > 0)
    df["attendance_pct"] = (df["classes_attended"] / held * 100).round(1)
    df["internal_score"] = (0.35 * df["internal1"] + 0.35 * df["internal2"]
                            + 0.30 * df["assignment"]).round(1)
    return df


def student_summary(df=None):
    """dict: student_id -> averages across subjects."""
    df = load_frame() if df is None else df
    if df.empty:
        return {}
    pass_mark = current_app.config["PASS_MARK"]
    g = df.assign(_weak=(df["internal_score"] < pass_mark).astype(int)).groupby("student_id")
    out = pd.DataFrame({
        "avg_internal": g["internal_score"].mean(),
        "avg_attendance": g["attendance_pct"].mean(),
        "avg_final": g["final_mark"].mean(),
        "subjects": g["subject_id"].count(),
        "weak_subjects": g["_weak"].sum(),
    })
    return {int(sid): {"avg_internal": _f(r.avg_internal), "avg_attendance": _f(r.avg_attendance),
                       "avg_final": _f(r.avg_final), "subjects": int(r.subjects),
                       "weak_subjects": int(r.weak_subjects)}
            for sid, r in out.iterrows()}


def _subject_table(df):
    if df.empty:
        return []
    pass_mark = current_app.config["PASS_MARK"]
    rows = []
    for (code, name), grp in df.groupby(["subject_code", "subject_name"]):
        finals = grp["final_mark"].dropna()
        rows.append({
            "code": code, "name": name,
            "internal": _f(grp["internal_score"].mean()),
            "final": _f(grp["final_mark"].mean()),
            "attendance": _f(grp["attendance_pct"].mean()),
            "pass_rate": _f((finals >= pass_mark).mean() * 100) if len(finals) else None,
            "students": int(grp["student_id"].nunique()),
        })
    return rows


def prediction_table():
    """Latest prediction per student, enriched with the reasons behind the risk."""
    cfg = current_app.config
    summary = student_summary()
    rows = []
    for r in repo.latest_predictions():
        p = dict(r)
        s = summary.get(p["student_id"], {})
        p["avg_attendance"] = s.get("avg_attendance")
        p["avg_internal"] = s.get("avg_internal")
        p["weak_subjects"] = s.get("weak_subjects", 0)
        reasons = []
        if p["avg_attendance"] is not None and p["avg_attendance"] < cfg["MEDIUM_ATTENDANCE"]:
            reasons.append(f"Attendance is {p['avg_attendance']}%")
        if p["avg_internal"] is not None and p["avg_internal"] < cfg["MEDIUM_SCORE"]:
            reasons.append(f"Internal average is {p['avg_internal']}")
        if p["weak_subjects"]:
            reasons.append(f"{p['weak_subjects']} subject(s) with internals below {cfg['PASS_MARK']}")
        if p["predicted_score"] < cfg["MEDIUM_SCORE"]:
            reasons.append(f"Predicted score is {round(p['predicted_score'], 1)}")
        p["reasons"] = reasons
        rows.append(p)
    return rows


def dashboard_data():
    df = load_frame()
    students = repo.list_students()
    preds = {p["student_id"]: p for p in prediction_table()}
    summary = student_summary(df)
    finals = df["final_mark"].dropna() if not df.empty else pd.Series(dtype=float)
    pass_mark = current_app.config["PASS_MARK"]

    counts = {"Low": 0, "Medium": 0, "High": 0}
    for p in preds.values():
        counts[p["risk_level"]] += 1
    last_run = max((p["predicted_at"] for p in preds.values()), default=None)

    roll, scatter = [], []
    for s in students:
        risk = preds[s["student_id"]]["risk_level"] if s["student_id"] in preds else "Unrated"
        roll.append({"id": s["student_id"], "name": s["name"], "usn": s["usn"], "risk": risk})
        sm = summary.get(s["student_id"])
        if sm and sm["avg_attendance"] is not None and sm["avg_internal"] is not None:
            scatter.append({"name": s["name"], "x": sm["avg_attendance"],
                            "y": sm["avg_internal"], "risk": risk})

    semester = []
    if not df.empty:
        for sem, grp in df.groupby("semester"):
            semester.append({"semester": int(sem), "internal": _f(grp["internal_score"].mean()),
                             "attendance": _f(grp["attendance_pct"].mean())})
    return {
        "kpis": {
            "students": len(students),
            "subjects": len(repo.list_subjects()),
            "avg_internal": _f(df["internal_score"].mean()) if not df.empty else None,
            "avg_attendance": _f(df["attendance_pct"].mean()) if not df.empty else None,
            "pass_rate": _f((finals >= pass_mark).mean() * 100) if len(finals) else None,
            "high": counts["High"], "medium": counts["Medium"], "low": counts["Low"],
            "last_run": last_run,
        },
        "subjects": _subject_table(df), "risk_counts": counts,
        "roll": roll, "scatter": scatter, "semester": semester,
    }


def analytics_data(semester=None, section=None):
    df = load_frame()
    if not df.empty:
        if semester:
            df = df[df["semester"] == semester]
        if section:
            df = df[df["section"] == section]
    if df.empty:
        return {"empty": True}

    cols = [("internal1", "Internal 1"), ("internal2", "Internal 2"), ("assignment", "Assignment"),
            ("final_mark", "Final mark"), ("attendance_pct", "Attendance %")]
    describe = []
    for col, label in cols:
        s = df[col].dropna()
        describe.append({"metric": label, "count": int(s.count()), "mean": _f(s.mean()),
                         "std": _f(s.std()), "min": _f(s.min()), "median": _f(s.median()),
                         "max": _f(s.max())})

    edges = list(range(0, 101, 10))
    labels = [f"{a}-{b}" for a, b in zip(edges[:-1], edges[1:])]
    def hist(series):
        counts, _ = np.histogram(series.dropna().clip(0, 100), bins=edges)
        return [int(c) for c in counts]

    bands = pd.cut(df["attendance_pct"], bins=[-0.1, 60, 70, 75, 85, 100.1],
                   labels=["Below 60%", "60-70%", "70-75%", "75-85%", "85%+"])
    band_rows = []
    for band, grp in df.groupby(bands, observed=True):
        band_rows.append({"band": str(band), "students": int(grp["student_id"].nunique()),
                          "avg_internal": _f(grp["internal_score"].mean())})

    corr_cols = ["internal1", "internal2", "assignment", "attendance_pct", "final_mark"]
    corr_labels = ["Internal 1", "Internal 2", "Assignment", "Attendance", "Final"]
    corr = df[corr_cols].corr().round(2)
    matrix = [[None if pd.isna(v) else float(v) for v in row] for row in corr.values]

    sect = [{"section": f"Sem {int(sem)} {sec}", "internal": _f(g["internal_score"].mean()),
             "attendance": _f(g["attendance_pct"].mean())}
            for (sem, sec), g in df.groupby(["semester", "section"])]
    gender = [{"gender": gnd, "internal": _f(g["internal_score"].mean()),
               "students": int(g["student_id"].nunique())} for gnd, g in df.groupby("gender")]

    summ = pd.DataFrame(student_summary(df)).T
    names = df.drop_duplicates("student_id").set_index("student_id")["name"]
    summ["name"] = names
    summ = summ.dropna(subset=["avg_internal"]).sort_values("avg_internal")
    pick = lambda frame: [{"name": r["name"], "avg_internal": _f(r["avg_internal"]),
                           "avg_attendance": _f(r["avg_attendance"])} for _, r in frame.iterrows()]
    return {
        "empty": False, "describe": describe, "subjects": _subject_table(df),
        "hist": {"labels": labels, "internal": hist(df["internal_score"]),
                 "final": hist(df["final_mark"])},
        "bands": band_rows, "corr": {"labels": corr_labels, "matrix": matrix},
        "sections": sect, "gender": gender,
        "bottom": pick(summ.head(5)), "top": pick(summ.tail(5).iloc[::-1]),
    }
