from flask import Flask, render_template, request, redirect, url_for, session, flash
import sqlite3
import pandas as pd
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import requests
from bs4 import BeautifulSoup

app = Flask(__name__)
app.secret_key = 'your_secret_key'  # Required for session management

# Initialize DB
def init_db():
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
    ''')
    conn.commit()
    conn.close()

# @app.route('/')
# def home():
#     return redirect(url_for('login'))

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form['username']
        password = generate_password_hash(request.form['password'])

        try:
            conn = sqlite3.connect('users.db')
            cursor = conn.cursor()
            cursor.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, password))
            conn.commit()
            flash('Signup successful. Please login.', 'success')
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            flash('Username already exists.', 'danger')
        finally:
            conn.close()
    return render_template('signup.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        conn = sqlite3.connect('users.db')
        cursor = conn.cursor()
        cursor.execute("SELECT password FROM users WHERE username=?", (username,))
        result = cursor.fetchone()
        conn.close()

        if result and check_password_hash(result[0], password):
            session['username'] = username
            return redirect(url_for('home'))
        else:
            flash('Invalid credentials', 'danger')
    return render_template('login.html')

@app.route('/dashboard')
def dashboard():
    if 'username' in session:
        return render_template('dashboard.html', username=session['username'])
    return redirect(url_for('login'))

@app.route('/logout')
def logout():
    session.pop('username', None)
    flash('Logged out successfully', 'info')
    return redirect(url_for('login'))


DB_FILE = 'notices.db'
URL = 'https://jcboseust.ac.in/notice_page?type=examination'

def fetch_and_store_notices():
    response = requests.get(URL)
    if response.status_code != 200:
        print(f"❌ Failed to fetch page. Status code: {response.status_code}")
        return

    soup = BeautifulSoup(response.text, 'html.parser')
    rows = soup.find_all('tr')

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS notices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            link TEXT NOT NULL,
            created_at DATE NOT NULL
        )
    ''')

    added = 0

    for row in rows:
        a_tag = row.find('a')
        if a_tag:
            title = a_tag.text.strip()
            link = a_tag['href'].strip()
            if not link.startswith('http'):
                link = 'https://jcboseust.ac.in/' + link.lstrip('/')

            date_td = row.find_all('td')
            if len(date_td) >= 2:
                date_text = date_td[-1].text.strip()
                try:
                    created_at = datetime.strptime(date_text, "%d-%m-%Y").date()
                except ValueError:
                    created_at = datetime.today().date()
            else:
                created_at = datetime.today().date()

            # Check for duplicates before inserting
            cursor.execute("SELECT COUNT(*) FROM notices WHERE title=? AND link=?", (title, link))
            if cursor.fetchone()[0] == 0:
                cursor.execute(
                    "INSERT INTO notices (title, link, created_at) VALUES (?, ?, ?)",
                    (title, link, created_at)
                )
                added += 1

    conn.commit()
    conn.close()
    print(f"\n✅ DONE! Added {added} new notices to '{DB_FILE}'!\n")


@app.route('/exam')
def show_notices():
    fetch_and_store_notices()

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT title, link, created_at FROM notices ORDER BY created_at DESC")
    rows = cursor.fetchall()
    conn.close()

    today = datetime.now().date()
    notices = []
    for title, link, created_at in rows:
        created_at_date = datetime.strptime(created_at, '%Y-%m-%d').date()
        is_new = (today - created_at_date).days <= 20
        notices.append({
            'title': title,
            'link': link,
            'created_at': created_at,
            'is_new': is_new
        })

    return render_template('exam.html', notices=notices)

# Load and clean CSV
df_predict = pd.read_csv("P.csv")
df_predict["Category"] = df_predict["Category"].str.strip().str.upper()
df_predict["Gender"] = df_predict["Gender"].str.strip().str.title()
df_predict["Branch"] = df_predict["Branch"].str.strip()
df_predict["Year"] = df_predict["Year"].astype(int)

@app.route("/rank-prediction")
def rank():
    return render_template("rank-prediction.html")

@app.route("/predict", methods=["POST"])
def predict():
    user_rank = int(request.form["rank"])
    gender = request.form["gender"].title()
    category = request.form["category"].upper()

    # Filter only 2024 records from df_predict
    df_2024 = df_predict[(df_predict["Year"] == 2024) & 
                         (df_predict["Gender"] == gender) & 
                         (df_predict["Category"] == category)]

    # Eligible branches where closing rank >= user rank
    eligible_branches = df_2024[df_2024["Closing Rank"] >= user_rank]["Branch"].unique()
    eligible_branches = sorted(eligible_branches)

    return render_template("result.html", branches=eligible_branches, user_rank=user_rank)


