"""Database access layer: connection handling and schema."""
import os
import sqlite3

from flask import current_app, g

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT NOT NULL,
    email         TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL DEFAULT 'teacher' CHECK (role IN ('admin','teacher')),
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS students (
    student_id INTEGER PRIMARY KEY AUTOINCREMENT,
    usn        TEXT NOT NULL UNIQUE,
    name       TEXT NOT NULL,
    gender     TEXT NOT NULL,
    semester   INTEGER NOT NULL CHECK (semester BETWEEN 1 AND 8),
    section    TEXT NOT NULL,
    email      TEXT
);

CREATE TABLE IF NOT EXISTS subjects (
    subject_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    subject_code TEXT NOT NULL UNIQUE,
    subject_name TEXT NOT NULL,
    semester     INTEGER NOT NULL CHECK (semester BETWEEN 1 AND 8),
    credits      INTEGER NOT NULL CHECK (credits BETWEEN 1 AND 10)
);

CREATE TABLE IF NOT EXISTS marks (
    mark_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER NOT NULL REFERENCES students(student_id) ON DELETE CASCADE,
    subject_id INTEGER NOT NULL REFERENCES subjects(subject_id) ON DELETE CASCADE,
    internal1  REAL, internal2 REAL, assignment REAL, final_mark REAL,
    UNIQUE (student_id, subject_id)
);

CREATE TABLE IF NOT EXISTS attendance (
    attendance_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id       INTEGER NOT NULL REFERENCES students(student_id) ON DELETE CASCADE,
    subject_id       INTEGER NOT NULL REFERENCES subjects(subject_id) ON DELETE CASCADE,
    classes_held     INTEGER NOT NULL CHECK (classes_held >= 0),
    classes_attended INTEGER NOT NULL CHECK (classes_attended >= 0),
    UNIQUE (student_id, subject_id)
);

CREATE TABLE IF NOT EXISTS predictions (
    prediction_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id      INTEGER NOT NULL REFERENCES students(student_id) ON DELETE CASCADE,
    predicted_score REAL NOT NULL,
    risk_level      TEXT NOT NULL CHECK (risk_level IN ('Low','Medium','High')),
    predicted_at    TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_marks_student ON marks(student_id);
CREATE INDEX IF NOT EXISTS idx_att_student ON attendance(student_id);
CREATE INDEX IF NOT EXISTS idx_pred_student ON predictions(student_id, predicted_at);
"""

TABLES = ["predictions", "attendance", "marks", "subjects", "students", "users"]


def get_db():
    if "db" not in g:
        path = current_app.config["DATABASE"]
        os.makedirs(os.path.dirname(path), exist_ok=True)
        g.db = sqlite3.connect(path)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(_exc=None):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


def init_db():
    get_db().executescript(SCHEMA)


def reset_db():
    conn = get_db()
    for table in TABLES:
        conn.execute(f"DROP TABLE IF EXISTS {table}")
    conn.commit()
    init_db()


def q(sql, args=(), one=False):
    cur = get_db().execute(sql, args)
    rows = cur.fetchall()
    cur.close()
    if one:
        return rows[0] if rows else None
    return rows


def run(sql, args=()):
    """Execute a write. Caller must call commit()."""
    cur = get_db().execute(sql, args)
    return cur.lastrowid


def commit():
    get_db().commit()
