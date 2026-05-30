import calendar
import csv
import html
import os
import re
import sqlite3
from contextlib import closing
from datetime import date, datetime, timedelta, timezone
from functools import wraps
from io import StringIO

from flask import (
    Flask,
    Response,
    flash,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename


BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DATABASE = os.getenv("DATABASE_PATH", os.path.join(BASE_DIR, "trunow.db"))
UPLOAD_ROOT = os.path.join(BASE_DIR, "static", "uploads")
PROFILE_UPLOAD = os.path.join(UPLOAD_ROOT, "profiles")
ATTENDANCE_UPLOAD = os.path.join(UPLOAD_ROOT, "attendance")
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}
IST = timezone(timedelta(hours=5, minutes=30), name="IST")
IFSC_REGEX = re.compile(r"^[A-Z]{4}0[A-Z0-9]{6}$")
BANK_NAME_REGEX = re.compile(r"^[A-Za-z][A-Za-z .&'()-]*$")
ATTENDANCE_STATUS_MAP = {
    "Present": "P",
    "Absent": "AB",
    "Leave": "L",
    "Sunday Work": "SUN-WORK",
    "Compensated Leave": "COMP",
}
MORNING_STATUS_OPTIONS = {"Present", "Absent", "Leave"}
NIGHT_STATUS_OPTIONS = {"Present", "Absent", "Not Applicable"}
APPROVAL_STATUS_OPTIONS = {"Pending", "Approved", "Rejected"}
LEAVE_TYPE_OPTIONS = {"Casual Leave", "Sick Leave", "Emergency Leave", "Other"}


app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "trunow-secret-key-change-me")
app.config["MAX_CONTENT_LENGTH"] = 4 * 1024 * 1024