# Load Excel file
df = pd.read_excel("Formatted_Rank_Data.xlsx")
df['Branch'] = df['Branch'].astype(str).str.strip()
df['Category'] = df['Category'].astype(str).str.strip()

# All branches to show in dropdown, even if not in Excel
branches = [
    "Computer Engg.", "Computer Engg. (Hindi Medium)", "Computer Engg. (with specialization in Data Science)",
    "Electrical Engg.", "Electronics & Communication", "Information Technology", "Electronics and Computer Engg.",
    "Electronics Engg. (Specialization in IOT)", "Mechanical Engg.", "Mechanical Engg. (Hindi Medium)", "Robotics and Artificial Intelligence",
    "Civil", "Environmental Engg."
]

# Get unique categories and genders from the file
categories = sorted(df['Category'].dropna().unique())
genders = sorted(df['Gender'].dropna().unique())

@app.route('/cutoff2025', methods=['GET', 'POST'])
def cutoff2025():
    # Load the 2025 data that includes multiple rounds
    df_2025 = pd.read_excel("Formatted_Rank_Data_2025_Round1.xlsx")

    # Strip and clean all relevant columns
    df_2025['Round'] = df_2025['Round'].astype(str).str.strip()
    df_2025['Branch'] = df_2025['Branch'].astype(str).str.strip()
    df_2025['Category'] = df_2025['Category'].astype(str).str.strip()
    df_2025['Gender'] = df_2025['Gender'].astype(str).str.strip()

    # Get form selections
    selected_round = request.form.get('round') if request.method == 'POST' else None
    selected_branch = request.form.get('branch') if request.method == 'POST' else None
    selected_category = request.form.get('category') if request.method == 'POST' else None
    selected_gender = request.form.get('gender') if request.method == 'POST' else None

    # Apply filters
    filtered_df = df_2025.copy()
    if selected_round:
        filtered_df = filtered_df[filtered_df['Round'].str.lower() == selected_round.lower()]
    if selected_branch:
        filtered_df = filtered_df[filtered_df['Branch'].str.lower() == selected_branch.lower()]
    if selected_category:
        filtered_df = filtered_df[filtered_df['Category'].str.lower() == selected_category.lower()]
    if selected_gender:
        filtered_df = filtered_df[filtered_df['Gender'].str.lower() == selected_gender.lower()]

    # Convert filtered results to list of dicts
    filtered_data = filtered_df.to_dict(orient='records') if request.method == 'POST' else []

    # Render the template with all necessary dropdown values and data
    return render_template(
        'index_2025.html',
        rounds=sorted(df_2025['Round'].dropna().unique()),
        branches=sorted(df_2025['Branch'].dropna().unique()),
        categories=sorted(df_2025['Category'].dropna().unique()),
        genders=sorted(df_2025['Gender'].dropna().unique()),
        data=filtered_data,
        selected_round=selected_round,
        selected_branch=selected_branch,
        selected_category=selected_category,
        selected_gender=selected_gender
    )



@app.route('/cutoff2024', methods=['GET', 'POST'])
def cutoff2024():
    selected_branch = None
    selected_category = None
    selected_gender = None
    filtered_data = []

    if request.method == 'POST':
        selected_branch = request.form.get('branch')
        selected_category = request.form.get('category')
        selected_gender = request.form.get('gender')

        filtered_df = df.copy()

        if selected_branch:
            filtered_df = filtered_df[filtered_df['Branch'].str.lower() == selected_branch.lower()]
        if selected_category:
            filtered_df = filtered_df[filtered_df['Category'].str.lower() == selected_category.lower()]
        if selected_gender:
            filtered_df = filtered_df[filtered_df['Gender'].str.lower() == selected_gender.lower()]

        filtered_data = filtered_df.to_dict(orient='records')

    return render_template(
        'index_2024.html',  # ✅ Changed this line
        branches=branches,
        categories=categories,
        genders=genders,
        data=filtered_data,
        selected_branch=selected_branch,
        selected_category=selected_category,
        selected_gender=selected_gender
    )




