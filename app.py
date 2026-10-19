import os
from functools import wraps

from dotenv import load_dotenv
from flask import Flask, render_template, request, redirect, url_for, session, flash, abort
from werkzeug.security import check_password_hash

from db import query

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY")

# after login each role goes to its own page
HOME_PAGE = {
    "student": "student_home",
    "faculty": "faculty_home",
    "director": "director_home",
}


def login_required(role=None):
    def decorator(view):
        @wraps(view)
        def wrapper(*args, **kwargs):
            if "user_id" not in session:
                return redirect(url_for("login"))
            if role and session.get("role") != role:
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
    return render_template("student_home.html", student=student)


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
    return render_template("error.html", message="You are not allowed to open this page."), 403


if __name__ == "__main__":
    app.run(debug=True)
