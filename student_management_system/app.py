from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import mysql.connector
from pathlib import Path
from dotenv import load_dotenv
import os

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY")
DB_PATH = Path(__file__).with_name("school.db")

def db():
    con = mysql.connector.connect(
        host=os.getenv("DB_HOST"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        database=os.getenv("DB_NAME")
    )
    return con

def init_db():
    con = db()
    cursor = con.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTO_INCREMENT,
            username varchar(100) UNIQUE NOT NULL,
            password_hash TEXT NOT NULL)""")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY AUTO_INCREMENT,
            reg_no varchar(50) UNIQUE NOT NULL,
            first_name varchar(100) NOT NULL,
            last_name varchar(100) NOT NULL,
            gender varchar(20),
            course varchar(100),
            phone varchar(20),
            email varchar(100)
       )""" )
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTO_INCREMENT,
            student_id INTEGER NOT NULL,
            amount REAL NOT NULL CHECK(amount > 0),
            payment_date varchar(100) NOT NULL,
            purpose varchar(100) NOT NULL,
            reference varchar(100),
            FOREIGN KEY(student_id) REFERENCES students(id) ON DELETE CASCADE
        )""")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS marks (
            id INTEGER PRIMARY KEY AUTO_INCREMENT,
            student_id INTEGER NOT NULL, 
            subject varchar(100) NOT NULL,
            mark REAL NOT NULL CHECK(mark >= 0 AND mark <= 100),
            term TEXT,
            FOREIGN KEY(student_id) REFERENCES students(id) ON DELETE CASCADE
        )""")
    con.commit()
    cursor.close()

