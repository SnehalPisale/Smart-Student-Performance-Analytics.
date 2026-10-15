# Smart Student Performance Analytics & Prediction System

A Flask portal that combines marks, attendance and assignment scores to analyse learning
outcomes and flag students who may need academic intervention.

## Quick start

```bash
python -m venv venv
venv\Scripts\activate          # Windows   (macOS/Linux: source venv/bin/activate)
pip install -r requirements.txt
python seed.py                 # optional: loads 60 demo students and runs a first prediction
python app.py                  # open http://127.0.0.1:5000
```

Logins: `admin@college.edu / admin123` (admin) and `teacher@college.edu / teacher123` (teacher).
Without `seed.py`, the app starts empty with only the admin login. Change that password
and set `SECRET_KEY` (environment variable) before any real use.
Charts load Plotly from a CDN, so the first page view needs internet access.

## Modules (as in the project brief)

| Module | Where |
|---|---|
| Admin / login / user management | `/login`, `/register`, `/users` (admin only) |
| Student and course management | `/students`, `/subjects` |
| Marks and attendance entry | `/entry` (class-sheet grid) and `/upload` (CSV / Excel) |
| Data analytics dashboard | `/` and `/analytics` (Pandas + NumPy, Plotly charts) |
| Performance prediction | `/prediction` (Random Forest) |
| At-risk student alerts | `/alerts` |
| Reports and export | `/reports` (CSV, Excel, PDF) and `/history` |

Page flow: Login > Dashboard > Master data > Data entry / upload > Analytics > Prediction > History > Reports.

## Database (SQLite, `instance/student_analytics.db`)

`users`, `students`, `subjects`, `marks`, `attendance`, `predictions` with the fields from the
brief. Primary keys identify records; foreign keys use `ON DELETE CASCADE`, and
`UNIQUE(student_id, subject_id)` on marks and attendance prevents duplicates.

## Code layout (presentation / business logic / data access kept apart)

```
app.py          routes, auth, CSRF           (presentation layer)
analytics.py    Pandas statistics            (business logic)
predictor.py    Random Forest + risk rules   (business logic)
validators.py   input validation             (business logic)
uploads.py      safe file import             (business logic)
reports.py      CSV / Excel / PDF export     (business logic)
repository.py   every SQL statement         (data access)
db.py           connection + schema          (data access)
config.py       thresholds and settings
seed.py         demo data
templates/      Jinja pages     static/   CSS + JS
```

## How the prediction works

All marks are out of 100. Internal score = 35% Internal 1 + 35% Internal 2 + 30% Assignment.

1. Each student-subject row has features: Internal 1, Internal 2, Assignment, Attendance %.
2. A Random Forest regressor learns the final mark from rows that already have one
   (80/20 split to report R-squared and average error, then refit on all labelled rows).
3. It predicts a score for rows with no final mark yet; a student's predicted score is the
   average across subjects. Known final marks are used as-is.
4. Risk: **High** if predicted score < 45 or attendance < 65%; **Medium** if < 60 or < 75%;
   otherwise **Low**. Edit the numbers in `config.py`.
5. Every run is saved with a timestamp in `predictions` (history and audit).

With fewer than 30 labelled rows the app falls back to a weighted formula and says so on the page.
To use Logistic Regression instead, replace the model in `predictor.py` with a classifier on
a pass/fail or risk label.

## File upload formats (sample files can be downloaded from the Upload page)

- Students: `usn,name,gender,semester,section,email`
- Marks: `usn,subject_code,internal1,internal2,assignment,final_mark` (blank keeps existing value)
- Attendance: `usn,subject_code,classes_held,classes_attended`

## Security notes

Hashed passwords, CSRF tokens on every POST, admin-only deletes and user management, parameterised SQL,
auto-escaped templates, `secure_filename` plus an extension whitelist and a 2 MB cap on uploads,
spreadsheet-formula neutralisation in CSV/Excel exports, safe `next=` redirects.

## Ideas to extend

Email alerts to mentors, per-teacher subject assignment, student login to view their own report,
PostgreSQL via SQLAlchemy, and a scheduled weekly prediction run.