@app.route('/cutoff2023', methods=['GET', 'POST'])
def cutoff2023():
    # Load the 2023 data from Excel
    df_2023 = pd.read_excel("Formatted_Rank_Data_2023.xlsx")
    df_2023['Branch'] = df_2023['Branch'].astype(str).str.strip()
    df_2023['Category'] = df_2023['Category'].astype(str).str.strip()
    df_2023['Gender'] = df_2023['Gender'].astype(str).str.strip()

    # Get form selections
    selected_branch = request.form.get('branch') if request.method == 'POST' else None
    selected_category = request.form.get('category') if request.method == 'POST' else None
    selected_gender = request.form.get('gender') if request.method == 'POST' else None

    # Apply filters
    filtered_df = df_2023.copy()
    if selected_branch:
        filtered_df = filtered_df[filtered_df['Branch'].str.lower() == selected_branch.lower()]
    if selected_category:
        filtered_df = filtered_df[filtered_df['Category'].str.lower() == selected_category.lower()]
    if selected_gender:
        filtered_df = filtered_df[filtered_df['Gender'].str.lower() == selected_gender.lower()]

    # Prepare data for the template
    filtered_data = filtered_df.to_dict(orient='records') if request.method == 'POST' else []

    return render_template(
        'index_2023.html',
        branches=sorted(df_2023['Branch'].dropna().unique()),
        categories=sorted(df_2023['Category'].dropna().unique()),
        genders=sorted(df_2023['Gender'].dropna().unique()),
        data=filtered_data,
        selected_branch=selected_branch,
        selected_category=selected_category,
        selected_gender=selected_gender
    )
@app.route('/')
def home():
    return render_template('index.html') 

@app.route('/placement2024')
def placement2024():
    return render_template('2023-2024.html')  # ✅ This file must be in the templates/ folder

@app.route('/placement2023')
def placement2023():
    return render_template('2022-2023.html')  # ✅ This file must be in the templates/ folder

@app.route('/placement2022')
def placement2022():
    return render_template('2021-2022.html')  # ✅ This file must be in the templates/ folder

@app.route('/placement2021')
def placement2021():
    return render_template('2020-2021.html')  # ✅ This file must be in the templates/ folder

@app.route('/placement2020')
def placement2020():
    return render_template('2019-2020.html')  # ✅ This file must be in the templates/ folder

@app.route('/placement2019')
def placement2019():
    return render_template('2018-2019.html')  # ✅ This file must be in the templates/ folder

@app.route('/placement2018')
def placement2018():
    return render_template('2017-2018.html')  # ✅ This file must be in the templates/ folder

@app.route('/placement2017')
def placement2017():
    return render_template('2016-2017.html')  # ✅ This file must be in the templates/ folder

@app.route('/placement2016')
def placement2016():
    return render_template('2015-2016.html')  # ✅ This file must be in the templates/ folder

@app.route('/placement2015')
def placement2015():
    return render_template('2014-2015.html')  # ✅ This file must be in the templates/ folder

@app.route('/syllabus-ECE')
def syllabusECE():
    return render_template('btech-ece-pdf.html')  # ✅ This file must be in the templates/ folder

@app.route('/syllabus-ME')
def syllabusME():
    return render_template('btech-me-pdf.html')  # ✅ This file must be in the templates/ folder

@app.route('/syllabus-CE-AL')
def syllabusCEAL():
    return render_template('btech-ce-al-pdf.html')  # ✅ This file must be in the templates/ folder

@app.route('/syllabus-CE-Data')
def syllabusCEData():
    return render_template('btech-ce-data-pdf.html')  # ✅ This file must be in the templates/ folder

@app.route('/syllabus-CE')
def syllabusCE():
    return render_template('btech-ce-pdf.html')  # ✅ This file must be in the templates/ folder

@app.route('/syllabus-CEHindi')
def syllabusCEHindi():
    return render_template('ce-hindi-syllabus.html')

@app.route('/syllabus-civil')
def syllabusCivil():
    return render_template('btech-civil-pdf.html')  # ✅ This file must be in the templates/ folder

@app.route('/syllabus-EE')
def syllabusEE():
    return render_template('btech-ee-pdf.html')  # ✅ This file must be in the templates/ folder

@app.route('/syllabus-electrical')
def syllabusElectrical():
    return render_template('btech-electrical-pdf.html')  # ✅ This file must be in the templates/ folder

@app.route('/syllabus-ENC')
def syllabusENC():
    return render_template('btech-enc-pdf.html')  # ✅ This file must be in the templates/ folder

@app.route('/syllabus-ENV')
def syllabusENV():
    return render_template('btech-env-pdf.html')  # ✅ This file must be in the templates/ folder

@app.route('/syllabus-IOT')
def syllabusIOT():
    return render_template('btech-iot-pdf.html')  # ✅ This file must be in the templates/ folder

@app.route('/syllabus-IT')
def syllabusIT():
    return render_template('btech-IT-pdf.html')  # ✅ This file must be in the templates/ folder

