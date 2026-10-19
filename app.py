import json
import os
from functools import wraps

from dotenv import load_dotenv
from flask import Flask, render_template, request, redirect, url_for, session, flash, abort, jsonify
from werkzeug.security import check_password_hash

from db import query, execute

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY")
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_HTTPONLY"] = True

# after login each role goes to its own page
HOME_PAGE = {
    "student": "student_home",
    "faculty": "faculty_home",
    "director": "director_home",
}


def login_required(*roles):
    def decorator(view):
        @wraps(view)
        def wrapper(*args, **kwargs):
            if "user_id" not in session:
                return redirect(url_for("login"))
            if roles and session.get("role") not in roles:
                abort(403)
            return view(*args, **kwargs)
        return wrapper
    return decorator


@app.route("/")
def index():
    if "user_id" in session:
        return redirect(url_for(HOME_PAGE[session["role"]]))
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = query("SELECT * FROM users WHERE email = %s", (email,), one=True)

        if user and check_password_hash(user["password_hash"], password):
            session.clear()
            session["user_id"] = user["id"]
            session["name"] = user["name"]
            session["role"] = user["role"]
            return redirect(url_for(HOME_PAGE[user["role"]]))

        flash("Wrong email or password")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/student")
@login_required("student")
def student_home():
    student = query("""
        SELECT s.*, u.name, u.email, m.name AS mentor_name,
               f.status AS form_status, f.updated_at AS form_updated
        FROM students s
        JOIN users u ON u.id = s.user_id
        LEFT JOIN users m ON m.id = s.mentor_id
        LEFT JOIN mentoring_forms f ON f.student_id = s.id
        WHERE s.user_id = %s
    """, (session["user_id"],), one=True)
    remarks = get_remarks(student["id"])
    return render_template("student_home.html", student=student, remarks=remarks)


def get_remarks(student_id):
    return query("""
        SELECT r.remark, r.created_at, u.name AS faculty_name
        FROM mentor_remarks r
        JOIN users u ON u.id = r.faculty_id
        WHERE r.student_id = %s
        ORDER BY r.created_at DESC
    """, (student_id,))


def current_student():
    return query("""
        SELECT s.*, u.name, u.email
        FROM students s JOIN users u ON u.id = s.user_id
        WHERE s.user_id = %s
    """, (session["user_id"],), one=True)


def load_form(student_id):
    row = query("SELECT data FROM mentoring_forms WHERE student_id = %s", (student_id,), one=True)
    if not row:
        return None
    data = row["data"]
    if isinstance(data, (bytes, bytearray)):
        data = data.decode()
    return json.loads(data)


def to_number(value, kind=float):
    try:
        return kind(value)
    except (TypeError, ValueError):
        return None


@app.route("/student/form")
@login_required("student")
def student_form():
    student = current_student()
    saved = load_form(student["id"])
    if saved is None:
        # first time: fill what we already know about the student
        saved = {
            "name": student["name"],
            "email": student["email"],
            "roll": student["roll_no"] or "",
            "branch": student["branch"] or "",
            "class": student["class_name"] or "",
            "admyear": student["admitted_year"] or "",
        }
    return render_template("form.html", saved=saved, readonly=False,
                           back_url=url_for("student_home"))


@app.route("/student/form", methods=["POST"])
@login_required("student")
def save_form():
    student = current_student()
    body = request.get_json(silent=True) or {}
    data = body.get("data")
    if not isinstance(data, dict):
        return jsonify(error="no form data received"), 400

    old = query("SELECT status FROM mentoring_forms WHERE student_id = %s",
                (student["id"],), one=True)
    submitting = body.get("action") == "submit"
    if submitting or (old and old["status"] != "draft"):
        # once sent to the mentor, every change goes back to the mentor
        status = "submitted"
    else:
        status = "draft"

    execute("""
        INSERT INTO mentoring_forms (student_id, data, status, submitted_at)
        VALUES (%s, %s, %s, IF(%s, NOW(), NULL)) AS new
        ON DUPLICATE KEY UPDATE
            data = new.data,
            status = new.status,
            submitted_at = COALESCE(new.submitted_at, mentoring_forms.submitted_at)
    """, (student["id"], json.dumps(data), status, submitting))

    # copy a few fields to the students table for faculty / director reports
    cgpa = to_number(data.get("cgpa"))
    if cgpa is not None and not 0 <= cgpa <= 10:
        cgpa = None
    backlogs = 0
    if "Yes" in data.get("backlog", []):
        backlogs = to_number(data.get("backlogs_n"), int) or 0
    placement = (data.get("pstatus") or [None])[0]

    execute("""
        UPDATE students
        SET cgpa = %s, backlogs = %s, placement_status = %s,
            branch = COALESCE(NULLIF(%s, ''), branch),
            class_name = COALESCE(NULLIF(%s, ''), class_name)
        WHERE id = %s
    """, (cgpa, backlogs, placement, data.get("branch", ""), data.get("class", ""), student["id"]))

    return jsonify(status=status)