EMPLOYEE_SEED_DATA = [
    {"employee_id": "EMP001", "full_name": "Selvam", "username": "selvam", "password": "Selvam@2026", "bank_account_no": "717388828", "ifsc_code": "IDIB000P076", "bank_name": "Indian Bank"},
    {"employee_id": "EMP002", "full_name": "Rajesh Sagar", "username": "rajesh.sagar", "password": "Rajesh@2026", "bank_account_no": "62105169140", "ifsc_code": "SBIN0008026", "bank_name": "SBI"},
    {"employee_id": "EMP003", "full_name": "Rajaram", "username": "rajaram", "password": "Rajaram@2026", "bank_account_no": "50100250797924", "ifsc_code": "HDFC0000024", "bank_name": "HDFC"},
    {"employee_id": "EMP004", "full_name": "Vikraman", "username": "vikraman", "password": "Vikraman@2026", "bank_account_no": "50100412610221", "ifsc_code": "HDFC0001854", "bank_name": "HDFC"},
    {"employee_id": "EMP005", "full_name": "Bikesh", "username": "bikesh", "password": "Bikesh@2026", "bank_account_no": "32338835940", "ifsc_code": "SBIN0012056", "bank_name": "SBI"},
    {"employee_id": "EMP006", "full_name": "Kavindra", "username": "kavindra", "password": "Kavindra@2026", "bank_account_no": "921010055859379", "ifsc_code": "UTIB0000110", "bank_name": "Axis Bank"},
    {"employee_id": "EMP007", "full_name": "Balasudhan", "username": "balasudhan", "password": "Bala@2026", "bank_account_no": "6923026029", "ifsc_code": "IDIB000K269", "bank_name": "Indian Bank"},
    {"employee_id": "EMP008", "full_name": "Rajasekar", "username": "rajasekar", "password": "Rajasekar@2026", "bank_account_no": "6733615792", "ifsc_code": "IDIB000K249", "bank_name": "Indian Bank"},
    {"employee_id": "EMP009", "full_name": "Vetrivel", "username": "vetrivel", "password": "Vetrivel@2026", "bank_account_no": "110045993544", "ifsc_code": "CNRB0001669", "bank_name": "Canara Bank"},
    {"employee_id": "EMP010", "full_name": "Jagdish", "username": "jagdish", "password": "Jagdish@2026", "bank_account_no": "643401050639", "ifsc_code": "ICIC0006434", "bank_name": "ICIC Bank"},
    {"employee_id": "EMP011", "full_name": "Mani Vannan", "username": "mani.vannan", "password": "Mani@2026", "bank_account_no": "00000035347537076", "ifsc_code": "SBIN0005582", "bank_name": "SBI Bank"},
    {"employee_id": "EMP012", "full_name": "Mohanraj", "username": "mohanraj", "password": "Mohanraj@2026", "bank_account_no": "50100762115634", "ifsc_code": "HDFC0000232", "bank_name": "HDFC Bank"},
    {"employee_id": "EMP013", "full_name": "Dinabaindhu Malik", "username": "dinabaindhu.malik", "password": "Dinabaindhu@2026", "bank_account_no": "35823747800", "ifsc_code": "SBIN0012054", "bank_name": "SBI Bank"},
    {"employee_id": "EMP014", "full_name": "Aasath", "username": "aasath", "password": "Aasath@2026", "bank_account_no": "7748149459", "ifsc_code": "KKBK0000431", "bank_name": "Kotak Mahindra"},
    {"employee_id": "EMP015", "full_name": "Pugazhenthi", "username": "pugazhenthi", "password": "Pugazhenthi@2026", "bank_account_no": "41853736374", "ifsc_code": "SBIN0017122", "bank_name": "SBI Bank"},
]


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(exception=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def query_db(query, args=(), one=False):
    cur = get_db().execute(query, args)
    rows = cur.fetchall()
    cur.close()
    return (rows[0] if rows else None) if one else rows


def execute_db(query, args=()):
    db = get_db()
    cur = db.execute(query, args)
    db.commit()
    return cur


def ist_now():
    return datetime.now(IST)


def ist_today():
    return ist_now().date()


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def ensure_directories():
    os.makedirs(PROFILE_UPLOAD, exist_ok=True)
    os.makedirs(ATTENDANCE_UPLOAD, exist_ok=True)


def ensure_employee_bank_columns(db):
    existing_columns = {
        row["name"] for row in db.execute("PRAGMA table_info(employees)").fetchall()
    }
    required_columns = {
        "bank_account_no": "TEXT",
        "ifsc_code": "TEXT",
        "bank_name": "TEXT",
    }
    for column_name, column_type in required_columns.items():
        if column_name not in existing_columns:
            db.execute(f"ALTER TABLE employees ADD COLUMN {column_name} {column_type}")


def get_employee_form_data(form, include_password=False):
    fields = {
        "employee_id": form.get("employee_id", "").strip(),
        "full_name": form.get("full_name", "").strip(),
        "username": form.get("username", "").strip(),
        "phone": form.get("phone", "").strip(),
        "email": form.get("email", "").strip(),
        "department": form.get("department", "").strip(),
        "designation": form.get("designation", "").strip(),
        "status": form.get("status", "Active").strip(),
        "bank_account_no": form.get("bank_account_no", "").strip(),
        "ifsc_code": form.get("ifsc_code", "").strip().upper(),
        "bank_name": form.get("bank_name", "").strip(),
        "monthly_salary": form.get("monthly_salary", "0").strip(),
        "night_shift_allowed": "1" if form.get("night_shift_allowed") == "1" else "0",
        "role": form.get("role", "").strip() or "Employee",
    }
    if include_password:
        fields["password"] = form.get("password", "").strip()
    return fields


def employee_required_fields_complete(fields, include_password=False):
    required_keys = [
        "employee_id",
        "full_name",
        "username",
        "phone",
        "email",
        "department",
        "designation",
        "monthly_salary",
        "role",
        "status",
    ]
    if include_password:
        required_keys.append("password")
    return all(fields.get(key) for key in required_keys)


def validate_employee_bank_fields(fields):
    if fields["bank_account_no"] and not fields["bank_account_no"].isdigit():
        return "Bank Account Number should contain numbers only."
    if fields["ifsc_code"] and not IFSC_REGEX.fullmatch(fields["ifsc_code"]):
        return "IFSC Code must be in the format HDFC0001234."
    if fields["bank_name"] and not BANK_NAME_REGEX.fullmatch(fields["bank_name"]):
        return "Bank Name should contain text only."
    try:
        if float(fields["monthly_salary"]) < 0:
            return "Monthly Salary should be zero or greater."
    except ValueError:
        return "Monthly Salary should be a valid number."
    return None


def ensure_employee_attendance_columns(db):
    existing_columns = {
        row["name"] for row in db.execute("PRAGMA table_info(employees)").fetchall()
    }
    required_columns = {
        "monthly_salary": "REAL NOT NULL DEFAULT 0",
        "night_shift_allowed": "INTEGER NOT NULL DEFAULT 0",
        "role": "TEXT",
    }
    for column_name, column_type in required_columns.items():
        if column_name not in existing_columns:
            db.execute(f"ALTER TABLE employees ADD COLUMN {column_name} {column_type}")


def ensure_attendance_columns(db):
    existing_columns = {
        row["name"] for row in db.execute("PRAGMA table_info(attendance)").fetchall()
    }
    required_columns = {
        "day_name": "TEXT",
        "morning_status": "TEXT NOT NULL DEFAULT 'Present'",
        "night_status": "TEXT NOT NULL DEFAULT 'Not Applicable'",
        "night_check_in_time": "TEXT",
        "night_check_out_time": "TEXT",
        "remarks": "TEXT",
        "approval_status": "TEXT NOT NULL DEFAULT 'Pending'",
        "admin_approval_status": "TEXT NOT NULL DEFAULT 'Pending'",
        "is_sunday_work": "INTEGER NOT NULL DEFAULT 0",
        "is_compensated_leave": "INTEGER NOT NULL DEFAULT 0",
        "salary_cut_status": "INTEGER NOT NULL DEFAULT 0",
    }
    for column_name, column_type in required_columns.items():
        if column_name not in existing_columns:
            db.execute(f"ALTER TABLE attendance ADD COLUMN {column_name} {column_type}")



def migrate_attendance_data(db):
    db.execute(
        """
        UPDATE attendance
        SET day_name = COALESCE(day_name, CASE
            WHEN date IS NOT NULL AND date != '' THEN
                CASE strftime('%w', date)
                    WHEN '0' THEN 'Sunday'
                    WHEN '1' THEN 'Monday'
                    WHEN '2' THEN 'Tuesday'
                    WHEN '3' THEN 'Wednesday'
                    WHEN '4' THEN 'Thursday'
                    WHEN '5' THEN 'Friday'
                    WHEN '6' THEN 'Saturday'
                END
            ELSE day_name
        END)
        """
    )
    db.execute("UPDATE attendance SET morning_status = COALESCE(morning_status, status, 'Present')")
    db.execute("UPDATE attendance SET night_status = COALESCE(night_status, 'Not Applicable')")
    db.execute("UPDATE attendance SET approval_status = COALESCE(approval_status, 'Approved')")
    db.execute("UPDATE attendance SET admin_approval_status = COALESCE(admin_approval_status, approval_status, 'Approved')")
    db.execute(
        """
        UPDATE attendance
        SET is_sunday_work = CASE
            WHEN COALESCE(day_name, '') != 'Sunday' THEN 0
            WHEN COALESCE(is_sunday_work, 0) = 1 THEN 1
            WHEN COALESCE(day_name, '') = 'Sunday' AND COALESCE(morning_status, status, 'Absent') = 'Present' THEN 1
            ELSE 0
        END
        """
    )


def ensure_leave_and_salary_tables(db):
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS leave_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_id INTEGER NOT NULL,
            leave_date TEXT NOT NULL,
            reason TEXT NOT NULL,
            leave_type TEXT NOT NULL,
            remarks TEXT,
            status TEXT NOT NULL DEFAULT 'Pending',
            admin_remarks TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (employee_id) REFERENCES employees (id)
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS monthly_salary_report (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_id INTEGER NOT NULL,
            month INTEGER NOT NULL,
            year INTEGER NOT NULL,
            total_working_days INTEGER NOT NULL,
            present_days INTEGER NOT NULL,
            absent_days INTEGER NOT NULL,
            leave_days INTEGER NOT NULL,
            sunday_work_count INTEGER NOT NULL,
            compensated_leave_count INTEGER NOT NULL,
            salary_cut_days INTEGER NOT NULL,
            per_day_salary REAL NOT NULL,
            salary_cut_amount REAL NOT NULL,
            final_salary REAL NOT NULL,
            generated_at TEXT NOT NULL,
            UNIQUE(employee_id, month, year),
            FOREIGN KEY (employee_id) REFERENCES employees (id)
        )
        """
    )


def get_day_name(value):
    return datetime.strptime(value, "%Y-%m-%d").strftime("%A")


def is_sunday(value):
    return get_day_name(value) == "Sunday"


def calculate_total_working_days(month, year):
    return sum(
        1
        for day in range(1, calendar.monthrange(year, month)[1] + 1)
        if date(year, month, day).weekday() != 6
    )


def iter_months_between(start_date, end_date):
    start_obj = datetime.strptime(start_date, "%Y-%m-%d").date().replace(day=1)
    end_obj = datetime.strptime(end_date, "%Y-%m-%d").date().replace(day=1)
    if end_obj < start_obj:
        start_obj, end_obj = end_obj, start_obj
    current = start_obj
    while current <= end_obj:
        yield current.month, current.year
        if current.month == 12:
            current = current.replace(year=current.year + 1, month=1)
        else:
            current = current.replace(month=current.month + 1)


def calculate_working_days_between(start_date, end_date):
    start_obj = datetime.strptime(start_date, "%Y-%m-%d").date()
    end_obj = datetime.strptime(end_date, "%Y-%m-%d").date()
    if end_obj < start_obj:
        start_obj, end_obj = end_obj, start_obj
    total = 0
    current = start_obj
    while current <= end_obj:
        if current.weekday() != 6:
            total += 1
        current += timedelta(days=1)
    return total


def normalize_date_range(start_date, end_date):
    start_obj = datetime.strptime(start_date, "%Y-%m-%d").date()
    end_obj = datetime.strptime(end_date, "%Y-%m-%d").date()
    if end_obj < start_obj:
        start_obj, end_obj = end_obj, start_obj
    return start_obj.isoformat(), end_obj.isoformat()


def get_attendance_status_label(row):
    morning_status = row["morning_status"] or row["status"] or "Absent"
    if row["is_compensated_leave"]:
        return "Compensated Leave"
    if row["is_sunday_work"]:
        return "Sunday Work"
    if morning_status == "Leave":
        return "Leave"
    if morning_status == "Present":
        return "Present"
    return "Absent"


def get_attendance_status_code(row):
    return ATTENDANCE_STATUS_MAP[get_attendance_status_label(row)]


def get_attendance_badge_class(status_label):
    return {
        "Present": "badge-present",
        "Absent": "badge-absent",
        "Leave": "badge-pending",
        "Sunday Work": "badge-progress",
        "Compensated Leave": "badge-comp",
    }.get(status_label, "badge-present")


def parse_month_year(month_value, year_value):
    today = ist_today()
    try:
        month = int(month_value) if month_value else today.month
        year = int(year_value) if year_value else today.year
    except ValueError:
        return today.month, today.year
    month = min(12, max(1, month))
    return month, year


def calculate_employee_monthly_attendance(employee_id, month, year):
    start_date = date(year, month, 1).isoformat()
    end_date = date(year, month, calendar.monthrange(year, month)[1]).isoformat()
    rows = query_db(
        """
        SELECT *
        FROM attendance
        WHERE employee_id = ? AND date BETWEEN ? AND ?
        ORDER BY date
        """,
        (employee_id, start_date, end_date),
    )
    day_map = {row["date"]: row for row in rows}
    totals = {
        "records": rows,
        "day_map": day_map,
        "present_days": 0,
        "absent_days": 0,
        "leave_days": 0,
        "sunday_work_count": 0,
        "night_shift_count": 0,
    }
    for row in rows:
        if row["night_status"] == "Present":
            totals["night_shift_count"] += 1
        if row["is_sunday_work"]:
            totals["sunday_work_count"] += 1
        elif row["morning_status"] == "Present":
            totals["present_days"] += 1
        elif row["morning_status"] == "Leave" and not is_sunday(row["date"]):
            totals["leave_days"] += 1
        elif row["morning_status"] == "Absent" and not is_sunday(row["date"]):
            totals["absent_days"] += 1

    month_days = calendar.monthrange(year, month)[1]
    for day in range(1, month_days + 1):
        current_date = date(year, month, day).isoformat()
        if current_date in day_map or is_sunday(current_date):
            continue
        totals["absent_days"] += 1
    totals["total_working_days"] = calculate_total_working_days(month, year)
    return totals


def apply_monthly_compensation_flags(employee_id, month, year):
    start_date = date(year, month, 1).isoformat()
    end_date = date(year, month, calendar.monthrange(year, month)[1]).isoformat()
    leave_rows = query_db(
        """
        SELECT id
        FROM attendance
        WHERE employee_id = ? AND date BETWEEN ? AND ? AND morning_status = 'Leave' AND approval_status = 'Approved' AND day_name != 'Sunday'
        ORDER BY date ASC
        """,
        (employee_id, start_date, end_date),
    )
    sunday_work_count = query_db(
        """
        SELECT COUNT(*) AS count
        FROM attendance
        WHERE employee_id = ? AND date BETWEEN ? AND ? AND is_sunday_work = 1 AND approval_status = 'Approved'
        """,
        (employee_id, start_date, end_date),
        one=True,
    )["count"]
    if leave_rows:
        execute_db(
            """
            UPDATE attendance
            SET is_compensated_leave = 0, salary_cut_status = 0
            WHERE employee_id = ? AND date BETWEEN ? AND ? AND morning_status = 'Leave' AND day_name != 'Sunday'
            """,
            (employee_id, start_date, end_date),
        )
    extra_leaves = leave_rows[1:]
    compensated_ids = {row["id"] for row in extra_leaves[:sunday_work_count]}
    salary_cut_ids = {row["id"] for row in extra_leaves[sunday_work_count:]}
    for attendance_id in compensated_ids:
        execute_db(
            "UPDATE attendance SET is_compensated_leave = 1, salary_cut_status = 0 WHERE id = ?",
            (attendance_id,),
        )
    for attendance_id in salary_cut_ids:
        execute_db(
            "UPDATE attendance SET is_compensated_leave = 0, salary_cut_status = 1 WHERE id = ?",
            (attendance_id,),
        )


def calculate_leave_and_salary_cut(employee_id, month, year):
    apply_monthly_compensation_flags(employee_id, month, year)
    summary = calculate_employee_monthly_attendance(employee_id, month, year)
    allowed_leave = 1
    total_leaves_taken = summary["leave_days"]
    sunday_work_count = summary["sunday_work_count"]
    extra_leave = max(0, total_leaves_taken - allowed_leave)
    compensated_leave = min(extra_leave, sunday_work_count)
    salary_cut_days = extra_leave - compensated_leave
    employee = query_db("SELECT monthly_salary FROM employees WHERE id = ?", (employee_id,), one=True)
    monthly_salary = float(employee["monthly_salary"] or 0) if employee else 0.0
    total_working_days = max(1, summary["total_working_days"])
    per_day_salary = monthly_salary / total_working_days
    salary_cut_amount = round(salary_cut_days * per_day_salary, 2)
    final_salary = round(monthly_salary - salary_cut_amount, 2)
    return {
        **summary,
        "allowed_leave": allowed_leave,
        "total_leaves_taken": total_leaves_taken,
        "extra_leave": extra_leave,
        "compensated_leave_count": compensated_leave,
        "salary_cut_days": salary_cut_days,
        "per_day_salary": round(per_day_salary, 2),
        "salary_cut_amount": salary_cut_amount,
        "final_salary": final_salary,
        "monthly_salary": monthly_salary,
    }


def calculate_employee_attendance_range(employee_id, start_date, end_date):
    start_date, end_date = normalize_date_range(start_date, end_date)
    start_obj = datetime.strptime(start_date, "%Y-%m-%d").date()
    end_obj = datetime.strptime(end_date, "%Y-%m-%d").date()
    rows = query_db(
        """
        SELECT *
        FROM attendance
        WHERE employee_id = ? AND date BETWEEN ? AND ?
        ORDER BY date
        """,
        (employee_id, start_obj.isoformat(), end_obj.isoformat()),
    )
    day_map = {row["date"]: row for row in rows}
    totals = {
        "records": rows,
        "day_map": day_map,
        "present_days": 0,
        "absent_days": 0,
        "leave_days": 0,
        "sunday_work_count": 0,
        "night_shift_count": 0,
    }
    for row in rows:
        if row["night_status"] == "Present":
            totals["night_shift_count"] += 1
        if row["is_sunday_work"]:
            totals["sunday_work_count"] += 1
        elif row["morning_status"] == "Present":
            totals["present_days"] += 1
        elif row["morning_status"] == "Leave" and not is_sunday(row["date"]):
            totals["leave_days"] += 1
        elif row["morning_status"] == "Absent" and not is_sunday(row["date"]):
            totals["absent_days"] += 1

    current = start_obj
    while current <= end_obj:
        current_date = current.isoformat()
        if current_date not in day_map and current.weekday() != 6:
            totals["absent_days"] += 1
        current += timedelta(days=1)
    totals["total_working_days"] = calculate_working_days_between(start_obj.isoformat(), end_obj.isoformat())
    return totals


def refresh_compensation_flags_for_range(employee_id, start_date, end_date):
    for month, year in iter_months_between(start_date, end_date):
        apply_monthly_compensation_flags(employee_id, month, year)


def calculate_leave_and_salary_cut_range(employee_id, start_date, end_date):
    start_date, end_date = normalize_date_range(start_date, end_date)
    refresh_compensation_flags_for_range(employee_id, start_date, end_date)
    summary = calculate_employee_attendance_range(employee_id, start_date, end_date)
    allowed_leave = 0
    compensated_leave = 0
    salary_cut_days = 0
    total_leaves_taken = summary["leave_days"]
    for month, year in iter_months_between(start_date, end_date):
        month_start = max(start_date, date(year, month, 1).isoformat())
        month_end = min(end_date, date(year, month, calendar.monthrange(year, month)[1]).isoformat())
        month_summary = calculate_employee_attendance_range(employee_id, month_start, month_end)
        month_allowed_leave = 1
        month_extra_leave = max(0, month_summary["leave_days"] - month_allowed_leave)
        month_compensated = min(month_extra_leave, month_summary["sunday_work_count"])
        allowed_leave += month_allowed_leave
        compensated_leave += month_compensated
        salary_cut_days += month_extra_leave - month_compensated
    sunday_work_count = summary["sunday_work_count"]
    employee = query_db("SELECT monthly_salary FROM employees WHERE id = ?", (employee_id,), one=True)
    monthly_salary = float(employee["monthly_salary"] or 0) if employee else 0.0
    total_working_days = max(1, summary["total_working_days"])
    per_day_salary = monthly_salary / total_working_days
    salary_cut_amount = round(salary_cut_days * per_day_salary, 2)
    final_salary = round(monthly_salary - salary_cut_amount, 2)
    return {
        **summary,
        "allowed_leave": allowed_leave,
        "total_leaves_taken": total_leaves_taken,
        "extra_leave": extra_leave,
        "compensated_leave_count": compensated_leave,
        "salary_cut_days": salary_cut_days,
        "per_day_salary": round(per_day_salary, 2),
        "salary_cut_amount": salary_cut_amount,
        "final_salary": final_salary,
        "monthly_salary": monthly_salary,
    }


def get_employee_compensation_balance(employee_id, month, year):
    salary_info = calculate_leave_and_salary_cut(employee_id, month, year)
    return salary_info["sunday_work_count"] - salary_info["compensated_leave_count"]


def upsert_monthly_salary_report(employee_id, month, year, report_data):
    execute_db(
        """
        INSERT INTO monthly_salary_report
        (
            employee_id, month, year, total_working_days, present_days, absent_days,
            leave_days, sunday_work_count, compensated_leave_count, salary_cut_days,
            per_day_salary, salary_cut_amount, final_salary, generated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(employee_id, month, year) DO UPDATE SET
            total_working_days = excluded.total_working_days,
            present_days = excluded.present_days,
            absent_days = excluded.absent_days,
            leave_days = excluded.leave_days,
            sunday_work_count = excluded.sunday_work_count,
            compensated_leave_count = excluded.compensated_leave_count,
            salary_cut_days = excluded.salary_cut_days,
            per_day_salary = excluded.per_day_salary,
            salary_cut_amount = excluded.salary_cut_amount,
            final_salary = excluded.final_salary,
            generated_at = excluded.generated_at
        """,
        (
            employee_id,
            month,
            year,
            report_data["total_working_days"],
            report_data["present_days"],
            report_data["absent_days"],
            report_data["leave_days"],
            report_data["sunday_work_count"],
            report_data["compensated_leave_count"],
            report_data["salary_cut_days"],
            report_data["per_day_salary"],
            report_data["salary_cut_amount"],
            report_data["final_salary"],
            ist_now().strftime("%Y-%m-%d %H:%M:%S"),
        ),
    )


def monthly_export_rows(month, year):
    employees = query_db(
        """
        SELECT id, employee_id, full_name, department, bank_account_no, ifsc_code, bank_name, monthly_salary
        FROM employees
        WHERE status = 'Active'
        ORDER BY full_name
        """
    )
    total_days = calendar.monthrange(year, month)[1]
    rows = []
    for employee in employees:
        salary_info = calculate_leave_and_salary_cut(employee["id"], month, year)
        row = {
            "employee_id": employee["employee_id"],
            "employee_name": employee["full_name"],
            "department": employee["department"],
            "bank_account_no": employee["bank_account_no"] or "",
            "ifsc_code": employee["ifsc_code"] or "",
            "bank_name": employee["bank_name"] or "",
            "monthly_salary": employee["monthly_salary"] or 0,
            "present_days": salary_info["present_days"],
            "absent_days": salary_info["absent_days"],
            "leave_days": salary_info["leave_days"],
            "sunday_work_count": salary_info["sunday_work_count"],
            "compensated_leave_count": salary_info["compensated_leave_count"],
            "salary_cut_days": salary_info["salary_cut_days"],
            "salary_cut_amount": salary_info["salary_cut_amount"],
            "final_salary": salary_info["final_salary"],
            "night_shift_count": salary_info["night_shift_count"],
            "days": [],
        }
        for day in range(1, total_days + 1):
            current_date = date(year, month, day).isoformat()
            attendance_row = salary_info["day_map"].get(current_date)
            if attendance_row:
                row["days"].append(get_attendance_status_code(attendance_row))
            else:
                row["days"].append("" if is_sunday(current_date) else "AB")
        rows.append(row)
    return rows


def build_summary_rows_from_monthly(rows, period_label):
    headers = [
        "Employee ID",
        "Employee Name",
        "Department",
        "Period",
        "Present",
        "Absent",
        "Leave",
        "Sunday Work",
        "Comp Leave",
        "Salary Cut Days",
        "Salary Cut Amount",
        "Final Salary",
        "Night Shift Count",
    ]
    summary_rows = []
    for row in rows:
        summary_rows.append(
            [
                row["employee_id"],
                row["employee_name"],
                row["department"],
                period_label,
                row["present_days"],
                row["absent_days"],
                row["leave_days"],
                row["sunday_work_count"],
                row["compensated_leave_count"],
                row["salary_cut_days"],
                row["salary_cut_amount"],
                row["final_salary"],
                row["night_shift_count"],
            ]
        )
    return headers, summary_rows


def build_excel_sheet(sheet_name, title, subtitle, headers, rows, day_columns=None, day_labels=None):
    day_columns = day_columns or []
    day_labels = day_labels or []
    total_columns = len(headers)
    day_column_set = set(day_columns)
    xml = StringIO()
    xml.write(f'<Worksheet ss:Name="{html.escape(sheet_name)}"><Table>')
    for index, header in enumerate(headers):
        width = 80
        if index == 0:
            width = 90
        elif index == 1:
            width = 160
        elif index in {2, 5}:
            width = 110
        elif index in {3, 4}:
            width = 105
        elif index in day_column_set:
            width = 52
        elif "Salary" in header or "Final" in header:
            width = 95
        elif "Night" in header:
            width = 85
        xml.write(f'<Column ss:AutoFitWidth="0" ss:Width="{width}"/>')
    xml.write(f'<Row ss:Height="26"><Cell ss:MergeAcross="{total_columns - 1}" ss:StyleID="title"><Data ss:Type="String">{html.escape(title)}</Data></Cell></Row>')
    xml.write(f'<Row ss:Height="20"><Cell ss:MergeAcross="{total_columns - 1}" ss:StyleID="subtitle"><Data ss:Type="String">{html.escape(subtitle)}</Data></Cell></Row>')
    xml.write('<Row ss:Height="8"></Row>')
    xml.write('<Row ss:Height="24">')
    for index, header in enumerate(headers):
        style = "headerDay" if index in day_column_set else "header"
        if index in day_column_set and day_labels:
            day_label = day_labels[index - min(day_column_set)]
            if day_label == "Sun":
                style = "headerSunday"
        xml.write(f'<Cell ss:StyleID="{style}"><Data ss:Type="String">{html.escape(header)}</Data></Cell>')
    xml.write('</Row>')
    if day_labels:
        xml.write('<Row ss:Height="20">')
        first_day_column = min(day_column_set) if day_column_set else None
        for index in range(total_columns):
            if index in day_column_set and first_day_column is not None:
                day_label = day_labels[index - first_day_column]
                style = "headerSunday" if day_label == "Sun" else "headerDay"
                xml.write(f'<Cell ss:StyleID="{style}"><Data ss:Type="String">{html.escape(day_label)}</Data></Cell>')
            else:
                xml.write('<Cell ss:StyleID="header"><Data ss:Type="String"></Data></Cell>')
        xml.write('</Row>')
    for row in rows:
        xml.write('<Row ss:Height="22">')
        for index, value in enumerate(row):
            style = "cell"
            if index in day_column_set:
                style = {
                    "P": "statusP",
                    "AB": "statusAB",
                    "L": "statusL",
                    "SUN-WORK": "statusSUN",
                    "COMP": "statusCOMP",
                }.get(str(value), "cellCenter")
            elif isinstance(value, (int, float)):
                style = "money" if index >= total_columns - 4 else "cellCenter"
            elif index in {0, 3, 4}:
                style = "cellCenter"
            data_type = "Number" if isinstance(value, (int, float)) else "String"
            xml.write(
                f'<Cell ss:StyleID="{style}"><Data ss:Type="{data_type}">{html.escape(str(value))}</Data></Cell>'
            )
        xml.write('</Row>')
    freeze_row = 5 if day_labels else 4
    xml.write(
        f"""
        </Table>
        <WorksheetOptions xmlns="urn:schemas-microsoft-com:office:excel">
            <FreezePanes/>
            <FrozenNoSplit/>
            <SplitHorizontal>{freeze_row}</SplitHorizontal>
            <TopRowBottomPane>{freeze_row}</TopRowBottomPane>
            <ActivePane>2</ActivePane>
            <Panes>
                <Pane>
                    <Number>3</Number>
                </Pane>
            </Panes>
            <ProtectObjects>False</ProtectObjects>
            <ProtectScenarios>False</ProtectScenarios>
        </WorksheetOptions>
        """
    )
    xml.write('</Worksheet>')
    return xml.getvalue()


def build_excel_workbook(sheets):
    xml = StringIO()
    xml.write('<?xml version="1.0"?>')
    xml.write('<?mso-application progid="Excel.Sheet"?>')
    xml.write(
        '<Workbook xmlns="urn:schemas-microsoft-com:office:spreadsheet" '
        'xmlns:o="urn:schemas-microsoft-com:office:office" '
        'xmlns:x="urn:schemas-microsoft-com:office:excel" '
        'xmlns:ss="urn:schemas-microsoft-com:office:spreadsheet" '
        'xmlns:html="http://www.w3.org/TR/REC-html40">'
    )
    xml.write(
        """
        <Styles>
            <Style ss:ID="Default" ss:Name="Normal">
                <Alignment ss:Vertical="Center"/>
                <Borders/>
                <Font ss:FontName="Calibri" ss:Size="11" ss:Color="#172238"/>
                <Interior/>
                <NumberFormat/>
                <Protection/>
            </Style>
            <Style ss:ID="title">
                <Alignment ss:Horizontal="Center" ss:Vertical="Center"/>
                <Font ss:FontName="Calibri" ss:Bold="1" ss:Size="16" ss:Color="#0D1B4C"/>
            </Style>
            <Style ss:ID="subtitle">
                <Alignment ss:Horizontal="Center" ss:Vertical="Center"/>
                <Font ss:FontName="Calibri" ss:Size="10" ss:Color="#5D6B85"/>
            </Style>
            <Style ss:ID="header">
                <Alignment ss:Horizontal="Center" ss:Vertical="Center" ss:WrapText="1"/>
                <Borders>
                    <Border ss:Position="Bottom" ss:LineStyle="Continuous" ss:Weight="1" ss:Color="#D9E0EB"/>
                    <Border ss:Position="Left" ss:LineStyle="Continuous" ss:Weight="1" ss:Color="#D9E0EB"/>
                    <Border ss:Position="Right" ss:LineStyle="Continuous" ss:Weight="1" ss:Color="#D9E0EB"/>
                    <Border ss:Position="Top" ss:LineStyle="Continuous" ss:Weight="1" ss:Color="#D9E0EB"/>
                </Borders>
                <Font ss:FontName="Calibri" ss:Bold="1" ss:Size="11" ss:Color="#FFFFFF"/>
                <Interior ss:Color="#0D1B4C" ss:Pattern="Solid"/>
            </Style>
            <Style ss:ID="headerDay">
                <Alignment ss:Horizontal="Center" ss:Vertical="Center" ss:WrapText="1"/>
                <Borders>
                    <Border ss:Position="Bottom" ss:LineStyle="Continuous" ss:Weight="1" ss:Color="#D9E0EB"/>
                    <Border ss:Position="Left" ss:LineStyle="Continuous" ss:Weight="1" ss:Color="#D9E0EB"/>
                    <Border ss:Position="Right" ss:LineStyle="Continuous" ss:Weight="1" ss:Color="#D9E0EB"/>
                    <Border ss:Position="Top" ss:LineStyle="Continuous" ss:Weight="1" ss:Color="#D9E0EB"/>
                </Borders>
                <Font ss:FontName="Calibri" ss:Bold="1" ss:Size="10" ss:Color="#0D1B4C"/>
                <Interior ss:Color="#EAF2FF" ss:Pattern="Solid"/>
            </Style>
            <Style ss:ID="headerSunday">
                <Alignment ss:Horizontal="Center" ss:Vertical="Center" ss:WrapText="1"/>
                <Borders>
                    <Border ss:Position="Bottom" ss:LineStyle="Continuous" ss:Weight="1" ss:Color="#D9E0EB"/>
                    <Border ss:Position="Left" ss:LineStyle="Continuous" ss:Weight="1" ss:Color="#D9E0EB"/>
                    <Border ss:Position="Right" ss:LineStyle="Continuous" ss:Weight="1" ss:Color="#D9E0EB"/>
                    <Border ss:Position="Top" ss:LineStyle="Continuous" ss:Weight="1" ss:Color="#D9E0EB"/>
                </Borders>
                <Font ss:FontName="Calibri" ss:Bold="1" ss:Size="10" ss:Color="#7C3AED"/>
                <Interior ss:Color="#F1E8FF" ss:Pattern="Solid"/>
            </Style>
            <Style ss:ID="cell">
                <Alignment ss:Vertical="Center" ss:WrapText="1"/>
                <Borders>
                    <Border ss:Position="Bottom" ss:LineStyle="Continuous" ss:Weight="1" ss:Color="#E5EAF2"/>
                    <Border ss:Position="Left" ss:LineStyle="Continuous" ss:Weight="1" ss:Color="#E5EAF2"/>
                    <Border ss:Position="Right" ss:LineStyle="Continuous" ss:Weight="1" ss:Color="#E5EAF2"/>
                    <Border ss:Position="Top" ss:LineStyle="Continuous" ss:Weight="1" ss:Color="#E5EAF2"/>
                </Borders>
            </Style>
            <Style ss:ID="cellCenter">
                <Alignment ss:Horizontal="Center" ss:Vertical="Center"/>
                <Borders>
                    <Border ss:Position="Bottom" ss:LineStyle="Continuous" ss:Weight="1" ss:Color="#E5EAF2"/>
                    <Border ss:Position="Left" ss:LineStyle="Continuous" ss:Weight="1" ss:Color="#E5EAF2"/>
                    <Border ss:Position="Right" ss:LineStyle="Continuous" ss:Weight="1" ss:Color="#E5EAF2"/>
                    <Border ss:Position="Top" ss:LineStyle="Continuous" ss:Weight="1" ss:Color="#E5EAF2"/>
                </Borders>
            </Style>
            <Style ss:ID="money">
                <Alignment ss:Horizontal="Right" ss:Vertical="Center"/>
                <Borders>
                    <Border ss:Position="Bottom" ss:LineStyle="Continuous" ss:Weight="1" ss:Color="#E5EAF2"/>
                    <Border ss:Position="Left" ss:LineStyle="Continuous" ss:Weight="1" ss:Color="#E5EAF2"/>
                    <Border ss:Position="Right" ss:LineStyle="Continuous" ss:Weight="1" ss:Color="#E5EAF2"/>
                    <Border ss:Position="Top" ss:LineStyle="Continuous" ss:Weight="1" ss:Color="#E5EAF2"/>
                </Borders>
                <NumberFormat ss:Format="Standard"/>
            </Style>
            <Style ss:ID="statusP"><Alignment ss:Horizontal="Center" ss:Vertical="Center"/><Font ss:Bold="1" ss:Color="#0D7C59"/><Interior ss:Color="#DDF5EC" ss:Pattern="Solid"/><Borders><Border ss:Position="Bottom" ss:LineStyle="Continuous" ss:Weight="1" ss:Color="#E5EAF2"/><Border ss:Position="Left" ss:LineStyle="Continuous" ss:Weight="1" ss:Color="#E5EAF2"/><Border ss:Position="Right" ss:LineStyle="Continuous" ss:Weight="1" ss:Color="#E5EAF2"/><Border ss:Position="Top" ss:LineStyle="Continuous" ss:Weight="1" ss:Color="#E5EAF2"/></Borders></Style>
            <Style ss:ID="statusAB"><Alignment ss:Horizontal="Center" ss:Vertical="Center"/><Font ss:Bold="1" ss:Color="#B73141"/><Interior ss:Color="#FCE3E6" ss:Pattern="Solid"/><Borders><Border ss:Position="Bottom" ss:LineStyle="Continuous" ss:Weight="1" ss:Color="#E5EAF2"/><Border ss:Position="Left" ss:LineStyle="Continuous" ss:Weight="1" ss:Color="#E5EAF2"/><Border ss:Position="Right" ss:LineStyle="Continuous" ss:Weight="1" ss:Color="#E5EAF2"/><Border ss:Position="Top" ss:LineStyle="Continuous" ss:Weight="1" ss:Color="#E5EAF2"/></Borders></Style>
            <Style ss:ID="statusL"><Alignment ss:Horizontal="Center" ss:Vertical="Center"/><Font ss:Bold="1" ss:Color="#9B6A00"/><Interior ss:Color="#FFF0CB" ss:Pattern="Solid"/><Borders><Border ss:Position="Bottom" ss:LineStyle="Continuous" ss:Weight="1" ss:Color="#E5EAF2"/><Border ss:Position="Left" ss:LineStyle="Continuous" ss:Weight="1" ss:Color="#E5EAF2"/><Border ss:Position="Right" ss:LineStyle="Continuous" ss:Weight="1" ss:Color="#E5EAF2"/><Border ss:Position="Top" ss:LineStyle="Continuous" ss:Weight="1" ss:Color="#E5EAF2"/></Borders></Style>
            <Style ss:ID="statusSUN"><Alignment ss:Horizontal="Center" ss:Vertical="Center"/><Font ss:Bold="1" ss:Color="#1F5EFF"/><Interior ss:Color="#DCE8FF" ss:Pattern="Solid"/><Borders><Border ss:Position="Bottom" ss:LineStyle="Continuous" ss:Weight="1" ss:Color="#E5EAF2"/><Border ss:Position="Left" ss:LineStyle="Continuous" ss:Weight="1" ss:Color="#E5EAF2"/><Border ss:Position="Right" ss:LineStyle="Continuous" ss:Weight="1" ss:Color="#E5EAF2"/><Border ss:Position="Top" ss:LineStyle="Continuous" ss:Weight="1" ss:Color="#E5EAF2"/></Borders></Style>
            <Style ss:ID="statusCOMP"><Alignment ss:Horizontal="Center" ss:Vertical="Center"/><Font ss:Bold="1" ss:Color="#6D28D9"/><Interior ss:Color="#EEE2FF" ss:Pattern="Solid"/><Borders><Border ss:Position="Bottom" ss:LineStyle="Continuous" ss:Weight="1" ss:Color="#E5EAF2"/><Border ss:Position="Left" ss:LineStyle="Continuous" ss:Weight="1" ss:Color="#E5EAF2"/><Border ss:Position="Right" ss:LineStyle="Continuous" ss:Weight="1" ss:Color="#E5EAF2"/><Border ss:Position="Top" ss:LineStyle="Continuous" ss:Weight="1" ss:Color="#E5EAF2"/></Borders></Style>
        </Styles>
        """
    )
    for sheet in sheets:
        xml.write(sheet)
    xml.write("</Workbook>")
    return xml.getvalue()


def generate_attendance_export(month, year, export_format="csv"):
    rows = monthly_export_rows(month, year)
    total_days = calendar.monthrange(year, month)[1]
    headers = [
        "Employee ID",
        "Employee Name",
        "Department",
        "Bank A/c No",
        "IFSC Code",
        "Bank Name",
        *[str(day) for day in range(1, total_days + 1)],
        "Present",
        "Absent",
        "Leave",
        "Sunday Work",
        "Comp Leave",
        "Salary Cut Days",
        "Salary Cut Amount",
        "Final Salary",
        "Night Shift Count",
    ]
    if export_format == "excel":
        excel_rows = []
        for row in rows:
            excel_rows.append(
                [
                row["employee_id"],
                row["employee_name"],
                row["department"],
                row["bank_account_no"],
                row["ifsc_code"],
                row["bank_name"],
                *row["days"],
                row["present_days"],
                row["absent_days"],
                row["leave_days"],
                row["sunday_work_count"],
                row["compensated_leave_count"],
                row["salary_cut_days"],
                row["salary_cut_amount"],
                row["final_salary"],
                row["night_shift_count"],
                ]
            )
        day_columns = list(range(6, 6 + total_days))
        day_labels = [
            date(year, month, day).strftime("%a") for day in range(1, total_days + 1)
        ]
        title = f"TRUNOW Technologies Attendance Report - {calendar.month_name[month]} {year}"
        subtitle = f"Generated on {ist_now().strftime('%d %b %Y, %I:%M %p IST')}"
        summary_headers, summary_rows = build_summary_rows_from_monthly(
            rows, f"{calendar.month_name[month]} {year}"
        )
        return (
            build_excel_workbook(
                [
                    build_excel_sheet("Attendance", title, subtitle, headers, excel_rows, day_columns, day_labels),
                    build_excel_sheet("Summary", f"TRUNOW Attendance Summary - {calendar.month_name[month]} {year}", subtitle, summary_headers, summary_rows),
                ]
            ),
            "application/vnd.ms-excel",
            f"attendance_{year}_{month:02d}.xls",
        )

    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(headers)
    for row in rows:
        writer.writerow(
            [
                row["employee_id"],
                row["employee_name"],
                row["department"],
                row["bank_account_no"],
                row["ifsc_code"],
                row["bank_name"],
                *row["days"],
                row["present_days"],
                row["absent_days"],
                row["leave_days"],
                row["sunday_work_count"],
                row["compensated_leave_count"],
                row["salary_cut_days"],
                row["salary_cut_amount"],
                row["final_salary"],
                row["night_shift_count"],
            ]
        )
    return output.getvalue(), "text/csv", f"attendance_{year}_{month:02d}.csv"


def generate_attendance_export_range(start_date, end_date, export_format="csv"):
    start_obj = datetime.strptime(start_date, "%Y-%m-%d").date()
    end_obj = datetime.strptime(end_date, "%Y-%m-%d").date()
    if end_obj < start_obj:
        start_obj, end_obj = end_obj, start_obj
    employees = query_db(
        """
        SELECT id, employee_id, full_name, department, bank_account_no, ifsc_code, bank_name, monthly_salary
        FROM employees
        WHERE status = 'Active'
        ORDER BY full_name
        """
    )
    day_headers = []
    current = start_obj
    while current <= end_obj:
        day_headers.append(current)
        current += timedelta(days=1)
    headers = [
        "Employee ID",
        "Employee Name",
        "Department",
        "Bank A/c No",
        "IFSC Code",
        "Bank Name",
        *[day.strftime("%d-%m-%Y") for day in day_headers],
        "Present",
        "Absent",
        "Leave",
        "Sunday Work",
        "Comp Leave",
        "Salary Cut Days",
        "Salary Cut Amount",
        "Final Salary",
        "Night Shift Count",
    ]
    rows = []
    for employee in employees:
        salary_info = calculate_leave_and_salary_cut_range(employee["id"], start_obj.isoformat(), end_obj.isoformat())
        row = [
            employee["employee_id"],
            employee["full_name"],
            employee["department"],
            employee["bank_account_no"] or "",
            employee["ifsc_code"] or "",
            employee["bank_name"] or "",
        ]
        for day in day_headers:
            attendance_row = salary_info["day_map"].get(day.isoformat())
            if attendance_row:
                row.append(get_attendance_status_code(attendance_row))
            else:
                row.append("" if day.weekday() == 6 else "AB")
        row.extend(
            [
                salary_info["present_days"],
                salary_info["absent_days"],
                salary_info["leave_days"],
                salary_info["sunday_work_count"],
                salary_info["compensated_leave_count"],
                salary_info["salary_cut_days"],
                salary_info["salary_cut_amount"],
                salary_info["final_salary"],
                salary_info["night_shift_count"],
            ]
        )
        rows.append(row)
    if export_format == "excel":
        day_columns = list(range(6, 6 + len(day_headers)))
        day_labels = [day.strftime("%a") for day in day_headers]
        title = f"TRUNOW Technologies Attendance Report - {start_obj.strftime('%d %b %Y')} to {end_obj.strftime('%d %b %Y')}"
        subtitle = f"Generated on {ist_now().strftime('%d %b %Y, %I:%M %p IST')}"
        summary_headers = [
            "Employee ID",
            "Employee Name",
            "Department",
            "Period",
            "Present",
            "Absent",
            "Leave",
            "Sunday Work",
            "Comp Leave",
            "Salary Cut Days",
            "Salary Cut Amount",
            "Final Salary",
            "Night Shift Count",
        ]
        summary_rows = []
        for row in rows:
            summary_rows.append(
                [
                    row[0],
                    row[1],
                    row[2],
                    f"{start_obj.strftime('%d %b %Y')} to {end_obj.strftime('%d %b %Y')}",
                    row[-9],
                    row[-8],
                    row[-7],
                    row[-6],
                    row[-5],
                    row[-4],
                    row[-3],
                    row[-2],
                    row[-1],
                ]
            )
        return (
            build_excel_workbook(
                [
                    build_excel_sheet("Attendance", title, subtitle, headers, rows, day_columns, day_labels),
                    build_excel_sheet("Summary", f"TRUNOW Attendance Summary - {start_obj.strftime('%d %b %Y')} to {end_obj.strftime('%d %b %Y')}", subtitle, summary_headers, summary_rows),
                ]
            ),
            "application/vnd.ms-excel",
            f"attendance_{start_obj.isoformat()}_to_{end_obj.isoformat()}.xls",
        )
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(headers)
    writer.writerows(rows)
    return output.getvalue(), "text/csv", f"attendance_{start_obj.isoformat()}_to_{end_obj.isoformat()}.csv"


def save_uploaded_file(file_storage, folder):
    if not file_storage or not file_storage.filename:
        return None
    if not allowed_file(file_storage.filename):
        return None
    filename = secure_filename(file_storage.filename)
    timestamp = ist_now().strftime("%Y%m%d%H%M%S%f")
    final_name = f"{timestamp}_{filename}"
    file_storage.save(os.path.join(folder, final_name))
    return final_name


def log_activity(user_type, user_id, action):
    execute_db(
        "INSERT INTO activity_logs (user_type, user_id, action, created_at) VALUES (?, ?, ?, ?)",
        (user_type, user_id, action, ist_now().strftime("%Y-%m-%d %H:%M:%S")),
    )


def init_db():
    ensure_directories()
    schema = """
    CREATE TABLE IF NOT EXISTS admins (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL,
        created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS employees (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        employee_id TEXT NOT NULL UNIQUE,
        full_name TEXT NOT NULL,
        username TEXT NOT NULL UNIQUE,
        phone TEXT NOT NULL UNIQUE,
        email TEXT NOT NULL UNIQUE,
        department TEXT NOT NULL,
        designation TEXT NOT NULL,
        password_hash TEXT NOT NULL,
        profile_photo TEXT,
        monthly_salary REAL NOT NULL DEFAULT 0,
        night_shift_allowed INTEGER NOT NULL DEFAULT 0,
        role TEXT,
        status TEXT NOT NULL DEFAULT 'Active',
        created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS attendance (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        employee_id INTEGER NOT NULL,
        date TEXT NOT NULL,
        day_name TEXT,
        morning_status TEXT NOT NULL DEFAULT 'Present',
        night_status TEXT NOT NULL DEFAULT 'Not Applicable',
        clock_in_time TEXT,
        clock_out_time TEXT,
        night_check_in_time TEXT,
        night_check_out_time TEXT,
        latitude TEXT,
        longitude TEXT,
        location_text TEXT,
        photo TEXT,
        status TEXT NOT NULL DEFAULT 'Present',
        remarks TEXT,
        approval_status TEXT NOT NULL DEFAULT 'Pending',
        admin_approval_status TEXT NOT NULL DEFAULT 'Pending',
        is_sunday_work INTEGER NOT NULL DEFAULT 0,
        is_compensated_leave INTEGER NOT NULL DEFAULT 0,
        salary_cut_status INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL,
        FOREIGN KEY (employee_id) REFERENCES employees (id)
    );

    CREATE TABLE IF NOT EXISTS tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        description TEXT NOT NULL,
        assigned_to INTEGER NOT NULL,
        priority TEXT NOT NULL,
        due_date TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'Pending',
        remarks TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY (assigned_to) REFERENCES employees (id)
    );

    CREATE TABLE IF NOT EXISTS stock (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        item_name TEXT NOT NULL,
        category TEXT NOT NULL,
        quantity INTEGER NOT NULL,
        unit TEXT NOT NULL,
        supplier TEXT NOT NULL,
        purchase_date TEXT NOT NULL,
        status TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS activity_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_type TEXT NOT NULL,
        user_id INTEGER NOT NULL,
        action TEXT NOT NULL,
        created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS leave_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        employee_id INTEGER NOT NULL,
        leave_date TEXT NOT NULL,
        reason TEXT NOT NULL,
        leave_type TEXT NOT NULL,
        remarks TEXT,
        status TEXT NOT NULL DEFAULT 'Pending',
        admin_remarks TEXT,
        created_at TEXT NOT NULL,
        FOREIGN KEY (employee_id) REFERENCES employees (id)
    );

    CREATE TABLE IF NOT EXISTS monthly_salary_report (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        employee_id INTEGER NOT NULL,
        month INTEGER NOT NULL,
        year INTEGER NOT NULL,
        total_working_days INTEGER NOT NULL,
        present_days INTEGER NOT NULL,
        absent_days INTEGER NOT NULL,
        leave_days INTEGER NOT NULL,
        sunday_work_count INTEGER NOT NULL,
        compensated_leave_count INTEGER NOT NULL,
        salary_cut_days INTEGER NOT NULL,
        per_day_salary REAL NOT NULL,
        salary_cut_amount REAL NOT NULL,
        final_salary REAL NOT NULL,
        generated_at TEXT NOT NULL,
        UNIQUE(employee_id, month, year),
        FOREIGN KEY (employee_id) REFERENCES employees (id)
    );
    """
    with closing(sqlite3.connect(DATABASE)) as db:
        db.row_factory = sqlite3.Row
        db.executescript(schema)
        ensure_employee_bank_columns(db)
        ensure_employee_attendance_columns(db)
        ensure_attendance_columns(db)
        migrate_attendance_data(db)
        ensure_leave_and_salary_tables(db)
        db.commit()

    with closing(sqlite3.connect(DATABASE)) as db:
        db.row_factory = sqlite3.Row
        admin = db.execute("SELECT id FROM admins ORDER BY id LIMIT 1").fetchone()
        if not admin:
            db.execute(
                "INSERT INTO admins (username, password_hash, created_at) VALUES (?, ?, ?)",
                (
                    "TRUNOW ADMIN",
                    generate_password_hash("Admin123@"),
                    ist_now().strftime("%Y-%m-%d %H:%M:%S"),
                ),
            )
        else:
            db.execute(
                "UPDATE admins SET username = ?, password_hash = ? WHERE id = ?",
                (
                    "TRUNOW ADMIN",
                    generate_password_hash("Admin123@"),
                    admin["id"],
                ),
            )

        created_at = ist_now().strftime("%Y-%m-%d %H:%M:%S")
        seed_employee_ids = [employee["employee_id"] for employee in EMPLOYEE_SEED_DATA]
        removed_employee_rows = db.execute(
            f"SELECT id, full_name FROM employees WHERE employee_id NOT IN ({','.join(['?'] * len(seed_employee_ids))})",
            tuple(seed_employee_ids),
        ).fetchall()
        if removed_employee_rows:
            removed_ids = tuple(row["id"] for row in removed_employee_rows)
            placeholders = ",".join(["?"] * len(removed_ids))
            db.execute(f"DELETE FROM attendance WHERE employee_id IN ({placeholders})", removed_ids)
            db.execute(f"DELETE FROM leave_requests WHERE employee_id IN ({placeholders})", removed_ids)
            db.execute(f"DELETE FROM monthly_salary_report WHERE employee_id IN ({placeholders})", removed_ids)
            db.execute(f"DELETE FROM tasks WHERE assigned_to IN ({placeholders})", removed_ids)
            db.execute(
                f"DELETE FROM activity_logs WHERE user_type = 'employee' AND user_id IN ({placeholders})",
                removed_ids,
            )
            db.execute(f"DELETE FROM employees WHERE id IN ({placeholders})", removed_ids)

        for index, employee in enumerate(EMPLOYEE_SEED_DATA, start=1):
            phone = f"900000{index:04d}"
            email = f"{employee['username']}@trunowindia.com"
            existing_employee = db.execute(
                "SELECT id FROM employees WHERE employee_id = ?", (employee["employee_id"],)
            ).fetchone()
            if existing_employee:
                db.execute(
                    """
                    UPDATE employees
                    SET employee_id = ?, full_name = ?, username = ?, phone = ?, email = ?, department = ?, designation = ?, password_hash = ?, status = ?, role = COALESCE(role, ?), monthly_salary = COALESCE(monthly_salary, 0), night_shift_allowed = COALESCE(night_shift_allowed, 0), bank_account_no = ?, ifsc_code = ?, bank_name = ?
                    WHERE employee_id = ?
                    """,
                    (
                        employee["employee_id"],
                        employee["full_name"],
                        employee["username"],
                        phone,
                        email,
                        "Operations",
                        "Employee",
                        generate_password_hash(employee["password"]),
                        "Active",
                        "Employee",
                        employee["bank_account_no"],
                        employee["ifsc_code"],
                        employee["bank_name"],
                        employee["employee_id"],
                    ),
                )
            else:
                db.execute(
                    """
                    INSERT INTO employees
                    (employee_id, full_name, username, phone, email, department, designation, password_hash, status, created_at, bank_account_no, ifsc_code, bank_name, monthly_salary, night_shift_allowed, role)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        employee["employee_id"],
                        employee["full_name"],
                        employee["username"],
                        phone,
                        email,
                        "Operations",
                        "Employee",
                        generate_password_hash(employee["password"]),
                        "Active",
                        created_at,
                        employee["bank_account_no"],
                        employee["ifsc_code"],
                        employee["bank_name"],
                        0,
                        0,
                        "Employee",
                    ),
                )

        stock_count = db.execute("SELECT COUNT(*) AS count FROM stock").fetchone()["count"]
        if stock_count == 0:
            created_at = ist_now().strftime("%Y-%m-%d %H:%M:%S")
            db.executemany(
                """
                INSERT INTO stock
                (item_name, category, quantity, unit, supplier, purchase_date, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        "Cat6 Cable Box",
                        "Cabling",
                        24,
                        "Boxes",
                        "NetSource India",
                        "2026-04-10",
                        "Available",
                        created_at,
                        created_at,
                    ),
                    (
                        "Fiber Patch Panel",
                        "Fiber Optics",
                        5,
                        "Units",
                        "OptiLink Systems",
                        "2026-04-21",
                        "Low Stock",
                        created_at,
                        created_at,
                    ),
                ],
            )
        db.commit()


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if session.get("user_type") != "admin":
            flash("Please login as admin to continue.", "warning")
            return redirect(url_for("admin_login"))
        return view(*args, **kwargs)

    return wrapped


def employee_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if session.get("user_type") != "employee":
            flash("Please login as employee to continue.", "warning")
            return redirect(url_for("employee_login"))
        return view(*args, **kwargs)

    return wrapped


@app.context_processor
def inject_globals():
    current_employee = None
    if session.get("user_type") == "employee" and session.get("user_id"):
        current_employee = query_db(
            "SELECT * FROM employees WHERE id = ?", (session["user_id"],), one=True
        )
    return {
        "current_year": 2026,
        "session_user_type": session.get("user_type"),
        "current_employee": current_employee,
    }


@app.route("/")
def index():
    employees_count = query_db("SELECT COUNT(*) AS count FROM employees", one=True)["count"]
    active_projects = query_db("SELECT COUNT(*) AS count FROM tasks WHERE status != 'Completed'", one=True)[
        "count"
    ]
    return render_template(
        "index.html",
        employees_count=employees_count,
        active_projects=active_projects,
    )


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        if not username or not password:
            flash("Username and password are required.", "danger")
            return render_template("admin_login.html")

        admin = query_db("SELECT * FROM admins WHERE username = ?", (username,), one=True)
        if admin and check_password_hash(admin["password_hash"], password):
            session.clear()
            session["user_type"] = "admin"
            session["user_id"] = admin["id"]
            session["username"] = admin["username"]
            log_activity("admin", admin["id"], "Logged into admin portal")
            return redirect(url_for("admin_dashboard"))

        flash("Invalid admin credentials.", "danger")
    return render_template("admin_login.html")


@app.route("/employee/login", methods=["GET", "POST"])
def employee_login():
    if request.method == "POST":
        identifier = request.form.get("identifier", "").strip()
        password = request.form.get("password", "").strip()
        if not identifier or not password:
            flash("Username or phone and password are required.", "danger")
            return render_template("employee_login.html")

        employee = query_db(
            "SELECT * FROM employees WHERE username = ? OR phone = ?",
            (identifier, identifier),
            one=True,
        )
        if employee and check_password_hash(employee["password_hash"], password):
            session.clear()
            session["user_type"] = "employee"
            session["user_id"] = employee["id"]
            session["username"] = employee["username"]
            log_activity("employee", employee["id"], "Logged into employee portal")
            return redirect(url_for("employee_dashboard"))

        flash("Invalid employee credentials.", "danger")
    return render_template("employee_login.html")


@app.route("/logout")
def logout():
    user_type = session.get("user_type")
    user_id = session.get("user_id")
    if user_type and user_id:
        log_activity(user_type, user_id, "Logged out")
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("index"))


@app.route("/admin/dashboard")
@admin_required
def admin_dashboard():
    total_employees = query_db("SELECT COUNT(*) AS count FROM employees", one=True)["count"]
    today = ist_today().isoformat()
    present_today = query_db(
        "SELECT COUNT(DISTINCT employee_id) AS count FROM attendance WHERE date = ?",
        (today,),
        one=True,
    )["count"]
    pending_tasks = query_db(
        "SELECT COUNT(*) AS count FROM tasks WHERE status != 'Completed'", one=True
    )["count"]
    stock_items = query_db("SELECT COUNT(*) AS count FROM stock", one=True)["count"]
    recent_activity = query_db(
        """
        SELECT a.*, e.full_name
        FROM activity_logs a
        LEFT JOIN employees e ON a.user_type = 'employee' AND a.user_id = e.id
        ORDER BY a.created_at DESC
        LIMIT 8
        """
    )
    low_stock = query_db("SELECT * FROM stock WHERE quantity <= 5 ORDER BY quantity ASC LIMIT 5")
    return render_template(
        "admin/dashboard.html",
        total_employees=total_employees,
        present_today=present_today,
        pending_tasks=pending_tasks,
        stock_items=stock_items,
        recent_activity=recent_activity,
        low_stock=low_stock,
        today=today,
    )


@app.route("/admin/employees")
@admin_required
def admin_employees():
    search = request.args.get("search", "").strip()
    if search:
        employees = query_db(
            """
            SELECT * FROM employees
            WHERE full_name LIKE ? OR username LIKE ? OR department LIKE ? OR designation LIKE ?
            ORDER BY created_at DESC
            """,
            tuple([f"%{search}%"] * 4),
        )
    else:
        employees = query_db("SELECT * FROM employees ORDER BY created_at DESC")
    return render_template("admin/employees.html", employees=employees, search=search)


@app.route("/admin/employees/add", methods=["GET", "POST"])
@admin_required
def add_employee():
    if request.method == "POST":
        fields = get_employee_form_data(request.form, include_password=True)
        if not employee_required_fields_complete(fields, include_password=True):
            flash("Please complete all employee fields.", "danger")
            return render_template("admin/add_employee.html", employee=fields)
        bank_error = validate_employee_bank_fields(fields)
        if bank_error:
            flash(bank_error, "danger")
            return render_template("admin/add_employee.html", employee=fields)

        photo_name = save_uploaded_file(request.files.get("profile_photo"), PROFILE_UPLOAD)
        try:
            execute_db(
                """
                INSERT INTO employees
                (employee_id, full_name, username, phone, email, department, designation, password_hash, profile_photo, status, created_at, bank_account_no, ifsc_code, bank_name, monthly_salary, night_shift_allowed, role)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    fields["employee_id"],
                    fields["full_name"],
                    fields["username"],
                    fields["phone"],
                    fields["email"],
                    fields["department"],
                    fields["designation"],
                    generate_password_hash(fields["password"]),
                    photo_name,
                    fields["status"],
                    ist_now().strftime("%Y-%m-%d %H:%M:%S"),
                    fields["bank_account_no"] or None,
                    fields["ifsc_code"] or None,
                    fields["bank_name"] or None,
                    float(fields["monthly_salary"] or 0),
                    int(fields["night_shift_allowed"]),
                    fields["role"],
                ),
            )
            log_activity("admin", session["user_id"], f"Added employee {fields['full_name']}")
            flash("Employee added successfully.", "success")
            return redirect(url_for("admin_employees"))
        except sqlite3.IntegrityError:
            flash("Employee ID, username, phone, or email already exists.", "danger")
    return render_template("admin/add_employee.html", employee=None)