@app.route('/syllabus-ME(Hindi)')
def syllabusMEHindi():
    return render_template('btech-me(hindi)-pdf.html')  # ✅ This file must be in the templates/ folder

@app.route('/syllabus-RAI')
def syllabusRAI():
    return render_template('btech-RAI-pdf.html')  # ✅ This file must be in the templates/ folder

@app.route('/syllabus')
def syllabus():
    return render_template('syllbus.html')  # ✅ This file must be in the templates/ folder

@app.route('/syllabus-MSC')
def syllabusMSC():
    return render_template('msc-math.html')  # ✅ This file must be in the templates/ folder

@app.route('/syllabus-BSC')
def syllabusBSC():
    return render_template('bsc-math.html')  # ✅ This file must be in the templates/ folder

@app.route('/Msyllabus-CE')
def MsyllabusCE():
    return render_template('mtech-ce-pdf.html')  # ✅ This file must be in the templates/ folder

@app.route('/Msyllabus-CSE')
def MsyllabusCSE():
    return render_template('mtech-cse-pdf.html')  # ✅ This file must be in the templates/ folder

@app.route('/Msyllabus-ECE')
def MsyllabusECE():
    return render_template('mtech-ece-pdf.html')  # ✅ This file must be in the templates/ folder

@app.route('/Msyllabus-EIC')
def MsyllabusEIC():
    return render_template('mtech-eic-pdf.html')  # ✅ This file must be in the templates/ folder

@app.route('/Msyllabus-IT')
def MsyllabusIT():
    return render_template('mtech-IT-pdf.html')  # ✅ This file must be in the templates/ folder

@app.route('/syllabus-MA')
def syllabusMA():
    return render_template('mtech-ma-pdf.html')  # ✅ This file must be in the templates/ folder

@app.route('/Msyllabus-MD')
def MsyllabusMD():
    return render_template('mtech-md-pdf.html')  # ✅ This file must be in the templates/ folder

@app.route('/Msyllabus-ME')
def MsyllabusME():
    return render_template('mtech-me-pdf.html')  # ✅ This file must be in the templates/ folder

@app.route('/Msyllabus-MED')
def MsyllabusMED():
    return render_template('mtech-med-pdf.html')  # ✅ This file must be in the templates/ folder

@app.route('/Msyllabus-MTA')
def MsyllabusMTA():
    return render_template('mtech-mta-pdf.html')  # ✅ This file must be in the templates/ folder

@app.route('/Msyllabus-PS')
def MsyllabusPS():
    return render_template('mtech-ps-pdf.html')  # ✅ This file must be in the templates/ folder

@app.route('/Msyllabus-SE')
def MsyllabusSE():
    return render_template('mtech-se-pdf.html')  # ✅ This file must be in the templates/ folder

@app.route('/Msyllabus-SP')
def MsyllabusSP():
    return render_template('mtech-sp-pdf.html')  # ✅ This file must be in the templates/ folder

@app.route('/Msyllabus-TEM')
def MsyllabusTEM():
    return render_template('mtech-tem-pdf.html')  # ✅ This file must be in the templates/ folder

@app.route('/Msyllabus-VLSI')
def MsyllabusVLSI():
    return render_template('mtech-vlsi-pdf.html')  # ✅ This file must be in the templates/ folder

@app.route('/eligibility')
def eligibility():
    return render_template('eligibility.html')  # ✅ This file must be in the templates/ folder


@app.route('/footer')
def footer():
    return render_template('footer.html')  # ✅ This file must be in the templates/ folder

@app.route('/header')
def header():
    return render_template('header.html') 

@app.route('/seat-matrix')
def seat():
    return render_template('seat-matrix.html')  

@app.route('/girls-hostel')
def girls_hostel():
    return render_template('girls-hostel.html')  



@app.route('/Academic-Calendar')
def Academic_Calendar():
    return render_template('Academic-Calendar.html')  

@app.route('/admission-process')
def admission_process():
    return render_template('admission-process.html')  

@app.route('/all-scholarships')
def all_scholarships():
    return render_template('all-scholarships.html')  

@app.route('/alumni')
def alumni():
    return render_template('Alumni.html')

@app.route('/boys-hostel')
def boys_hostel():
    return render_template('boys-hostel.html')





@app.route('/camparsion')
def camparsion():       
    return render_template('camparsion.html')

@app.route('/CE-overview')
def CE_overview():     
    return render_template('CE-overview.html')

@app.route('/choice-filling')
def choice_filling():
    return render_template('choice-filling.html')

@app.route('/civil-overview')
def civil_overview():   
    return render_template('civil-overview.html')


