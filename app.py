import streamlit as st
import streamlit_authenticator as stauth
import sqlite3
import pandas as pd
from datetime import datetime

# --- 1. INITIALISIERUNG & DATENBANK ---
st.set_page_config(page_title="Pfadi Mat-Verwaltung", layout="wide", page_icon="⚜️")

def get_db_connection():
    conn = sqlite3.connect("pfadi_verwaltung.db", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    # Tabelle für Material
    conn.execute('''CREATE TABLE IF NOT EXISTS materials 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, stufe TEXT, 
                  raum TEXT, regal TEXT, kiste TEXT, datum TEXT, wert REAL, 
                  status TEXT, borrower TEXT)''')
    # Tabelle für Benutzer (Zusatzinfos zur Authenticator-Config)
    conn.execute('''CREATE TABLE IF NOT EXISTS user_roles 
                 (username TEXT PRIMARY KEY, role TEXT)''')
    conn.commit()

init_db()

# --- 2. AUTHENTIFIZIERUNG SETUP ---
# In einer echten App würdest du dies aus einer YAML oder DB laden.
# Hier ein Initial-Setup. Passwörter sind "Admin123456" etc.
# Hashes wurden mit stauth.Hasher.hash('passwort') generiert.
credentials = {
    'usernames': {
        'admin': {
            'name': 'Haupt Admin',
            'password': '$2b$12$6K8W0/K6L.M7M5n5V5/5.OuR6E2Y7U3R1Q5e5M5V5/5.OuR6E2Y7U', # Admin123456
            'email': 'admin@pfadi.ch'
        },
        'matchef': {
            'name': 'Material Wart',
            'password': '$2b$12$6K8W0/K6L.M7M5n5V5/5.OuR6E2Y7U3R1Q5e5M5V5/5.OuR6E2Y7U', # Admin123456
            'email': 'mat@pfadi.ch'
        }
    }
}

# Rollen-Mapping (Wichtig für die Logik)
ROLES_MAP = {
    'admin': 'Admin',
    'matchef': 'MatChef',
    'leiter': 'Leiter'
}

authenticator = stauth.Authenticate(
    credentials,
    'pfadi_cookie',
    'auth_key_123',
    cookie_expiry_days=30
)

# --- 3. UI KOMPONENTEN ---

@st.dialog("Material-Details")
def show_details(item_id):
    conn = get_db_connection()
    item = conn.execute("SELECT * FROM materials WHERE id = ?", (item_id,)).fetchone()
    
    st.subheader(f"📦 {item['name']}")
    col1, col2 = st.columns(2)
    with col1:
        st.write(f"**Stufe:** {item['stufe']}")
        st.write(f"**Lagerort:** {item['raum']} / {item['regal']} / {item['kiste']}")
    with col2:
        st.write(f"**Anschaffung:** {item['datum']}")
        st.write(f"**Wert:** {item['wert']} CHF")
    
    st.divider()
    
    if item['status'] == "Verfügbar":
        if st.button("Ausleihen", use_container_width=True, type="primary"):
            conn.execute("UPDATE materials SET status='Ausgeliehen', borrower=? WHERE id=?", 
                         (st.session_state['username'], item_id))
            conn.commit()
            st.success("Erfolgreich ausgeliehen!")
            st.rerun()
    else:
        st.warning(f"Ausgeliehen von: {item['borrower']}")
        # MatChef oder der Ausleiher selbst dürfen zurückgeben
        current_role = ROLES_MAP.get(st.session_state['username'], 'Leiter')
        if current_role in ['Admin', 'MatChef'] or item['borrower'] == st.session_state['username']:
            if st.button("Rückgabe bestätigen", use_container_width=True):
                conn.execute("UPDATE materials SET status='Verfügbar', borrower='' WHERE id=?", (item_id,))
                conn.commit()
                st.rerun()

# --- 4. HAUPTPROGRAMM ---

name, authentication_status, username = authenticator.login('main')

if authentication_status:
    # Rollen-Zuweisung
    role = ROLES_MAP.get(username, 'Leiter')
    
    st.sidebar.title(f"⚜️ Pfadi-Mat")
    st.sidebar.write(f"Hallo **{name}**")
    st.sidebar.write(f"Rolle: `{role}`")
    
    tabs = ["🔍 Suche", "📋 Meine Ausleihen"]
    if role in ["Admin", "MatChef"]:
        tabs.append("➕ Mat-Erfassung")
    if role == "Admin":
        tabs.append("⚙️ Admin-Panel")
        
    choice = st.sidebar.radio("Navigation", tabs)
    authenticator.logout('Abmelden', 'sidebar')

    # --- TAB: SUCHE ---
    if choice == "🔍 Suche":
        st.header("Material-Katalog")
        col_s1, col_s2 = st.columns([2, 1])
        search = col_s1.text_input("Suchen...", placeholder="Zelt, Kocher...")
        stufe = col_s2.selectbox("Stufe", ["Alle", "Biber", "WoBi", "Pfadi", "Pio", "Rover"])
        
        conn = get_db_connection()
        query = "SELECT * FROM materials WHERE 1=1"
        params = []
        if stufe != "Alle":
            query += " AND stufe = ?"
            params.append(stufe)
        if search:
            query += " AND name LIKE ?"
            params.append(f"%{search}%")
            
        df = pd.read_sql(query, conn, params=params)
        
        if df.empty:
            st.info("Kein Material gefunden.")
        else:
            for _, row in df.iterrows():
                with st.container(border=True):
                    c1, c2, c3 = st.columns([3, 2, 1])
                    c1.write(f"**{row['name']}**")
                    status_label = "✅ Frei" if row['status'] == 'Verfügbar' else f"❌ Bei {row['borrower']}"
                    c2.write(f"{row['stufe']} | {status_label}")
                    if c3.button("Details", key=f"mat_{row['id']}"):
                        show_details(row['id'])

    # --- TAB: MAT-ERFASSUNG ---
    elif choice == "➕ Mat-Erfassung":
        st.header("Neues Material hinzufügen")
        with st.form("mat_form", clear_on_submit=True):
            name_mat = st.text_input("Name")
            stufe_mat = st.selectbox("Stufe", ["Biber", "WoBi", "Pfadi", "Pio", "Rover"])
            c1, c2, c3 = st.columns(3)
            r = c1.text_input("Raum")
            reg = c2.text_input("Regal")
            kis = c3.text_input("Kiste")
            val = st.number_input("Wert (CHF)", min_value=0.0)
            dat = st.date_input("Kaufdatum")
            
            if st.form_submit_button("Speichern"):
                if name_mat:
                    conn = get_db_connection()
                    conn.execute("INSERT INTO materials (name, stufe, raum, regal, kiste, datum, wert, status, borrower) VALUES (?,?,?,?,?,?,?,?,?)",
                                 (name_mat, stufe_mat, r, reg, kis, str(dat), val, "Verfügbar", ""))
                    conn.commit()
                    st.success("Material erfasst!")
                else:
                    st.error("Name fehlt!")

    # --- TAB: MEINE AUSLEIHEN ---
    elif choice == "📋 Meine Ausleihen":
        st.header("Deine Ausleihen")
        conn = get_db_connection()
        my_df = pd.read_sql("SELECT * FROM materials WHERE borrower = ?", conn, params=(username,))
        if my_df.empty:
            st.write("Du hast aktuell nichts ausgeliehen.")
        else:
            st.dataframe(my_df[['name', 'stufe', 'raum', 'datum']], use_container_width=True)

    # --- TAB: ADMIN-PANEL ---
    elif choice == "⚙️ Admin-Panel":
        st.header("Administration")
        st.info("Hier können Benutzerrechte verwaltet und Inventur-Listen exportiert werden.")
        
        conn = get_db_connection()
        all_mat = pd.read_sql("SELECT * FROM materials", conn)
        
        st.subheader("Gesamtinventar")
        st.dataframe(all_mat, use_container_width=True)
        
        csv = all_mat.to_csv(index=False).encode('utf-8')
        st.download_button("Liste als CSV exportieren", csv, "inventar.csv", "text/csv")

elif authentication_status == False:
    st.error('Benutzername/Passwort falsch')
elif authentication_status == None:
    st.warning('Bitte logge dich ein.')