@app.route("/admin/employees/edit/<int:id>", methods=["GET", "POST"])
@admin_required
def edit_employee(id):
    employee = query_db("SELECT * FROM employees WHERE id = ?", (id,), one=True)
    if not employee:
        flash("Employee not found.", "danger")
        return redirect(url_for("admin_employees"))

    if request.method == "POST":
        fields = get_employee_form_data(request.form)
        if not employee_required_fields_complete(fields):
            flash("Please complete all employee fields.", "danger")
            return render_template("admin/add_employee.html", employee=fields, edit_mode=True, employee_row=employee)
        bank_error = validate_employee_bank_fields(fields)
        if bank_error:
            flash(bank_error, "danger")
            return render_template("admin/add_employee.html", employee=fields, edit_mode=True, employee_row=employee)

        photo_name = save_uploaded_file(request.files.get("profile_photo"), PROFILE_UPLOAD)
        password = request.form.get("password", "").strip()
        password_hash = employee["password_hash"] if not password else generate_password_hash(password)
        final_photo = photo_name or employee["profile_photo"]
        try:
            execute_db(
                """
                UPDATE employees
                SET employee_id = ?, full_name = ?, username = ?, phone = ?, email = ?, department = ?, designation = ?, password_hash = ?, profile_photo = ?, status = ?, bank_account_no = ?, ifsc_code = ?, bank_name = ?, monthly_salary = ?, night_shift_allowed = ?, role = ?
                WHERE id = ?
                """,
                (
                    fields["employee_id"],
                    fields["full_name"],
                    fields["username"],
                    fields["phone"],
                    fields["email"],
                    fields["department"],
                    fields["designation"],
                    password_hash,
                    final_photo,
                    fields["status"],
                    fields["bank_account_no"] or None,
                    fields["ifsc_code"] or None,
                    fields["bank_name"] or None,
                    float(fields["monthly_salary"] or 0),
                    int(fields["night_shift_allowed"]),
                    fields["role"],
                    id,
                ),
            )
            log_activity("admin", session["user_id"], f"Updated employee {fields['full_name']}")
            flash("Employee updated successfully.", "success")
            return redirect(url_for("admin_employees"))
        except sqlite3.IntegrityError:
            flash("Employee ID, username, phone, or email already exists.", "danger")

    return render_template("admin/add_employee.html", employee=employee, edit_mode=True, employee_row=employee)


