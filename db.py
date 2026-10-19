import os

import mysql.connector
from dotenv import load_dotenv

load_dotenv()


def get_connection(use_database=True):
    config = {
        "host": os.getenv("DB_HOST", "localhost"),
        "user": os.getenv("DB_USER", "root"),
        "password": os.getenv("DB_PASSWORD", ""),
    }
    # first time the database doesn't exist yet, so connect without it
    if use_database:
        config["database"] = os.getenv("DB_NAME", "thdc_mentoring")
    return mysql.connector.connect(**config)


def query(sql, params=None, one=False):
    conn = get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(sql, params or ())
        rows = cur.fetchall()
        if one:
            return rows[0] if rows else None
        return rows
    finally:
        conn.close()


def execute(sql, params=None):
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(sql, params or ())
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()