@app.route('/connectivity')
def connectivity():     
    return render_template('connectivity.html')
@app.route('/cutoff')
def cutoff():
    return render_template('cutoff.html')

@app.route('/document-required')
def document_required():
    return render_template('document-required.html')

@app.route('/ece-overview')
def ece_overview():
    return render_template('ece-overview.html')

@app.route('/ee-overview')
def ee_overview():
    return render_template('EE-overview.html')

@app.route('/electrical-overview')
def electrical_overview():
    return render_template('EL-overview.html')

@app.route('/fee-hostel')
def fee_hostel():
    return render_template('fee-hostel.html')

@app.route('/fee-structure')
def fee_structure():
    return render_template('fee-structure.html')

@app.route('/girls-hostel-info')
def girls_hostel_info():
    return render_template('girls-hostel-info.html')


@app.route('/holiday')
def holiday():
    return render_template('holiday.html')


@app.route('/IEEE-club')
def IEEE_club():
    return render_template('IEEE-club.html')



@app.route('/IOT-overview')
def IOT_overview():
    return render_template('IOT-overview.html')

@app.route('/ENV-overview')
def ENV_overview():
    return render_template('ENV-overview.html')

@app.route('/ENC-overview')
def ENC_overview():
    return render_template('ENC-overview.html')


@app.route('/CED-overview')
def CED_overview():
    return render_template('CED-overview.html')

@app.route('/IT-overview')
def IT_overview():
    return render_template('IT-overview.html')


@app.route('/Jhalak-club')
def Jhalak_club():
    return render_template('Jhalak-club.html')

@app.route('/Manan-club')
def Manan_club():
    return render_template('Manan-club.html')

@app.route('/ME-overview')
def ME_overview():
    return render_template('ME-overview.html')

@app.route('/Mechnext-club')
def Mechnext_club():
    return render_template('Mechnext-club.html')

@app.route('/Microbird-club')
def Microbird_club():
    return render_template('Microbird-club.html')

@app.route('/Nataraja-club')
def Nataraja_club():
    return render_template('Nataraja-club.html')

@app.route('/Niramayam-club')
def Niramayam_club():
    return render_template('Niramayam-club.html')

@app.route('/NITKKR-VS-YMCA')
def NITKKR_VS_YMCA():
    return render_template('NITKKR-VS-YMCA.html')

@app.route('/opcp2023')
def opcp2023():
    return render_template('opcp2023.html')

@app.route('/opcp2024')
def opcp2024():
    return render_template('opcp2024.html')

@app.route('/process')
def process():
    return render_template('process.html')


@app.route('/RAI-overview')
def RAI_overview():
    return render_template('RAI-overview.html')

@app.route('/rank-prediction')
def rank_prediction():
    return render_template('rank-prediction.html')

@app.route('/Samarpan-club')
def Samarpan_club():
    return render_template('Samarpan-club.html')

@app.route('/result')
def result():
    return render_template('result.html')

@app.route('/scholarship')
def scholarship():
    return render_template('scholarship.html')

@app.route('/sports')
def sports():
    return render_template('sports.html')

@app.route('/Srijan-club')
def Srijan_club():
    return render_template('Srijan-club.html')

@app.route('/timetable')
def timetable():
    return render_template('timetable.html')


@app.route('/Vividha-club')
def Vividha_club():
    return render_template('Vividha-club.html')


@app.route('/pyq')
def pyq():
    return render_template('pyq.html')



@app.route('/logo')
def logo():
    return render_template('logo.html')


@app.route('/logo1')
def logo1():
    return render_template('logo1.html')

@app.route('/event')
def event():
    return render_template('event.html')

@app.route('/story')
def story():
    return render_template('story.html')


@app.route('/ranking')
def ranking():
    return render_template('ranking.html')

@app.route('/faq')
def faq():
    return render_template('faq.html')

@app.route('/payment')
def payment():
    return render_template('payment.html')


@app.route('/placement')
def placement():
    return render_template('placement.html')


@app.route('/club')
def club():
    return render_template('club.html')




@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/mission')
def vision():
    return render_template('mission_vision.html')



@app.route('/branch-info')
def branch_info():
    return render_template('branch_info.html')


@app.route('/contact')
def contact():
    return render_template('contact.html')

@app.route('/report-issue')
def report_issue():
    return render_template('report_issue.html')

@app.route('/feedback')
def feedback():
    return render_template('feedback.html')


@app.route('/exam')
def exam():
    return render_template('exam.html')

if __name__ == '__main__':
    init_db()  # ✅ This creates the users table if it doesn't exist
    app.run(debug=True)