@app.route("/admin/employees/delete/<int:id>", methods=["POST"])
@admin_required
def delete_employee(id):
    employee = query_db("SELECT * FROM employees WHERE id = ?", (id,), one=True)
    if employee:
        execute_db("DELETE FROM employees WHERE id = ?", (id,))
        log_activity("admin", session["user_id"], f"Deleted employee {employee['full_name']}")
        flash("Employee deleted.", "success")
    return redirect(url_for("admin_employees"))


@app.route("/admin/attendance", methods=["GET", "POST"])
@admin_required
def admin_attendance():
    if request.method == "POST":
        action = request.form.get("form_action", "").strip()
        if action == "save_attendance":
            employee_id = request.form.get("employee_id", "").strip()
            record_date = request.form.get("attendance_date", "").strip()
            morning_status = request.form.get("morning_status", "").strip() or "Present"
            night_status = request.form.get("night_status", "").strip() or "Not Applicable"
            approval_status = request.form.get("approval_status", "").strip() or "Approved"
            remarks = request.form.get("remarks", "").strip()
            location_text = request.form.get("location_text", "").strip()
            check_in_time = request.form.get("check_in_time", "").strip()
            check_out_time = request.form.get("check_out_time", "").strip()
            night_check_in_time = request.form.get("night_check_in_time", "").strip()
            night_check_out_time = request.form.get("night_check_out_time", "").strip()
            is_sunday_work_value = 1 if request.form.get("is_sunday_work") == "1" else 0
            is_compensated_leave = 1 if request.form.get("is_compensated_leave") == "1" else 0
            if not employee_id or not record_date:
                flash("Employee and attendance date are required.", "danger")
                return redirect(url_for("admin_attendance"))
            if morning_status not in MORNING_STATUS_OPTIONS or night_status not in NIGHT_STATUS_OPTIONS:
                flash("Invalid attendance status selected.", "danger")
                return redirect(url_for("admin_attendance"))
            if approval_status not in APPROVAL_STATUS_OPTIONS:
                flash("Invalid approval status selected.", "danger")
                return redirect(url_for("admin_attendance"))
            if record_date:
                try:
                    record_date, _ = normalize_date_range(record_date, record_date)
                except ValueError:
                    flash("Invalid attendance date selected.", "danger")
                    return redirect(url_for("admin_attendance"))
            day_name = get_day_name(record_date)
            if is_sunday_work_value and not is_sunday(record_date):
                flash("Sunday Work can only be marked on actual Sundays.", "danger")
                return redirect(url_for("admin_attendance"))
            if is_compensated_leave and (morning_status != "Leave" or is_sunday(record_date)):
                flash("Compensated leave can only be marked for a leave day on a working day.", "danger")
                return redirect(url_for("admin_attendance"))
            is_sunday_work_value = 1 if is_sunday(record_date) and morning_status == "Present" and is_sunday_work_value else 0
            final_check_in = check_in_time or None if morning_status == "Present" else None
            final_check_out = check_out_time or None if morning_status == "Present" else None
            final_night_in = night_check_in_time or None if night_status == "Present" else None
            final_night_out = night_check_out_time or None if night_status == "Present" else None
            final_location = location_text or None if (morning_status == "Present" or night_status == "Present") else None
            existing_record = query_db(
                "SELECT id FROM attendance WHERE employee_id = ? AND date = ? ORDER BY id DESC LIMIT 1",
                (employee_id, record_date),
                one=True,
            )
            if existing_record:
                execute_db(
                    """
                    UPDATE attendance
                    SET day_name = ?, morning_status = ?, night_status = ?, clock_in_time = ?, clock_out_time = ?,
                        night_check_in_time = ?, night_check_out_time = ?, location_text = ?, remarks = ?,
                        approval_status = ?, admin_approval_status = ?, is_sunday_work = ?, is_compensated_leave = ?,
                        salary_cut_status = ?, status = ?
                    WHERE id = ?
                    """,
                    (
                        day_name,
                        morning_status,
                        night_status,
                        final_check_in,
                        final_check_out,
                        final_night_in,
                        final_night_out,
                        final_location,
                        remarks or None,
                        approval_status,
                        approval_status,
                        is_sunday_work_value,
                        is_compensated_leave,
                        1 if (morning_status == "Leave" and not is_compensated_leave) else 0,
                        morning_status,
                        existing_record["id"],
                    ),
                )
            else:
                execute_db(
                    """
                    INSERT INTO attendance
                    (
                        employee_id, date, day_name, morning_status, night_status, clock_in_time, clock_out_time,
                        night_check_in_time, night_check_out_time, location_text, remarks, approval_status,
                        admin_approval_status, is_sunday_work, is_compensated_leave, salary_cut_status,
                        status, created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        employee_id,
                        record_date,
                        day_name,
                        morning_status,
                        night_status,
                        final_check_in,
                        final_check_out,
                        final_night_in,
                        final_night_out,
                        final_location,
                        remarks or None,
                        approval_status,
                        approval_status,
                        is_sunday_work_value,
                        is_compensated_leave,
                        1 if (morning_status == "Leave" and not is_compensated_leave) else 0,
                        morning_status,
                        ist_now().strftime("%Y-%m-%d %H:%M:%S"),
                    ),
                )
            log_activity("admin", session["user_id"], f"Saved attendance for employee #{employee_id} on {record_date}")
            flash("Attendance record saved successfully.", "success")
            return redirect(url_for("admin_attendance"))

        if action == "review_attendance":
            attendance_id = request.form.get("attendance_id", "").strip()
            approval_status = request.form.get("approval_status", "").strip()
            remarks = request.form.get("remarks", "").strip()
            if approval_status not in APPROVAL_STATUS_OPTIONS:
                flash("Invalid approval status selected.", "danger")
                return redirect(url_for("admin_attendance"))
            execute_db(
                "UPDATE attendance SET approval_status = ?, admin_approval_status = ?, remarks = COALESCE(?, remarks) WHERE id = ?",
                (approval_status, approval_status, remarks or None, attendance_id),
            )
            flash("Attendance approval updated.", "success")
            return redirect(url_for("admin_attendance"))

        if action == "review_leave":
            leave_request_id = request.form.get("leave_request_id", "").strip()
            decision = request.form.get("decision", "").strip()
            admin_remarks = request.form.get("admin_remarks", "").strip()
            leave_request = query_db("SELECT * FROM leave_requests WHERE id = ?", (leave_request_id,), one=True)
            if not leave_request:
                flash("Leave request not found.", "danger")
                return redirect(url_for("admin_attendance"))
            if decision not in {"Approved", "Rejected"}:
                flash("Invalid leave decision.", "danger")
                return redirect(url_for("admin_attendance"))
            execute_db(
                "UPDATE leave_requests SET status = ?, admin_remarks = ? WHERE id = ?",
                (decision, admin_remarks or None, leave_request_id),
            )
            if decision == "Approved":
                leave_day_name = get_day_name(leave_request["leave_date"])
                if leave_day_name == "Sunday":
                    flash("Sunday is a holiday and cannot be approved as a leave day.", "danger")
                    return redirect(url_for("admin_attendance"))
                existing_record = query_db(
                    "SELECT id FROM attendance WHERE employee_id = ? AND date = ? ORDER BY id DESC LIMIT 1",
                    (leave_request["employee_id"], leave_request["leave_date"]),
                    one=True,
                )
                if existing_record:
                    execute_db(
                        """
                        UPDATE attendance
                        SET day_name = ?, morning_status = 'Leave', night_status = 'Not Applicable', remarks = ?,
                            approval_status = 'Approved', admin_approval_status = 'Approved', is_sunday_work = 0,
                            is_compensated_leave = 0, salary_cut_status = 0, status = 'Leave',
                            clock_in_time = NULL, clock_out_time = NULL, night_check_in_time = NULL, night_check_out_time = NULL,
                            latitude = NULL, longitude = NULL, location_text = NULL, photo = NULL
                        WHERE id = ?
                        """,
                        (
                            leave_day_name,
                            leave_request["reason"],
                            existing_record["id"],
                        ),
                    )
                else:
                    execute_db(
                        """
                        INSERT INTO attendance
                        (
                            employee_id, date, day_name, morning_status, night_status, remarks, approval_status,
                            admin_approval_status, is_sunday_work, is_compensated_leave, salary_cut_status, status, created_at
                        )
                        VALUES (?, ?, ?, 'Leave', 'Not Applicable', ?, 'Approved', 'Approved', 0, 0, 0, 'Leave', ?)
                        """,
                        (
                            leave_request["employee_id"],
                            leave_request["leave_date"],
                            leave_day_name,
                            leave_request["reason"],
                            ist_now().strftime("%Y-%m-%d %H:%M:%S"),
                        ),
                    )
            flash("Leave request updated.", "success")
            return redirect(url_for("admin_attendance"))

    selected_from_date = request.args.get("from_date", "").strip()
    selected_to_date = request.args.get("to_date", "").strip()
    selected_employee = request.args.get("employee_id", "").strip()
    selected_department = request.args.get("department", "").strip()
    selected_status = request.args.get("status", "").strip()
    selected_morning_shift = request.args.get("morning_shift", "").strip()
    selected_night_shift = request.args.get("night_shift", "").strip()
    if selected_from_date and selected_to_date:
        try:
            selected_from_date, selected_to_date = normalize_date_range(selected_from_date, selected_to_date)
        except ValueError:
            flash("Invalid date range selected.", "danger")
            return redirect(url_for("admin_attendance"))
    refresh_start_date = selected_from_date or selected_to_date or date(ist_today().year, ist_today().month, 1).isoformat()
    refresh_end_date = selected_to_date or selected_from_date or ist_today().isoformat()
    employee_scope_rows = (
        query_db("SELECT id FROM employees WHERE id = ?", (selected_employee,))
        if selected_employee
        else query_db("SELECT id FROM employees WHERE status = 'Active'")
    )
    for employee_row in employee_scope_rows:
        refresh_compensation_flags_for_range(employee_row["id"], refresh_start_date, refresh_end_date)

    query = """
    SELECT a.*, e.full_name, e.employee_id AS emp_code, e.department
    FROM attendance a
    JOIN employees e ON a.employee_id = e.id
    WHERE 1 = 1
    """
    params = []
    if selected_from_date:
        query += " AND a.date >= ?"
        params.append(selected_from_date)
    if selected_to_date:
        query += " AND a.date <= ?"
        params.append(selected_to_date)
    if selected_employee:
        query += " AND e.id = ?"
        params.append(selected_employee)
    if selected_department:
        query += " AND e.department = ?"
        params.append(selected_department)
    if selected_morning_shift:
        query += " AND a.morning_status = ?"
        params.append(selected_morning_shift)
    if selected_night_shift:
        query += " AND a.night_status = ?"
        params.append(selected_night_shift)
    if selected_status == "P":
        query += " AND a.morning_status = 'Present' AND COALESCE(a.is_sunday_work, 0) = 0"
    elif selected_status == "AB":
        query += " AND a.morning_status = 'Absent'"
    elif selected_status == "L":
        query += " AND a.morning_status = 'Leave' AND COALESCE(a.is_compensated_leave, 0) = 0"
    elif selected_status == "SUN-WORK":
        query += " AND COALESCE(a.is_sunday_work, 0) = 1"
    elif selected_status == "COMP":
        query += " AND COALESCE(a.is_compensated_leave, 0) = 1"
    query += " ORDER BY a.date DESC, a.created_at DESC"

    attendance_rows = [dict(row) for row in query_db(query, tuple(params))]
    for row in attendance_rows:
        row["status_label"] = get_attendance_status_label(row)
        row["status_code"] = get_attendance_status_code(row)
        row["status_badge"] = get_attendance_badge_class(row["status_label"])
    employees = query_db("SELECT id, full_name, department FROM employees ORDER BY full_name")
    departments = query_db("SELECT DISTINCT department FROM employees ORDER BY department")
    pending_leave_requests = query_db(
        """
        SELECT lr.*, e.full_name, e.employee_id AS emp_code
        FROM leave_requests lr
        JOIN employees e ON lr.employee_id = e.id
        ORDER BY CASE lr.status WHEN 'Pending' THEN 0 ELSE 1 END, lr.leave_date DESC
        LIMIT 12
        """
    )
    today = ist_today().isoformat()
    total_employees = query_db("SELECT COUNT(*) AS count FROM employees WHERE status = 'Active'", one=True)["count"]
    today_records = query_db(
        """
        SELECT *
        FROM attendance
        WHERE date = ? AND approval_status != 'Rejected'
        """,
        (today,),
    )
    present_today = sum(1 for row in today_records if row["morning_status"] == "Present" and not row["is_sunday_work"])
    leave_today = sum(1 for row in today_records if row["morning_status"] == "Leave")
    night_shift_today = sum(1 for row in today_records if row["night_status"] == "Present")
    sunday_work_today = sum(1 for row in today_records if row["is_sunday_work"])
    absent_today = 0 if is_sunday(today) else max(0, total_employees - present_today - leave_today)

    if request.args.get("export") == "excel":
        output = StringIO()
        writer = csv.writer(output)
        writer.writerow(
            [
                "Employee",
                "Employee ID",
                "Department",
                "Date",
                "Day",
                "Morning Shift",
                "Night Shift",
                "Clock In",
                "Clock Out",
                "Night In",
                "Night Out",
                "Location",
                "Remarks",
                "Status",
                "Approval",
            ]
        )
        for row in attendance_rows:
            writer.writerow(
                [
                    row["full_name"],
                    row["emp_code"],
                    row["department"],
                    row["date"],
                    row["day_name"],
                    row["morning_status"],
                    row["night_status"],
                    row["clock_in_time"],
                    row["clock_out_time"],
                    row["night_check_in_time"],
                    row["night_check_out_time"],
                    row["location_text"],
                    row["remarks"],
                    row["status_code"],
                    row["approval_status"],
                ]
            )
        headers = [
            "Employee",
            "Employee ID",
            "Department",
            "Date",
            "Day",
            "Morning Shift",
            "Night Shift",
            "Clock In",
            "Clock Out",
            "Night In",
            "Night Out",
            "Location",
            "Remarks",
            "Status",
            "Approval",
        ]
        excel_rows = [list(row) for row in []]
        excel_rows = []
        for row in attendance_rows:
            excel_rows.append(
                [
                    row["full_name"],
                    row["emp_code"],
                    row["department"],
                    row["date"],
                    row["day_name"],
                    row["morning_status"],
                    row["night_status"],
                    row["clock_in_time"] or "",
                    row["clock_out_time"] or "",
                    row["night_check_in_time"] or "",
                    row["night_check_out_time"] or "",
                    row["location_text"] or "",
                    row["remarks"] or "",
                    row["status_code"],
                    row["approval_status"],
                ]
            )
        workbook = build_excel_workbook(
            [
                build_excel_sheet(
                    "Attendance Register",
                    "TRUNOW Attendance Register",
                    f"Generated on {ist_now().strftime('%d %b %Y, %I:%M %p IST')}",
                    headers,
                    excel_rows,
                )
            ]
        )
        return Response(
            workbook,
            mimetype="application/vnd.ms-excel",
            headers={"Content-Disposition": "attachment; filename=attendance_register.xls"},
        )

    return render_template(
        "admin/attendance.html",
        attendance_rows=attendance_rows,
        employees=employees,
        departments=departments,
        selected_from_date=selected_from_date,
        selected_to_date=selected_to_date,
        selected_employee=selected_employee,
        selected_department=selected_department,
        selected_status=selected_status,
        selected_morning_shift=selected_morning_shift,
        selected_night_shift=selected_night_shift,
        pending_leave_requests=pending_leave_requests,
        total_employees=total_employees,
        present_today=present_today,
        absent_today=absent_today,
        leave_today=leave_today,
        night_shift_today=night_shift_today,
        sunday_work_today=sunday_work_today,
        today=today,
    )


@app.route("/admin/tasks")
@admin_required
def admin_tasks():
    tasks = query_db(
        """
        SELECT t.*, e.full_name
        FROM tasks t
        JOIN employees e ON t.assigned_to = e.id
        ORDER BY t.due_date ASC, t.updated_at DESC
        """
    )
    return render_template("admin/tasks.html", tasks=tasks)


@app.route("/admin/tasks/add", methods=["GET", "POST"])
@admin_required
def add_task():
    employees = query_db("SELECT id, full_name, department FROM employees WHERE status = 'Active' ORDER BY full_name")
    if request.method == "POST":
        fields = {
            "title": request.form.get("title", "").strip(),
            "description": request.form.get("description", "").strip(),
            "assigned_to": request.form.get("assigned_to", "").strip(),
            "priority": request.form.get("priority", "").strip(),
            "due_date": request.form.get("due_date", "").strip(),
            "status": request.form.get("status", "Pending").strip(),
        }
        if not all(fields.values()):
            flash("Please complete all task fields.", "danger")
            return render_template("admin/tasks.html", tasks=query_db(
                """
                SELECT t.*, e.full_name
                FROM tasks t JOIN employees e ON t.assigned_to = e.id
                ORDER BY t.due_date ASC, t.updated_at DESC
                """
            ), employees=employees, show_form=True, task_form=fields)
        now = ist_now().strftime("%Y-%m-%d %H:%M:%S")
        execute_db(
            """
            INSERT INTO tasks (title, description, assigned_to, priority, due_date, status, remarks, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                fields["title"],
                fields["description"],
                fields["assigned_to"],
                fields["priority"],
                fields["due_date"],
                fields["status"],
                "",
                now,
                now,
            ),
        )
        assignee = query_db("SELECT full_name FROM employees WHERE id = ?", (fields["assigned_to"],), one=True)
        log_activity("admin", session["user_id"], f"Assigned task '{fields['title']}' to {assignee['full_name']}")
        flash("Task created successfully.", "success")
        return redirect(url_for("admin_tasks"))
    return render_template("admin/tasks.html", tasks=query_db(
        """
        SELECT t.*, e.full_name
        FROM tasks t JOIN employees e ON t.assigned_to = e.id
        ORDER BY t.due_date ASC, t.updated_at DESC
        """
    ), employees=employees, show_form=True)