def login_required(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return fn(*args, **kwargs)
    return wrapped

@app.route("/")
def home():
    return redirect(url_for("dashboard") if "user_id" in session else url_for("login"))

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        if len(username) < 3 or len(password) < 8:
            flash("Username must be at least 3 characters and password at least 8 characters.", "error")
        else:
            try:
                con =db()
                cursor = con.cursor()
                cursor.execute("INSERT INTO users(username, password_hash) VALUES (%s, %s)",
                            (username, generate_password_hash(password)))
                con.commit()
                flash("Account created. Please log in.", "success")
                return redirect(url_for("login"))
            except mysql.connector.IntegrityError:
                flash("That username is already registered.", "error")
    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        con = db()
        cursor = con.cursor(dictionary=True)
        cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
        user=cursor.fetchone()

        if user == None:
            flash("Incorrect username or password.", "error")
        if user != None and check_password_hash(user["password_hash"], password):
            session.clear()
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            return redirect(url_for("dashboard"))
        flash("Incorrect username or password.", "error")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    flash("You have logged out.", "success")
    return redirect(url_for("login"))

@app.route("/dashboard")
@login_required
def dashboard():
    con =db()
    cursor= con.cursor()
    try:
        counts = {
            "students": cursor.execute("SELECT COUNT(*) FROM students").fetchone()[0],
            "payments": cursor.execute("SELECT COUNT(*) FROM payments").fetchone()[0],
            "marks": cursor.execute("SELECT COUNT(*) FROM marks").fetchone()[0],
            "total": cursor.execute("SELECT COALESCE(SUM(amount),0) FROM payments").fetchone()[0]
            }
    except TypeError,AttributeError:
        counts = {
            "students": 0,
            "payments": 0,
            "marks": 0,
            "total": 0
        }
    try:
        recent = cursor.execute("""SELECT id, reg_no, first_name, last_name, course
                                FROM students ORDER BY id DESC LIMIT 5""").fetchall()
        return render_template("dashboard.html", counts=counts, recent=recent)
    except Exception as e:
        print(e)
        return render_template("dashboard.html", counts=counts, recent=[])
    

@app.route("/students")
@login_required
def students():
    con = db()
    cursor = con.cursor()
    try:
        rows = cursor.execute("SELECT * FROM students ORDER BY id DESC").fetchall()
    except Exception as e:
        print(e)
        rows = []
    return render_template("students.html", students=rows)

@app.route("/students/add", methods=["GET", "POST"])
@app.route("/students/<int:student_id>/edit", methods=["GET", "POST"])
@login_required
def student_form(student_id=None):
    con = db()
    student = con.execute("SELECT * FROM students WHERE id=?", (student_id,)).fetchone() if student_id else None
    if student_id and not student:
        flash("Student not found.", "error")
        return redirect(url_for("students"))
    if request.method == "POST":
            values = tuple(request.form.get(k, "").strip() for k in
                           ("reg_no", "first_name", "last_name", "gender", "course", "phone", "email"))
            if not all(values[:3]):
                flash("Registration number, first name and last name are required.", "error")
            else:
                try:
                    if student_id:
                        con.execute("""UPDATE students SET reg_no=%s, first_name=%s, last_name=%s, gender=%s,
                                    course=%s, phone=%s, email=%s WHERE id=%s""", values + (student_id,))
                        flash("Student details updated.", "success")
                    else:
                        con.execute("""INSERT INTO students(reg_no, first_name, last_name, gender, course, phone, email)
                                    VALUES(%s,%s,%s,%s,%s,%s,%s)""", values)
                        flash("Student registered successfully.", "success")
                    return redirect(url_for("students"))
                except mysql.connector.IntegrityError:
                    flash("That registration number already exists.", "error")
    return render_template("student_form.html", student=student)

@app.post("/students/<int:student_id>/delete")
@login_required
def delete_student(student_id):
    con = db()
    con.execute("DELETE FROM students WHERE id=%s", (student_id,))
    flash("Student and their related records deleted.", "success")
    return redirect(url_for("students"))

@app.route("/payments")
@login_required
def payments():
    con = db()
    cursor=con.cursor()
    try:
        rows = cursor.execute("""SELECT p.*, s.reg_no, s.first_name, s.last_name
                          FROM payments p JOIN students s ON s.id=p.student_id
                          ORDER BY p.payment_date DESC, p.id DESC""").fetchall()
        students_list = cursor.execute("SELECT id, reg_no, first_name, last_name FROM students ORDER BY first_name").fetchall()
        return render_template("payments.html", payments=rows, students=students_list)
    except Exception:
        return render_template("payments.html", payments=[],students=[])

@app.route("/payments/add", methods=["POST"])
@app.route("/payments/<int:payment_id>/edit", methods=["POST"])
@login_required
def save_payment(payment_id=None):
    student_id = request.form.get("student_id", type=int)
    amount = request.form.get("amount", type=float)
    payment_date = request.form.get("payment_date", "").strip()
    purpose = request.form.get("purpose", "").strip()
    reference = request.form.get("reference", "").strip()
    if not student_id or not amount or amount <= 0 or not payment_date or not purpose:
        flash("Enter a student, positive amount, date and payment purpose.", "error")
        return redirect(url_for("payments"))
    con = db()
    if payment_id:
            con.execute("""UPDATE payments SET student_id=%s, amount=%s, payment_date=%s, purpose=%s, reference=%s
                           WHERE id=%s""", (student_id, amount, payment_date, purpose, reference, payment_id))
            flash("Payment updated.", "success")
    else:
            con.execute("""INSERT INTO payments(student_id, amount, payment_date, purpose, reference)
                           VALUES(%s,%s,%s,%s,%s)""", (student_id, amount, payment_date, purpose, reference))
            flash("Payment recorded.", "success")
    return redirect(url_for("payments"))

@app.post("/payments/<int:payment_id>/delete")
@login_required
def delete_payment(payment_id):
    con = db()
    con.execute("DELETE FROM payments WHERE id=%s", (payment_id,))
    flash("Payment deleted.", "success")
    return redirect(url_for("payments"))

@app.route("/marks")
@login_required
def marks():
    con = db()
    cursor = con.cursor()
    try:
        rows = cursor.execute("""SELECT m.*, s.reg_no, s.first_name, s.last_name
                          FROM marks m JOIN students s ON s.id=m.student_id
                          ORDER BY m.id DESC""").fetchall()
    except Exception as e:
        print(e)
        rows = []
    try:
        students_list = con.execute("SELECT id, reg_no, first_name, last_name FROM students ORDER BY first_name").fetchall()
    except Exception as e:
        print(e)
        students_list = []
    return render_template("marks.html", marks=rows, students=students_list)

@app.route("/marks/add", methods=["POST"])
@app.route("/marks/<int:mark_id>/edit", methods=["POST"])
@login_required
def save_mark(mark_id=None):
    student_id = request.form.get("student_id", type=int)
    subject = request.form.get("subject", "").strip()
    mark = request.form.get("mark", type=float)
    term = request.form.get("term", "").strip()
    if not student_id or not subject or mark is None or not 0 <= mark <= 100:
        flash("Choose a student and subject, and enter a mark from 0 to 100.", "error")
        return redirect(url_for("marks"))
    con =db()
    if mark_id:
            con.execute("UPDATE marks SET student_id=%s, subject=%s, mark=%s, term=%s WHERE id=%s",
                        (student_id, subject, mark, term, mark_id))
            flash("Student mark updated.", "success")
    else:
            con.execute("INSERT INTO marks(student_id, subject, mark, term) VALUES(%s,%s,%s,%s)",
                        (student_id, subject, mark, term))
            flash("Student mark saved.", "success")
    return redirect(url_for("marks"))

@app.post("/marks/<int:mark_id>/delete")
@login_required
def delete_mark(mark_id):
    con = db()
    con.execute("DELETE FROM marks WHERE id=%s", (mark_id,))
    flash("Mark deleted.", "success")
    return redirect(url_for("marks"))

if __name__ == "__main__":
    init_db()
    app.run(debug=True)
