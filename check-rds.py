# filename: check-rds.py

import os
import sys

from dotenv import load_dotenv

load_dotenv()

ENGINE = os.getenv("RDS_ENGINE", "postgres").lower()
TABLES = ("clients", "projects", "consultants", "invoices")


def connect():
    settings = {
        "host": os.environ["RDS_HOST"],
        "port": int(os.getenv("RDS_PORT", "5432" if ENGINE == "postgres" else "3306")),
        "user": os.environ["RDS_USER"],
        "password": os.environ["RDS_PASSWORD"],
        "database": os.environ["RDS_DATABASE"],
        "connect_timeout": 10,
    }

    if ENGINE == "postgres":
        import psycopg2
        return psycopg2.connect(**settings)
    if ENGINE == "mysql":
        import pymysql
        return pymysql.connect(**settings)

    raise ValueError("RDS_ENGINE must be 'postgres' or 'mysql'")


def main():
    try:
        connection = connect()
        try:
            with connection.cursor() as cursor:
                failed = False
                for table in TABLES:
                    cursor.execute(f"SELECT COUNT(*) FROM {table}")
                    count = cursor.fetchone()[0]
                    status = "PASS" if count > 0 else "FAIL"
                    print(f"{table}: {count} rows — {status}")
                    failed |= count == 0
            return 1 if failed else 0
        finally:
            connection.close()
    except Exception as error:
        print(f"RDS check failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
