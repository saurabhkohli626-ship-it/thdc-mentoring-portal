import os

import mysql.connector
from dotenv import load_dotenv

# read .env from the project folder, even if the app is started from somewhere else.
# ENV_FILE can point to another file, e.g. the online database settings.
load_dotenv(os.getenv("ENV_FILE") or os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))


def get_connection(use_database=True):
    config = {
        "host": os.getenv("DB_HOST", "localhost"),
        "port": int(os.getenv("DB_PORT", "3306")),
        "user": os.getenv("DB_USER", "root"),
        "password": os.getenv("DB_PASSWORD", ""),
    }
    # online MySQL (Aiven) only accepts encrypted connections
    if os.getenv("DB_SSL") == "true":
        config["ssl_disabled"] = False
        ca_file = os.getenv("DB_SSL_CA")
        if ca_file:
            # check the server certificate with the CA file given by the host
            config["ssl_ca"] = os.path.join(os.path.dirname(os.path.abspath(__file__)), ca_file)
            config["ssl_verify_cert"] = True
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
