"""Input validation shared by forms and file uploads."""
import re

import repository as repo

GENDERS = ["Male", "Female", "Other"]
EMAIL_RE = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")


def parse_number(text, label, lo=0.0, hi=100.0, integer=False):
    """Return (value, error). Blank text gives (None, None)."""
    text = ("" if text is None else str(text)).strip()
    if text == "":
        return None, None
    try:
        val = float(text)
    except ValueError:
        return None, f"{label}: '{text}' is not a number."
    if val != val or not lo <= val <= hi:
        return None, f"{label}: must be between {lo:g} and {hi:g}."
    if integer:
        if val != int(val):
            return None, f"{label}: must be a whole number."
        return int(val), None
    return round(val, 2), None


def validate_student(data, student_id=None):
    d = {k: str(data.get(k, "") or "").strip() for k in
         ("usn", "name", "gender", "semester", "section", "email")}
    d["usn"] = d["usn"].upper()
    d["section"] = d["section"].upper()
    d["gender"] = d["gender"].title()
    errors = {}

    if not d["usn"]:
        errors["usn"] = "USN is required."
    elif not re.fullmatch(r"[A-Z0-9]{4,20}", d["usn"]):
        errors["usn"] = "Use 4 to 20 letters or digits, no spaces."
    else:
        existing = repo.get_student_by_usn(d["usn"])
        if existing and existing["student_id"] != student_id:
            errors["usn"] = "A student with this USN already exists."

    if not d["name"]:
        errors["name"] = "Name is required."
    elif len(d["name"]) > 80:
        errors["name"] = "Name must be 80 characters or fewer."

    if d["gender"] not in GENDERS:
        errors["gender"] = "Choose Male, Female or Other."

    sem, err = parse_number(d["semester"], "Semester", 1, 8, integer=True)
    if sem is None:
        errors["semester"] = err or "Semester is required."
    d["semester"] = sem

    if not d["section"] or len(d["section"]) > 5:
        errors["section"] = "Section is required (up to 5 characters)."
    if d["email"] and not EMAIL_RE.fullmatch(d["email"]):
        errors["email"] = "Enter a valid email address."
    return d, errors


def validate_subject(data, subject_id=None):
    d = {k: str(data.get(k, "") or "").strip() for k in
         ("subject_code", "subject_name", "semester", "credits")}
    d["subject_code"] = d["subject_code"].upper()
    errors = {}

    if not re.fullmatch(r"[A-Z0-9]{3,12}", d["subject_code"]):
        errors["subject_code"] = "Use 3 to 12 letters or digits, no spaces."
    else:
        existing = repo.get_subject_by_code(d["subject_code"])
        if existing and existing["subject_id"] != subject_id:
            errors["subject_code"] = "This subject code already exists."
    if not d["subject_name"]:
        errors["subject_name"] = "Subject name is required."
    sem, err = parse_number(d["semester"], "Semester", 1, 8, integer=True)
    if sem is None:
        errors["semester"] = err or "Semester is required."
    d["semester"] = sem
    cred, err = parse_number(d["credits"], "Credits", 1, 10, integer=True)
    if cred is None:
        errors["credits"] = err or "Credits are required."
    d["credits"] = cred
    return d, errors


def parse_entry_row(raw, who):
    """Validate one row of the marks/attendance grid. Returns (values, errors)."""
    vals, errs = {}, []
    for field, label in (("internal1", "Internal 1"), ("internal2", "Internal 2"),
                         ("assignment", "Assignment"), ("final_mark", "Final")):
        vals[field], e = parse_number(raw.get(field), f"{who} - {label}")
        if e:
            errs.append(e)
    vals["classes_held"], e = parse_number(raw.get("classes_held"), f"{who} - Classes held",
                                           0, 500, integer=True)
    if e:
        errs.append(e)
    vals["classes_attended"], e = parse_number(raw.get("classes_attended"),
                                               f"{who} - Classes attended", 0, 500, integer=True)
    if e:
        errs.append(e)
    held, att = vals["classes_held"], vals["classes_attended"]
    if att is not None and held is None:
        errs.append(f"{who}: enter classes held along with classes attended.")
    if held is not None and att is None:
        errs.append(f"{who}: enter classes attended along with classes held.")
    if held is not None and att is not None and att > held:
        errs.append(f"{who}: attended ({att}) cannot exceed held ({held}).")
    return vals, errs
