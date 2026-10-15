"""Safe CSV/Excel import for students, marks and attendance."""
import os
from datetime import datetime

import pandas as pd
from werkzeug.utils import secure_filename

import db
import repository as repo
import validators as v

KINDS = {
    "students": {
        "label": "Students",
        "required": ["usn", "name", "gender", "semester", "section"],
        "optional": ["email"],
        "sample": "usn,name,gender,semester,section,email\n"
                  "1AB24CS101,Asha Rao,Female,3,A,asha@example.com\n"
                  "1AB24CS102,Vikram Shetty,Male,3,A,\n",
    },
    "marks": {
        "label": "Marks",
        "required": ["usn", "subject_code"],
        "optional": ["internal1", "internal2", "assignment", "final_mark"],
        "sample": "usn,subject_code,internal1,internal2,assignment,final_mark\n"
                  "1AB24CS101,CS301,72,68,80,\n1AB24CS102,CS301,45,50,60,\n",
    },
    "attendance": {
        "label": "Attendance",
        "required": ["usn", "subject_code", "classes_held", "classes_attended"],
        "optional": [],
        "sample": "usn,subject_code,classes_held,classes_attended\n"
                  "1AB24CS101,CS301,42,39\n1AB24CS102,CS301,42,28\n",
    },
}


def _read(path, ext):
    if ext == "csv":
        df = pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    else:
        df = pd.read_excel(path, dtype=str).fillna("")
    df.columns = [str(c).strip().lower() for c in df.columns]
    return df.apply(lambda col: col.astype(str).str.strip())


def handle(file, kind, cfg):
    result = {"saved": 0, "skipped": 0, "errors": [], "filename": None, "kind": kind}
    if kind not in KINDS:
        result["errors"].append("Choose what you are uploading.")
        return result
    if file is None or not file.filename:
        result["errors"].append("Choose a file to upload.")
        return result

    safe = secure_filename(file.filename)
    ext = safe.rsplit(".", 1)[-1].lower() if "." in safe else ""
    if ext not in cfg["ALLOWED_EXTENSIONS"]:
        result["errors"].append("Only .csv and .xlsx files are accepted.")
        return result

    os.makedirs(cfg["UPLOAD_FOLDER"], exist_ok=True)
    stored = f"{datetime.now():%Y%m%d_%H%M%S}_{safe}"
    path = os.path.join(cfg["UPLOAD_FOLDER"], stored)
    file.save(path)
    result["filename"] = stored

    try:
        df = _read(path, ext)
    except Exception:
        result["errors"].append("The file could not be read. Check that it is a valid "
                                "CSV or Excel file with a header row.")
        return result

    spec = KINDS[kind]
    missing = [c for c in spec["required"] if c not in df.columns]
    if missing:
        result["errors"].append("Missing column(s): " + ", ".join(missing))
        return result
    if len(df) > cfg["MAX_UPLOAD_ROWS"]:
        result["errors"].append(f"Too many rows (limit {cfg['MAX_UPLOAD_ROWS']}).")
        return result

    for idx, row in df.iterrows():
        n = idx + 2                                  # header is row 1
        errs = _save_row(kind, row.to_dict())
        if errs:
            result["skipped"] += 1
            result["errors"].extend(f"Row {n}: {e}" for e in errs)
        else:
            result["saved"] += 1
    db.commit()
    return result


def _save_row(kind, row):
    if kind == "students":
        existing = repo.get_student_by_usn(row.get("usn", "").upper())
        data, errors = v.validate_student(row, existing["student_id"] if existing else None)
        if errors:
            return list(errors.values())
        repo.save_student(data, existing["student_id"] if existing else None)
        return []

    student = repo.get_student_by_usn(row.get("usn", "").upper())
    subject = repo.get_subject_by_code(row.get("subject_code", "").upper())
    errs = []
    if not student:
        errs.append(f"unknown USN '{row.get('usn', '')}'")
    if not subject:
        errs.append(f"unknown subject code '{row.get('subject_code', '')}'")
    if errs:
        return errs

    if kind == "marks":
        vals, errs = v.parse_entry_row({k: row.get(k) for k in
                                        ("internal1", "internal2", "assignment", "final_mark")}, "marks")
        errs = [e.replace("marks - ", "") for e in errs if "Classes" not in e]
        if errs:
            return errs
        repo.upsert_marks(student["student_id"], subject["subject_id"], vals["internal1"],
                          vals["internal2"], vals["assignment"], vals["final_mark"],
                          overwrite=False)
    else:
        vals, errs = v.parse_entry_row({"classes_held": row.get("classes_held"),
                                        "classes_attended": row.get("classes_attended")}, "attendance")
        if vals["classes_held"] is None:
            errs.append("classes_held is required")
        errs = [e.replace("attendance - ", "") for e in errs]
        if errs:
            return errs
        repo.upsert_attendance(student["student_id"], subject["subject_id"],
                               vals["classes_held"], vals["classes_attended"])
    return []
