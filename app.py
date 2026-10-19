import csv
import io
import json
import os
from functools import wraps

from flask import (Flask, render_template, request, redirect, url_for, session, flash, abort,
                   jsonify, Response)
from werkzeug.security import check_password_hash, generate_password_hash

from db import query, execute  # db.py also loads the .env file

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY")
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_HTTPONLY"] = True
# Render sets RENDER=true and serves the site over https
if os.getenv("RENDER"):
    app.config["SESSION_COOKIE_SECURE"] = True

# after login each role goes to its own page
HOME_PAGE = {
    "student": "student_home",
    "faculty": "faculty_home",
    "director": "director_home",
}

# public demo: "Try as ..." buttons on the login page, no password needed
DEMO_MODE = os.getenv("DEMO_MODE") == "true"
DEMO_USERS = {
    "student": "student1@thdc.test",
    "faculty": "faculty1@thdc.test",
    "director": "director@thdc.test",
}


@app.context_processor
def inject_demo():
    return {"demo_mode": DEMO_MODE, "is_demo": session.get("demo", False)}


def block_in_demo():
    """Demo visitors can look around but cannot change accounts."""
    if session.get("demo"):
        flash("This is disabled in the demo.")
        return True
    return False


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
    if request.method == "GET" and "user_id" in session:
        return redirect(url_for(HOME_PAGE[session["role"]]))
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


@app.route("/demo/<role>")
def demo_login(role):
    if not DEMO_MODE or role not in DEMO_USERS:
        abort(404)
    user = query("SELECT * FROM users WHERE email = %s", (DEMO_USERS[role],), one=True)
    if not user:
        abort(404)
    session.clear()
    session["user_id"] = user["id"]
    session["name"] = user["name"]
    session["role"] = user["role"]
    session["demo"] = True
    return redirect(url_for(HOME_PAGE[user["role"]]))


@app.route("/account/password", methods=["GET", "POST"])
@login_required()
def change_password():
    if session.get("demo"):
        block_in_demo()
        return redirect(url_for("index"))
    if request.method == "POST":
        current = request.form.get("current", "")
        new = request.form.get("new", "")
        confirm = request.form.get("confirm", "")
        user = query("SELECT password_hash FROM users WHERE id = %s", (session["user_id"],), one=True)

        if not check_password_hash(user["password_hash"], current):
            flash("Current password is wrong.")
        elif len(new) < 8:
            flash("New password must be at least 8 characters.")
        elif new != confirm:
            flash("New password and confirm password do not match.")
        elif new == current:
            flash("New password must be different from the current one.")
        else:
            execute("UPDATE users SET password_hash = %s WHERE id = %s",
                    (generate_password_hash(new), session["user_id"]))
            flash("Password changed.", "ok")
            return redirect(url_for("index"))
    return render_template("change_password.html")


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
        VALUES (%s, %s, %s, IF(%s, NOW(), NULL))
        ON DUPLICATE KEY UPDATE
            data = VALUES(data),
            status = VALUES(status),
            submitted_at = COALESCE(VALUES(submitted_at), submitted_at)
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
    faculty = faculty_list() if session["role"] == "director" else []
    return render_template("student_detail.html", student=student,
                           remarks=get_remarks(student_id), faculty=faculty)


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
    summary = query("""
        SELECT COUNT(*) AS students,
               COALESCE(SUM(f.status IS NULL OR f.status = 'draft'), 0) AS not_submitted,
               COALESCE(SUM(f.status = 'submitted'), 0) AS pending_review,
               COALESCE(SUM(f.status = 'reviewed'), 0) AS reviewed,
               ROUND(AVG(s.cgpa), 2) AS avg_cgpa,
               COALESCE(SUM(s.backlogs > 0), 0) AS with_backlogs
        FROM students s
        LEFT JOIN mentoring_forms f ON f.student_id = s.id
    """, one=True)

    branches = query("""
        SELECT branch,
               COUNT(*) AS students,
               ROUND(AVG(cgpa), 2) AS avg_cgpa,
               SUM(backlogs > 0) AS with_backlogs,
               SUM(placement_status = 'Selected/Placed') AS placed
        FROM students
        GROUP BY branch
        ORDER BY branch
    """)

    placement = query("""
        SELECT COALESCE(placement_status, 'Not filled') AS placement, COUNT(*) AS students
        FROM students
        GROUP BY placement
        ORDER BY students DESC
    """)

    mentors = query("""
        SELECT u.id, u.name,
               COUNT(s.id) AS mentees,
               COALESCE(SUM(f.status = 'submitted'), 0) AS pending,
               COALESCE(SUM(f.status = 'reviewed'), 0) AS reviewed,
               COALESCE(SUM(s.id IS NOT NULL AND (f.status IS NULL OR f.status = 'draft')), 0) AS not_submitted
        FROM users u
        LEFT JOIN students s ON s.mentor_id = u.id
        LEFT JOIN mentoring_forms f ON f.student_id = s.id
        WHERE u.role = 'faculty'
        GROUP BY u.id, u.name
        ORDER BY pending DESC, u.name
    """)

    return render_template("director_home.html", summary=summary, branches=branches,
                           placement=placement, mentors=mentors)


