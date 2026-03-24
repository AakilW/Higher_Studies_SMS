import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime
import hashlib
import plotly.express as px
from io import BytesIO
from reportlab.platypus import SimpleDocTemplate, Table
from reportlab.lib import colors

# -----------------------------
# CONFIG
# -----------------------------
st.set_page_config(page_title="Student Dashboard", layout="wide")

# -----------------------------
# DATABASE
# -----------------------------
conn = sqlite3.connect("students.db", check_same_thread=False)
c = conn.cursor()

def create_tables():
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY,
            password TEXT,
            role TEXT
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name TEXT,
            institution TEXT,
            course TEXT,
            contact TEXT,
            start_date TEXT,
            end_date TEXT
        )
    ''')
    conn.commit()

def migrate_db():
    """Ensure missing columns are added safely"""
    c.execute("PRAGMA table_info(students)")
    columns = [col[1] for col in c.fetchall()]

    if "Halka_Mahalla" not in columns:
        c.execute("ALTER TABLE students ADD COLUMN Halka_Mahalla TEXT")
    
    conn.commit()

create_tables()
migrate_db()

# -----------------------------
# AUTH
# -----------------------------
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def create_default_user():
    c.execute("SELECT * FROM users WHERE username = ?", ("admin",))
    if not c.fetchone():
        c.execute("INSERT INTO users VALUES (?, ?, ?)",
                  ("admin", hash_password("admin123"), "admin"))
        conn.commit()

create_default_user()

def login(username, password):
    c.execute("SELECT * FROM users WHERE username = ?", (username,))
    user = c.fetchone()
    if user and user[1] == hash_password(password):
        return {"username": user[0], "role": user[2]}
    return None

# -----------------------------
# HELPERS
# -----------------------------
def get_status(start, end):
    today = datetime.today().date()
    start = datetime.strptime(start, "%Y-%m-%d").date()
    end = datetime.strptime(end, "%Y-%m-%d").date()

    if end < today:
        return "Completed"
    elif start > today:
        return "Upcoming"
    else:
        return "Active"

def extract_halka(x):
    if isinstance(x, str):
        if x.startswith("PKT"):
            return "PKT"
        elif x.startswith("KM"):
            return "KM"
        elif x.startswith("NT"):
            return "NT"
    return "Other"

def get_students():
    df = pd.read_sql_query("SELECT * FROM students", conn)
    if not df.empty:
        df["status"] = df.apply(lambda x: get_status(x["start_date"], x["end_date"]), axis=1)
        df["Halka"] = df["Halka_Mahalla"].fillna("").apply(extract_halka)
    return df

def add_student(data):
    c.execute('''
        INSERT INTO students (full_name, institution, course, contact, Halka_Mahalla, start_date, end_date)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', data)
    conn.commit()

def delete_student(student_id):
    c.execute("DELETE FROM students WHERE id = ?", (student_id,))
    conn.commit()

# -----------------------------
# SESSION
# -----------------------------
if "user" not in st.session_state:
    st.session_state.user = None

# -----------------------------
# LOGIN
# -----------------------------
if not st.session_state.user:
    st.title("🔐 Login")

    username = st.text_input("Username")
    password = st.text_input("Password", type="password")

    if st.button("Login"):
        user = login(username, password)
        if user:
            st.session_state.user = user
            st.rerun()
        else:
            st.error("Invalid credentials")

    st.stop()

# -----------------------------
# SIDEBAR
# -----------------------------
st.sidebar.title("📊 Navigation")
page = st.sidebar.radio("Go to", [
    "Dashboard",
    "Add Student",
    "Manage Students",
    "Notifications"
])

if st.sidebar.button("Logout"):
    st.session_state.user = None
    st.rerun()