@app.route("/admin/tasks/edit/<int:id>", methods=["GET", "POST"])
@admin_required
def edit_task(id):
    task = query_db("SELECT * FROM tasks WHERE id = ?", (id,), one=True)
    employees = query_db("SELECT id, full_name, department FROM employees WHERE status = 'Active' ORDER BY full_name")
    if not task:
        flash("Task not found.", "danger")
        return redirect(url_for("admin_tasks"))
    if request.method == "POST":
        fields = {
            "title": request.form.get("title", "").strip(),
            "description": request.form.get("description", "").strip(),
            "assigned_to": request.form.get("assigned_to", "").strip(),
            "priority": request.form.get("priority", "").strip(),
            "due_date": request.form.get("due_date", "").strip(),
            "status": request.form.get("status", "Pending").strip(),
        }
        if not all(fields.values()):
            flash("Please complete all task fields.", "danger")
            return render_template("admin/tasks.html", tasks=query_db(
                """
                SELECT t.*, e.full_name
                FROM tasks t JOIN employees e ON t.assigned_to = e.id
                ORDER BY t.due_date ASC, t.updated_at DESC
                """
            ), employees=employees, show_form=True, edit_mode=True, task_form=fields, task_row=task)
        execute_db(
            """
            UPDATE tasks
            SET title = ?, description = ?, assigned_to = ?, priority = ?, due_date = ?, status = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                fields["title"],
                fields["description"],
                fields["assigned_to"],
                fields["priority"],
                fields["due_date"],
                fields["status"],
                ist_now().strftime("%Y-%m-%d %H:%M:%S"),
                id,
            ),
        )
        log_activity("admin", session["user_id"], f"Updated task '{fields['title']}'")
        flash("Task updated successfully.", "success")
        return redirect(url_for("admin_tasks"))

    tasks = query_db(
        """
        SELECT t.*, e.full_name
        FROM tasks t JOIN employees e ON t.assigned_to = e.id
        ORDER BY t.due_date ASC, t.updated_at DESC
        """
    )
    return render_template("admin/tasks.html", tasks=tasks, employees=employees, show_form=True, edit_mode=True, task_form=task, task_row=task)


@app.route("/admin/tasks/delete/<int:id>", methods=["POST"])
@admin_required
def delete_task(id):
    task = query_db("SELECT * FROM tasks WHERE id = ?", (id,), one=True)
    if task:
        execute_db("DELETE FROM tasks WHERE id = ?", (id,))
        log_activity("admin", session["user_id"], f"Deleted task '{task['title']}'")
        flash("Task deleted.", "success")
    return redirect(url_for("admin_tasks"))


@app.route("/admin/stock")
@admin_required
def admin_stock():
    stock_items = query_db("SELECT * FROM stock ORDER BY updated_at DESC")
    return render_template("admin/stock.html", stock_items=stock_items)


@app.route("/admin/stock/add", methods=["GET", "POST"])
@admin_required
def add_stock():
    if request.method == "POST":
        fields = {
            "item_name": request.form.get("item_name", "").strip(),
            "category": request.form.get("category", "").strip(),
            "quantity": request.form.get("quantity", "").strip(),
            "unit": request.form.get("unit", "").strip(),
            "supplier": request.form.get("supplier", "").strip(),
            "purchase_date": request.form.get("purchase_date", "").strip(),
            "status": request.form.get("status", "").strip(),
        }
        if not all(fields.values()):
            flash("Please complete all stock fields.", "danger")
            return render_template("admin/stock.html", stock_items=query_db("SELECT * FROM stock ORDER BY updated_at DESC"), show_form=True, stock_form=fields)
        now = ist_now().strftime("%Y-%m-%d %H:%M:%S")
        execute_db(
            """
            INSERT INTO stock (item_name, category, quantity, unit, supplier, purchase_date, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                fields["item_name"],
                fields["category"],
                int(fields["quantity"]),
                fields["unit"],
                fields["supplier"],
                fields["purchase_date"],
                fields["status"],
                now,
                now,
            ),
        )
        log_activity("admin", session["user_id"], f"Added stock item {fields['item_name']}")
        flash("Stock item added successfully.", "success")
        return redirect(url_for("admin_stock"))
    return render_template("admin/stock.html", stock_items=query_db("SELECT * FROM stock ORDER BY updated_at DESC"), show_form=True)