@app.route("/faculty")
@login_required("faculty")
def faculty_home():
    students = query("""
        SELECT s.id, s.roll_no, s.branch, s.cgpa, s.backlogs, u.name,
               COALESCE(f.status, 'not started') AS form_status
        FROM students s
        JOIN users u ON u.id = s.user_id
        LEFT JOIN mentoring_forms f ON f.student_id = s.id
        WHERE s.mentor_id = %s
        ORDER BY s.roll_no
    """, (session["user_id"],))
    return render_template("faculty_home.html", students=students)


def student_for_staff(student_id):
    """Load one student for faculty/director. A faculty member only gets their own mentees."""
    student = query("""
        SELECT s.*, u.name, u.email, m.name AS mentor_name,
               f.status AS form_status, f.submitted_at, f.updated_at AS form_updated
        FROM students s
        JOIN users u ON u.id = s.user_id
        LEFT JOIN users m ON m.id = s.mentor_id
        LEFT JOIN mentoring_forms f ON f.student_id = s.id
        WHERE s.id = %s
    """, (student_id,), one=True)
    if not student:
        abort(404)
    if session["role"] == "faculty" and student["mentor_id"] != session["user_id"]:
        abort(403)
    return student


@app.route("/students/<int:student_id>")
@login_required("faculty", "director")
def student_detail(student_id):
    student = student_for_staff(student_id)
    return render_template("student_detail.html", student=student,
                           remarks=get_remarks(student_id))


@app.route("/students/<int:student_id>/form")
@login_required("faculty", "director")
def view_form(student_id):
    student = student_for_staff(student_id)
    saved = load_form(student_id)
    if saved is None:
        flash("This student has not filled the form yet.")
        return redirect(url_for("student_detail", student_id=student_id))
    return render_template("form.html", saved=saved, readonly=True,
                           student_name=student["name"],
                           back_url=url_for("student_detail", student_id=student_id))


@app.route("/students/<int:student_id>/remarks", methods=["POST"])
@login_required("faculty")
def add_remark(student_id):
    student_for_staff(student_id)
    remark = request.form.get("remark", "").strip()
    if remark:
        execute("INSERT INTO mentor_remarks (student_id, faculty_id, remark) VALUES (%s, %s, %s)",
                (student_id, session["user_id"], remark))
        flash("Remark added.", "ok")
    return redirect(url_for("student_detail", student_id=student_id))


@app.route("/students/<int:student_id>/review", methods=["POST"])
@login_required("faculty")
def mark_reviewed(student_id):
    student_for_staff(student_id)
    # updated_at = updated_at keeps the student's "last saved" time unchanged
    execute("""
        UPDATE mentoring_forms SET status = 'reviewed', updated_at = updated_at
        WHERE student_id = %s AND status = 'submitted'
    """, (student_id,))
    flash("Form marked as reviewed.", "ok")
    return redirect(url_for("student_detail", student_id=student_id))


@app.route("/director")
@login_required("director")
def director_home():
    counts = query("SELECT role, COUNT(*) AS total FROM users GROUP BY role")
    faculty = query("""
        SELECT u.name, u.email, COUNT(s.id) AS mentees
        FROM users u
        LEFT JOIN students s ON s.mentor_id = u.id
        WHERE u.role = 'faculty'
        GROUP BY u.id, u.name, u.email
        ORDER BY u.name
    """)
    return render_template("director_home.html",
                           counts={row["role"]: row["total"] for row in counts},
                           faculty=faculty)


@app.errorhandler(403)
def forbidden(e):
    return render_template("error.html", title="Access denied",
                           message="You are not allowed to open this page."), 403


@app.errorhandler(404)
def not_found(e):
    return render_template("error.html", title="Not found",
                           message="This page does not exist."), 404


if __name__ == "__main__":
    app.run(debug=True)
