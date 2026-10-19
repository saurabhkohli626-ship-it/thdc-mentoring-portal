"""Create the tables and the demo users.

Run once after setting up .env:   python init_db.py
Safe to run again, it does not create duplicates.
"""
import os

import mysql.connector
from werkzeug.security import generate_password_hash

from db import get_connection, query, execute


def create_database():
    # works on your own computer; on hosting sites the database is made from their dashboard
    try:
        conn = get_connection(use_database=False)
        conn.cursor().execute("CREATE DATABASE IF NOT EXISTS `%s`" % os.getenv("DB_NAME"))
        conn.close()
    except mysql.connector.Error as e:
        print("skipped CREATE DATABASE:", e.msg)


def create_tables():
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "schema.sql"), encoding="utf-8") as f:
        sql = f.read()

    conn = get_connection()
    cur = conn.cursor()
    for statement in sql.split(";"):
        statement = statement.strip()
        if not statement or statement.upper().startswith(("CREATE DATABASE", "USE ")):
            continue
        cur.execute(statement)
    conn.commit()
    conn.close()
    print("tables ready")


def add_demo_users():
    password = os.getenv("DEMO_PASSWORD")
    if not password:
        print("DEMO_PASSWORD is not set in .env, skipping demo users")
        return
    demo_hash = generate_password_hash(password)

    people = [
        ("Director", "director@thdc.test", "director"),
        ("Dr. Amit Rawat", "faculty1@thdc.test", "faculty"),
        ("Dr. Neha Bisht", "faculty2@thdc.test", "faculty"),
        ("Rahul Negi", "student1@thdc.test", "student"),
        ("Priya Semwal", "student2@thdc.test", "student"),
        ("Ankit Panwar", "student3@thdc.test", "student"),
    ]
    for name, email, role in people:
        if not query("SELECT id FROM users WHERE email = %s", (email,), one=True):
            execute("INSERT INTO users (name, email, password_hash, role) VALUES (%s, %s, %s, %s)",
                    (name, email, demo_hash, role))

    def user_id(email):
        return query("SELECT id FROM users WHERE email = %s", (email,), one=True)["id"]

    f1, f2 = user_id("faculty1@thdc.test"), user_id("faculty2@thdc.test")
    students = [
        ("student1@thdc.test", "230101", "CSE", "B.Tech 3rd Year", 2023, f1),
        ("student2@thdc.test", "230102", "CSE", "B.Tech 3rd Year", 2023, f1),
        ("student3@thdc.test", "230201", "ECE", "B.Tech 3rd Year", 2023, f2),
    ]
    for email, roll, branch, cls, year, mentor in students:
        uid = user_id(email)
        if not query("SELECT id FROM students WHERE user_id = %s", (uid,), one=True):
            execute("INSERT INTO students (user_id, roll_no, branch, class_name, admitted_year, mentor_id) "
                    "VALUES (%s, %s, %s, %s, %s, %s)", (uid, roll, branch, cls, year, mentor))
    print("demo users ready")


if __name__ == "__main__":
    create_database()
    create_tables()
    add_demo_users()
