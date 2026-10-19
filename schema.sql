CREATE DATABASE IF NOT EXISTS thdc_mentoring;
USE thdc_mentoring;

-- login table for all three roles
CREATE TABLE IF NOT EXISTS users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(120) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    role ENUM('student', 'faculty', 'director') NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- cgpa, backlogs and placement_status are copied from the form
-- so that reports can be made with simple queries
CREATE TABLE IF NOT EXISTS students (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL UNIQUE,
    roll_no VARCHAR(30) UNIQUE,
    branch VARCHAR(60),
    class_name VARCHAR(40),
    admitted_year INT,
    mentor_id INT NULL,
    cgpa DECIMAL(4,2) NULL,
    backlogs INT DEFAULT 0,
    placement_status VARCHAR(40) NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (mentor_id) REFERENCES users(id) ON DELETE SET NULL
);

-- full mentoring form is stored as JSON
CREATE TABLE IF NOT EXISTS mentoring_forms (
    student_id INT PRIMARY KEY,
    data JSON NOT NULL,
    status ENUM('draft', 'submitted', 'reviewed') NOT NULL DEFAULT 'draft',
    submitted_at DATETIME NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS mentor_remarks (
    id INT AUTO_INCREMENT PRIMARY KEY,
    student_id INT NOT NULL,
    faculty_id INT NOT NULL,
    remark TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE,
    FOREIGN KEY (faculty_id) REFERENCES users(id) ON DELETE CASCADE
);
