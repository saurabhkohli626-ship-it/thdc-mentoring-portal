# THDC-IHET Student Mentoring Portal

A web portal for the student mentoring process of THDC Institute of Hydropower Engineering & Technology, Tehri.

Earlier the mentoring form was a paper / single HTML page, so the data stayed with the student and the mentor or director had no way to see it together. In this project I built a backend for it using **Python (Flask)** and **MySQL**. There is one server and one database, and after login every user gets their own portal based on their role.

## Features

**Student**
- Fill the full mentoring form (15 sections: personal details, education, fees, scholarship, semester marks, placement, etc.)
- Save as draft section by section, then submit to the mentor
- See the form status and the remarks written by the mentor

**Faculty (mentor)**
- See only their own mentees with CGPA, backlogs and form status
- Open a student's form in read-only mode
- Write remarks after a meeting and mark the form as reviewed

**Director**
- Dashboard: total students, average CGPA, students with backlogs, form status counts
- Mentor workload (pending / reviewed / not submitted per mentor)
- Branch-wise report and placement status report
- Search and filter all students, download the list as CSV
- Add new student / faculty accounts and change a student's mentor

**Common**
- Login with hashed passwords (Werkzeug), change password
- Role based access control: every page checks the role, and a mentor can open only their own mentees (others get 403)

## Tech stack

| Part | Used |
|---|---|
| Backend | Python, Flask |
| Database | MySQL 8 (mysql-connector-python) |
| Frontend | HTML, CSS, JavaScript (Jinja templates) |
| Tools | Jupyter Notebook, Git, GitHub |

## Database

| Table | What it stores |
|---|---|
| `users` | name, email, password hash, role (student / faculty / director) |
| `students` | roll no., branch, class, mentor (`mentor_id` -> `users.id`), CGPA, backlogs, placement status |
| `mentoring_forms` | the full form as JSON, status (draft / submitted / reviewed), submitted time |
| `mentor_remarks` | remarks written by the mentor for a student |

The form has 15 sections and around 900 fields, so it is stored in one `JSON` column. Fields needed for reports (CGPA, backlogs, placement status) are also copied to the `students` table so that reports can be made with normal SQL (`GROUP BY`, `AVG`, `COUNT`).

Full schema: [`schema.sql`](schema.sql)

## Project structure

```
app.py               Flask routes (login, student, faculty, director)
db.py                MySQL connection helpers
schema.sql           tables
init_db.py           creates the tables and demo users
02_database.ipynb    same database setup, step by step in Jupyter
templates/           HTML pages
static/style.css     styling
```

## How to run it on your computer

1. Install Python 3 and MySQL 8.
2. Clone the repo and install the packages:
   ```
   git clone https://github.com/saurabhkohli626-ship-it/thdc-mentoring-portal.git
   cd thdc-mentoring-portal
   pip install -r requirements.txt
   ```
3. Copy `.env.example` to `.env` and put your MySQL password and a secret key in it.
4. Create the database, tables and demo users:
   ```
   python init_db.py
   ```
   (`02_database.ipynb` does the same step by step in Jupyter.)
5. Start the server:
   ```
   python app.py
   ```
6. Open http://127.0.0.1:5000 in the browser.

**Demo accounts** (password = `DEMO_PASSWORD` from your `.env`):
`director@thdc.test`, `faculty1@thdc.test`, `faculty2@thdc.test`, `student1@thdc.test`, `student2@thdc.test`, `student3@thdc.test`

## What I want to add next

- Encrypt sensitive fields like Aadhaar and bank account number
- CSRF tokens on all forms
- Email to the mentor when a student submits the form
- Forgot password with email reset
- Charts on the director dashboard

## Author

Saurabh Kohli - [GitHub](https://github.com/saurabhkohli626-ship-it)