def filtered_students(args):
    sql = """
        SELECT s.id, s.roll_no, u.name, u.email, s.branch, s.class_name, s.cgpa, s.backlogs,
               s.placement_status, m.name AS mentor_name,
               COALESCE(f.status, 'not started') AS form_status
        FROM students s
        JOIN users u ON u.id = s.user_id
        LEFT JOIN users m ON m.id = s.mentor_id
        LEFT JOIN mentoring_forms f ON f.student_id = s.id
        WHERE 1 = 1
    """
    params = []
    if args.get("q"):
        sql += " AND (u.name LIKE %s OR s.roll_no LIKE %s)"
        params += ["%" + args["q"].strip() + "%"] * 2
    if args.get("branch"):
        sql += " AND s.branch = %s"
        params.append(args["branch"])
    if args.get("status"):
        sql += " AND COALESCE(f.status, 'not started') = %s"
        params.append(args["status"])
    sql += " ORDER BY s.roll_no"
    return query(sql, params)


@app.route("/director/students")
@login_required("director")
def director_students():
    branches = [r["branch"] for r in query(
        "SELECT DISTINCT branch FROM students WHERE branch IS NOT NULL ORDER BY branch")]
    return render_template("director_students.html", students=filtered_students(request.args),
                           branches=branches, args=request.args)


@app.route("/director/students.csv")
@login_required("director")
def export_students():
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["Roll No", "Name", "Email", "Branch", "Class", "CGPA", "Backlogs",
                     "Placement", "Mentor", "Form status"])
    for s in filtered_students(request.args):
        writer.writerow([s["roll_no"], s["name"], s["email"], s["branch"], s["class_name"],
                         s["cgpa"], s["backlogs"], s["placement_status"], s["mentor_name"],
                         s["form_status"]])
    return Response(out.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=students.csv"})


def faculty_list():
    return query("SELECT id, name FROM users WHERE role = 'faculty' ORDER BY name")


@app.route("/director/users/new", methods=["GET", "POST"])
@login_required("director")
def add_user():
    form = request.form
    if request.method == "POST" and block_in_demo():
        return redirect(url_for("add_user"))
    if request.method == "POST":
        name = form.get("name", "").strip()
        email = form.get("email", "").strip().lower()
        role = form.get("role")
        password = form.get("password", "")
        roll_no = form.get("roll_no", "").strip()

        error = None
        if not name or not email or role not in ("student", "faculty"):
            error = "Name, email and role are required."
        elif len(password) < 8:
            error = "Password must be at least 8 characters."
        elif query("SELECT id FROM users WHERE email = %s", (email,), one=True):
            error = "A user with this email already exists."
        elif role == "student" and not roll_no:
            error = "Roll number is required for a student."
        elif role == "student" and query("SELECT id FROM students WHERE roll_no = %s", (roll_no,), one=True):
            error = "This roll number already exists."

        if error:
            flash(error)
        else:
            user_id = execute(
                "INSERT INTO users (name, email, password_hash, role) VALUES (%s, %s, %s, %s)",
                (name, email, generate_password_hash(password), role))
            if role == "student":
                execute("""
                    INSERT INTO students (user_id, roll_no, branch, class_name, admitted_year, mentor_id)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (user_id, roll_no, form.get("branch") or None, form.get("class_name") or None,
                      to_number(form.get("admitted_year"), int), to_number(form.get("mentor_id"), int)))
            flash(f"{role.title()} account created for {name}.", "ok")
            return redirect(url_for("add_user"))

    return render_template("add_user.html", faculty=faculty_list(), form=form)


@app.route("/students/<int:student_id>/mentor", methods=["POST"])
@login_required("director")
def change_mentor(student_id):
    student_for_staff(student_id)
    if block_in_demo():
        return redirect(url_for("student_detail", student_id=student_id))
    mentor_id = to_number(request.form.get("mentor_id"), int)
    if mentor_id and not query("SELECT id FROM users WHERE id = %s AND role = 'faculty'",
                               (mentor_id,), one=True):
        abort(400)
    execute("UPDATE students SET mentor_id = %s WHERE id = %s", (mentor_id, student_id))
    flash("Mentor updated.", "ok")
    return redirect(url_for("student_detail", student_id=student_id))


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