@app.route("/admin/stock/edit/<int:id>", methods=["GET", "POST"])
@admin_required
def edit_stock(id):
    stock_item = query_db("SELECT * FROM stock WHERE id = ?", (id,), one=True)
    if not stock_item:
        flash("Stock item not found.", "danger")
        return redirect(url_for("admin_stock"))

    if request.method == "POST":
        fields = {
            "item_name": request.form.get("item_name", "").strip(),
            "category": request.form.get("category", "").strip(),
            "quantity": request.form.get("quantity", "").strip(),
            "unit": request.form.get("unit", "").strip(),
            "supplier": request.form.get("supplier", "").strip(),
            "purchase_date": request.form.get("purchase_date", "").strip(),
            "status": request.form.get("status", "").strip(),
        }
        if not all(fields.values()):
            flash("Please complete all stock fields.", "danger")
            return render_template("admin/stock.html", stock_items=query_db("SELECT * FROM stock ORDER BY updated_at DESC"), show_form=True, edit_mode=True, stock_form=fields, stock_row=stock_item)
        execute_db(
            """
            UPDATE stock
            SET item_name = ?, category = ?, quantity = ?, unit = ?, supplier = ?, purchase_date = ?, status = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                fields["item_name"],
                fields["category"],
                int(fields["quantity"]),
                fields["unit"],
                fields["supplier"],
                fields["purchase_date"],
                fields["status"],
                ist_now().strftime("%Y-%m-%d %H:%M:%S"),
                id,
            ),
        )
        log_activity("admin", session["user_id"], f"Updated stock item {fields['item_name']}")
        flash("Stock item updated successfully.", "success")
        return redirect(url_for("admin_stock"))
    return render_template("admin/stock.html", stock_items=query_db("SELECT * FROM stock ORDER BY updated_at DESC"), show_form=True, edit_mode=True, stock_form=stock_item, stock_row=stock_item)


@app.route("/admin/stock/delete/<int:id>", methods=["POST"])
@admin_required
def delete_stock(id):
    stock_item = query_db("SELECT * FROM stock WHERE id = ?", (id,), one=True)
    if stock_item:
        execute_db("DELETE FROM stock WHERE id = ?", (id,))
        log_activity("admin", session["user_id"], f"Deleted stock item {stock_item['item_name']}")
        flash("Stock item deleted.", "success")
    return redirect(url_for("admin_stock"))


@app.route("/admin/reports")
@admin_required
def admin_reports():
    selected_start_date = request.args.get("start_date", "").strip()
    selected_end_date = request.args.get("end_date", "").strip()
    if selected_start_date and selected_end_date:
        try:
            selected_start_date, selected_end_date = normalize_date_range(selected_start_date, selected_end_date)
        except ValueError:
            flash("Invalid report date range selected.", "danger")
            return redirect(url_for("admin_reports"))
    elif selected_start_date or selected_end_date:
        single_date = selected_start_date or selected_end_date
        try:
            single_date, _ = normalize_date_range(single_date, single_date)
        except ValueError:
            flash("Invalid report date selected.", "danger")
            return redirect(url_for("admin_reports"))
        selected_start_date = single_date
        selected_end_date = single_date
    selected_month, selected_year = parse_month_year(
        request.args.get("month", "").strip(),
        request.args.get("year", "").strip(),
    )
    report_rows = []
    employees = query_db(
        """
        SELECT id, employee_id, full_name, department, monthly_salary
        FROM employees
        WHERE status = 'Active'
        ORDER BY full_name
        """
    )
    for employee in employees:
        if selected_start_date or selected_end_date:
            report_data = calculate_leave_and_salary_cut_range(
                employee["id"],
                selected_start_date,
                selected_end_date,
            )
            period_label = f"{selected_start_date} to {selected_end_date}"
        else:
            report_data = calculate_leave_and_salary_cut(employee["id"], selected_month, selected_year)
            upsert_monthly_salary_report(employee["id"], selected_month, selected_year, report_data)
            period_label = f"{calendar.month_name[selected_month]} {selected_year}"
        report_rows.append(
            {
                "employee_id": employee["employee_id"],
                "employee_name": employee["full_name"],
                "department": employee["department"],
                "month_label": period_label,
                **report_data,
            }
        )

    if request.args.get("export") == "excel":
        if selected_start_date or selected_end_date:
            content, mimetype, filename = generate_attendance_export_range(
                selected_start_date,
                selected_end_date,
                "excel",
            )
        else:
            content, mimetype, filename = generate_attendance_export(
                selected_month,
                selected_year,
                "excel",
            )
        return Response(
            content,
            mimetype=mimetype,
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )

    attendance_summary = report_rows
    task_summary = query_db(
        """
        SELECT status, COUNT(*) AS total
        FROM tasks
        GROUP BY status
        """
    )
    stock_summary = query_db(
        """
        SELECT category, SUM(quantity) AS total_quantity
        FROM stock
        GROUP BY category
        ORDER BY total_quantity DESC
        """
    )
    return render_template(
        "admin/reports.html",
        attendance_summary=attendance_summary,
        task_summary=task_summary,
        stock_summary=stock_summary,
        report_rows=report_rows,
        selected_month=selected_month,
        selected_year=selected_year,
        selected_start_date=selected_start_date,
        selected_end_date=selected_end_date,
        month_options=list(enumerate(calendar.month_name))[1:],
    )


@app.route("/employee/dashboard")
@employee_required
def employee_dashboard():
    employee = query_db("SELECT * FROM employees WHERE id = ?", (session["user_id"],), one=True)
    today = ist_today().isoformat()
    attendance_today = query_db(
        "SELECT * FROM attendance WHERE employee_id = ? AND date = ?",
        (session["user_id"], today),
        one=True,
    )
    if attendance_today:
        attendance_today = dict(attendance_today)
        attendance_today["status_label"] = get_attendance_status_label(attendance_today)
        attendance_today["status_code"] = get_attendance_status_code(attendance_today)
        attendance_today["status_badge"] = get_attendance_badge_class(attendance_today["status_label"])
    tasks = query_db(
        "SELECT * FROM tasks WHERE assigned_to = ? ORDER BY due_date ASC, updated_at DESC",
        (session["user_id"],),
    )
    current_month, current_year = today.split("-")[1], today.split("-")[0]
    month_summary = calculate_leave_and_salary_cut(session["user_id"], int(current_month), int(current_year))
    attendance_status = get_attendance_status_label(attendance_today) if attendance_today else "Pending"
    pending_attendance = not attendance_today or not attendance_today["clock_out_time"]
    alerts = []
    if pending_attendance:
        alerts.append("Attendance action pending for today.")
    pending_leave = query_db(
        "SELECT COUNT(*) AS count FROM leave_requests WHERE employee_id = ? AND status = 'Pending'",
        (session["user_id"],),
        one=True,
    )["count"]
    if pending_leave:
        alerts.append(f"{pending_leave} leave request(s) are awaiting admin approval.")
    for task in tasks:
        if task["status"] != "Completed" and task["due_date"] <= today:
            alerts.append(f"Task '{task['title']}' is due.")
    if tasks:
        alerts.append("Check newly assigned tasks and keep remarks updated.")
    return render_template(
        "employee/dashboard.html",
        employee=employee,
        attendance_today=attendance_today,
        attendance_status=attendance_status,
        tasks=tasks,
        alerts=alerts,
        today=today,
        month_summary=month_summary,
    )


@app.route("/employee/profile", methods=["GET", "POST"])
@employee_required
def employee_profile():
    employee = query_db("SELECT * FROM employees WHERE id = ?", (session["user_id"],), one=True)
    if request.method == "POST":
        photo_name = save_uploaded_file(request.files.get("profile_photo"), PROFILE_UPLOAD)
        if photo_name:
            execute_db("UPDATE employees SET profile_photo = ? WHERE id = ?", (photo_name, session["user_id"]))
            log_activity("employee", session["user_id"], "Updated profile photo")
            flash("Profile photo updated.", "success")
        else:
            flash("Please upload a valid image file.", "danger")
        return redirect(url_for("employee_profile"))
    return render_template("employee/profile.html", employee=employee)


@app.route("/employee/attendance", methods=["GET", "POST"])
@employee_required
def employee_attendance():
    employee = query_db("SELECT * FROM employees WHERE id = ?", (session["user_id"],), one=True)
    today = ist_today().isoformat()
    attendance_today = query_db(
        "SELECT * FROM attendance WHERE employee_id = ? AND date = ?",
        (session["user_id"], today),
        one=True,
    )

    if request.method == "POST":
        action_type = request.form.get("action_type", "").strip()
        latitude = request.form.get("latitude", "").strip()
        longitude = request.form.get("longitude", "").strip()
        location_text = request.form.get("location_text", "").strip()
        photo_name = save_uploaded_file(request.files.get("photo"), ATTENDANCE_UPLOAD)
        if not latitude or not longitude or not location_text:
            flash("Location details are required to mark attendance.", "danger")
            return redirect(url_for("employee_attendance"))

        now_time = ist_now().strftime("%H:%M:%S")
        current_stamp = ist_now().strftime("%Y-%m-%d %H:%M:%S")
        today_day_name = get_day_name(today)
        if action_type == "morning_clock_in":
            if attendance_today and attendance_today["clock_in_time"]:
                flash("You have already marked morning attendance today.", "warning")
            else:
                if attendance_today:
                    execute_db(
                        """
                        UPDATE attendance
                        SET day_name = ?, morning_status = 'Present', clock_in_time = ?, latitude = ?, longitude = ?,
                            location_text = ?, photo = COALESCE(?, photo), status = 'Present',
                            approval_status = 'Pending', admin_approval_status = 'Pending', is_sunday_work = ?
                        WHERE id = ?
                        """,
                        (
                            today_day_name,
                            now_time,
                            latitude,
                            longitude,
                            location_text,
                            photo_name,
                            1 if is_sunday(today) else 0,
                            attendance_today["id"],
                        ),
                    )
                else:
                    execute_db(
                        """
                        INSERT INTO attendance
                        (
                            employee_id, date, day_name, morning_status, night_status, clock_in_time,
                            latitude, longitude, location_text, photo, status, approval_status,
                            admin_approval_status, is_sunday_work, created_at
                        )
                        VALUES (?, ?, ?, 'Present', 'Not Applicable', ?, ?, ?, ?, ?, 'Present', 'Pending', 'Pending', ?, ?)
                        """,
                        (
                            session["user_id"],
                            today,
                            today_day_name,
                            now_time,
                            latitude,
                            longitude,
                            location_text,
                            photo_name,
                            1 if is_sunday(today) else 0,
                            current_stamp,
                        ),
                    )
                log_activity("employee", session["user_id"], "Marked morning clock-in attendance")
                flash("Morning clock-in captured successfully.", "success")
        elif action_type == "morning_clock_out":
            if not attendance_today or not attendance_today["clock_in_time"]:
                flash("Please complete morning clock-in before clock-out.", "danger")
            elif attendance_today["clock_out_time"]:
                flash("Morning clock-out is already marked for today.", "warning")
            else:
                execute_db(
                    """
                    UPDATE attendance
                    SET clock_out_time = ?, latitude = ?, longitude = ?, location_text = ?,
                        photo = COALESCE(?, photo), approval_status = 'Pending', admin_approval_status = 'Pending'
                    WHERE id = ?
                    """,
                    (now_time, latitude, longitude, location_text, photo_name, attendance_today["id"]),
                )
                log_activity("employee", session["user_id"], "Marked morning clock-out attendance")
                flash("Morning clock-out captured successfully.", "success")
        elif action_type == "night_clock_in":
            if not employee["night_shift_allowed"]:
                flash("Night shift is not enabled for your profile.", "danger")
            elif attendance_today and attendance_today["night_check_in_time"]:
                flash("Night shift clock-in is already marked for today.", "warning")
            elif not attendance_today or attendance_today["morning_status"] != "Present":
                flash("Morning attendance must be marked before starting night shift.", "danger")
            else:
                execute_db(
                    """
                    UPDATE attendance
                    SET night_status = 'Present', night_check_in_time = ?, latitude = ?, longitude = ?,
                        location_text = ?, photo = COALESCE(?, photo), approval_status = 'Pending',
                        admin_approval_status = 'Pending'
                    WHERE id = ?
                    """,
                    (now_time, latitude, longitude, location_text, photo_name, attendance_today["id"]),
                )
                log_activity("employee", session["user_id"], "Marked night shift clock-in")
                flash("Night shift clock-in captured successfully.", "success")
        elif action_type == "night_clock_out":
            if not employee["night_shift_allowed"]:
                flash("Night shift is not enabled for your profile.", "danger")
            elif not attendance_today or not attendance_today["night_check_in_time"]:
                flash("Please mark night shift clock-in first.", "danger")
            elif attendance_today["night_check_out_time"]:
                flash("Night shift clock-out is already marked for today.", "warning")
            else:
                execute_db(
                    """
                    UPDATE attendance
                    SET night_check_out_time = ?, latitude = ?, longitude = ?, location_text = ?,
                        photo = COALESCE(?, photo), approval_status = 'Pending', admin_approval_status = 'Pending'
                    WHERE id = ?
                    """,
                    (now_time, latitude, longitude, location_text, photo_name, attendance_today["id"]),
                )
                log_activity("employee", session["user_id"], "Marked night shift clock-out")
                flash("Night shift clock-out captured successfully.", "success")
        else:
            flash("Invalid attendance action.", "danger")
        return redirect(url_for("employee_attendance"))

    attendance_history = [dict(row) for row in query_db(
        "SELECT * FROM attendance WHERE employee_id = ? ORDER BY date DESC, created_at DESC",
        (session["user_id"],),
    )]
    for row in attendance_history:
        row["status_label"] = get_attendance_status_label(row)
        row["status_code"] = get_attendance_status_code(row)
        row["status_badge"] = get_attendance_badge_class(row["status_label"])
    month = today.month if isinstance(today, date) else int(today.split("-")[1])
    year = today.year if isinstance(today, date) else int(today.split("-")[0])
    monthly_summary = calculate_leave_and_salary_cut(session["user_id"], month, year)
    compensation_balance = get_employee_compensation_balance(session["user_id"], month, year)
    return render_template(
        "employee/attendance.html",
        employee=employee,
        attendance_today=attendance_today,
        attendance_history=attendance_history,
        today=today,
        monthly_summary=monthly_summary,
        compensation_balance=compensation_balance,
        night_shift_allowed=bool(employee["night_shift_allowed"]),
        current_ist_display=ist_now().strftime("%d %b %Y, %I:%M %p IST"),
    )


@app.route("/employee/leave", methods=["GET", "POST"])
@employee_required
def employee_leave():
    employee = query_db("SELECT * FROM employees WHERE id = ?", (session["user_id"],), one=True)
    today = ist_today().isoformat()
    if request.method == "POST":
        leave_date = request.form.get("leave_date", "").strip()
        leave_reason = request.form.get("leave_reason", "").strip()
        leave_type = request.form.get("leave_type", "").strip()
        leave_remarks = request.form.get("leave_remarks", "").strip()
        if not leave_date or not leave_reason or leave_type not in LEAVE_TYPE_OPTIONS:
            flash("Leave date, reason, and valid leave type are required.", "danger")
            return redirect(url_for("employee_leave"))
        if leave_date < today:
            flash("Leave can only be requested for today or future dates.", "danger")
            return redirect(url_for("employee_leave"))
        if get_day_name(leave_date) == "Sunday":
            flash("Sunday is a holiday and does not need a leave request.", "warning")
            return redirect(url_for("employee_leave"))
        existing_request = query_db(
            "SELECT id FROM leave_requests WHERE employee_id = ? AND leave_date = ? AND status = 'Pending'",
            (session["user_id"], leave_date),
            one=True,
        )
        if existing_request:
            flash("A leave request for that date is already pending.", "warning")
            return redirect(url_for("employee_leave"))
        execute_db(
            """
            INSERT INTO leave_requests (employee_id, leave_date, reason, leave_type, remarks, status, created_at)
            VALUES (?, ?, ?, ?, ?, 'Pending', ?)
            """,
            (
                session["user_id"],
                leave_date,
                leave_reason,
                leave_type,
                leave_remarks or None,
                ist_now().strftime("%Y-%m-%d %H:%M:%S"),
            ),
        )
        log_activity("employee", session["user_id"], f"Requested leave for {leave_date}")
        flash("Leave request submitted for admin approval.", "success")
        return redirect(url_for("employee_leave"))

    leave_requests = query_db(
        "SELECT * FROM leave_requests WHERE employee_id = ? ORDER BY leave_date DESC, created_at DESC",
        (session["user_id"],),
    )
    month_summary = calculate_leave_and_salary_cut(session["user_id"], ist_today().month, ist_today().year)
    pending_count = sum(1 for row in leave_requests if row["status"] == "Pending")
    approved_count = sum(1 for row in leave_requests if row["status"] == "Approved")
    rejected_count = sum(1 for row in leave_requests if row["status"] == "Rejected")
    return render_template(
        "employee/leave.html",
        employee=employee,
        leave_requests=leave_requests,
        month_summary=month_summary,
        compensation_balance=get_employee_compensation_balance(session["user_id"], ist_today().month, ist_today().year),
        pending_count=pending_count,
        approved_count=approved_count,
        rejected_count=rejected_count,
        today=today,
    )


@app.route("/employee/tasks")
@employee_required
def employee_tasks():
    tasks = query_db(
        "SELECT * FROM tasks WHERE assigned_to = ? ORDER BY due_date ASC, updated_at DESC",
        (session["user_id"],),
    )
    return render_template("employee/tasks.html", tasks=tasks, today=ist_today().isoformat())


@app.route("/employee/tasks/update/<int:id>", methods=["POST"])
@employee_required
def update_employee_task(id):
    task = query_db(
        "SELECT * FROM tasks WHERE id = ? AND assigned_to = ?",
        (id, session["user_id"]),
        one=True,
    )
    if not task:
        flash("Task not found.", "danger")
        return redirect(url_for("employee_tasks"))

    status = request.form.get("status", "").strip()
    remarks = request.form.get("remarks", "").strip()
    if status not in {"Pending", "In Progress", "Completed"}:
        flash("Invalid task status.", "danger")
        return redirect(url_for("employee_tasks"))

    execute_db(
        "UPDATE tasks SET status = ?, remarks = ?, updated_at = ? WHERE id = ?",
        (status, remarks, ist_now().strftime("%Y-%m-%d %H:%M:%S"), id),
    )
    log_activity("employee", session["user_id"], f"Updated task '{task['title']}' to {status}")
    flash("Task updated successfully.", "success")
    return redirect(url_for("employee_tasks"))


init_db()


if __name__ == "__main__":
    app.run(debug=True)