# -----------------------------
# DASHBOARD
# -----------------------------
if page == "Dashboard":
    st.title("📊 Student Management Dashboard")

    df = get_students()

    if df.empty:
        st.info("No data available")
    else:
        total = len(df)
        active = len(df[df["status"] == "Active"])
        ending_soon = len(df[
            (pd.to_datetime(df["end_date"]) - pd.Timestamp.today()).dt.days <= 7
        ])

        col1, col2, col3 = st.columns(3)
        col1.metric("Total Students", total)
        col2.metric("Active", active)
        col3.metric("Ending Soon", ending_soon)

        col1, col2 = st.columns(2)

        with col1:
            st.subheader("Course Distribution")
            st.plotly_chart(px.pie(df, names="course", hole=0.4), use_container_width=True)

        with col2:
            st.subheader("Halka Distribution")
            st.plotly_chart(px.pie(df, names="Halka", hole=0.4), use_container_width=True)

        st.subheader("Students Trend")
        df["start_date"] = pd.to_datetime(df["start_date"])
        trend = df.groupby(df["start_date"].dt.to_period("M")).size().reset_index(name="count")
        trend["start_date"] = trend["start_date"].astype(str)

        st.plotly_chart(px.line(trend, x="start_date", y="count", markers=True),
                        use_container_width=True)

        # EXPORT
        st.subheader("Export Data")

        def to_excel(df):
            output = BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df.to_excel(writer, index=False)
            return output.getvalue()

        def to_pdf(df):
            buffer = BytesIO()
            doc = SimpleDocTemplate(buffer)
            table = Table([df.columns.tolist()] + df.values.tolist())
            table.setStyle([("GRID", (0, 0), (-1, -1), 1, colors.black)])
            doc.build([table])
            return buffer.getvalue()

        col1, col2 = st.columns(2)
        col1.download_button("Download Excel", to_excel(df), "students.xlsx")
        col2.download_button("Download PDF", to_pdf(df), "students.pdf")

# -----------------------------
# ADD STUDENT
# -----------------------------
elif page == "Add Student":
    st.title("➕ Add Student")

    with st.form("form"):
        name = st.text_input("Full Name")
        institution = st.text_input("Institution")
        course = st.text_input("Course")
        contact = st.text_input("Contact")

        Halka_Mahalla = st.text_input("Halka_Mahalla (PKT/KM/NT - Name)")

        if Halka_Mahalla and not Halka_Mahalla.startswith(("PKT", "KM", "NT")):
            st.warning("Use PKT / KM / NT format")

        col1, col2 = st.columns(2)
        start = col1.date_input("Start Date")
        end = col2.date_input("End Date")

        submit = st.form_submit_button("Add")

        if submit:
            if end < start:
                st.error("Invalid dates")
            else:
                add_student((
                    name, institution, course, contact, Halka_Mahalla,
                    start.strftime("%Y-%m-%d"),
                    end.strftime("%Y-%m-%d")
                ))
                st.success("Added")

# -----------------------------
# MANAGE
# -----------------------------
elif page == "Manage Students":
    st.title("Manage Students")

    df = get_students()

    if df.empty:
        st.warning("No data")
    else:
        st.dataframe(df, use_container_width=True)

        delete_id = st.number_input("ID to delete", step=1)
        if st.button("Delete"):
            delete_student(delete_id)
            st.success("Deleted")
            st.rerun()

        st.download_button("Download CSV", df.to_csv(index=False), "students.csv")

# -----------------------------
# NOTIFICATIONS
# -----------------------------
elif page == "Notifications":
    st.title("Notifications")

    df = get_students()

    if not df.empty:
        df["end_date"] = pd.to_datetime(df["end_date"])
        soon = df[(df["end_date"] - pd.Timestamp.today()).dt.days <= 7]

        if soon.empty:
            st.success("No alerts")
        else:
            st.warning("Ending Soon")
            st.dataframe(soon)

# -----------------------------
# DARK MODE
# -----------------------------
if st.sidebar.toggle("🌙 Dark Mode"):
    st.markdown(
        "<style>body { background-color: #0E1117; color: white; }</style>",
        unsafe_allow_html=True
    )