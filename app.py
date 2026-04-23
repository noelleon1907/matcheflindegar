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
    conn.commit()

init_db()

# --- 2. AUTHENTIFIZIERUNG SETUP ---
# Hinweis: Passwörter müssen in der Produktion gehasht sein. 
# Für dieses Beispiel nutzen wir das Passwort 'Admin123456' für alle Accounts.
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
        },
        'leiter': {
            'name': 'Pfadi Leiter',
            'password': '$2b$12$6K8W0/K6L.M7M5n5V5/5.OuR6E2Y7U3R1Q5e5M5V5/5.OuR6E2Y7U', # Admin123456
            'email': 'leiter@pfadi.ch'
        }
    }
}

ROLES_MAP = {
    'admin': 'Admin',
    'matchef': 'MatChef',
    'leiter': 'Leiter'
}

authenticator = stauth.Authenticate(
    credentials,
    'pfadi_material_cookie',
    'random_signature_key',
    cookie_expiry_days=30
)

# --- 3. DIALOGE ---
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
        if st.button("Jetzt ausleihen", use_container_width=True, type="primary"):
            conn.execute("UPDATE materials SET status='Ausgeliehen', borrower=? WHERE id=?", 
                         (st.session_state['username'], item_id))
            conn.commit()
            st.success("Viel Spaß damit!")
            st.rerun()
    else:
        st.warning(f"Aktuell bei: **{item['borrower']}**")
        current_role = ROLES_MAP.get(st.session_state['username'], 'Leiter')
        # Rückgabe erlauben wenn Admin/MatChef oder man selbst der Ausleiher ist
        if current_role in ['Admin', 'MatChef'] or item['borrower'] == st.session_state['username']:
            if st.button("Rückgabe bestätigen", use_container_width=True):
                conn.execute("UPDATE materials SET status='Verfügbar', borrower='' WHERE id=?", (item_id,))
                conn.commit()
                st.rerun()

# --- 4. LOGIN LOGIK ---
# In der Version 0.3.0+ gibt login() nur noch den Status zurück
authentication_status = authenticator.login(location='main')

if st.session_state["authentication_status"]:
    username = st.session_state["username"]
    name = st.session_state["name"]
    role = ROLES_MAP.get(username, 'Leiter')
    
    # Sidebar Navigation
    st.sidebar.title("⚜️ Pfadi-Material")
    st.sidebar.write(f"Angemeldet: **{name}**")
    st.sidebar.write(f"Rolle: `{role}`")
    
    tabs = ["🔍 Suche", "📋 Meine Ausleihen"]
    if role in ["Admin", "MatChef"]:
        tabs.append("➕ Mat-Erfassung")
    if role == "Admin":
        tabs.append("⚙️ Admin-Panel")
        
    choice = st.sidebar.radio("Navigation", tabs)
    authenticator.logout('Abmelden', 'sidebar')

    # --- SEITE: SUCHE ---
    if choice == "🔍 Suche":
        st.header("Material-Katalog")
        col_s1, col_s2 = st.columns([2, 1])
        search = col_s1.text_input("Name suchen...", placeholder="Zelt, Seil...")
        stufe_filter = col_s2.selectbox("Stufe", ["Alle", "Biber", "WoBi", "Pfadi", "Pio", "Rover"])
        
        conn = get_db_connection()
        query = "SELECT * FROM materials WHERE 1=1"
        params = []
        if stufe_filter != "Alle":
            query += " AND stufe = ?"
            params.append(stufe_filter)
        if search:
            query += " AND name LIKE ?"
            params.append(f"%{search}%")
            
        df = pd.read_sql(query, conn, params=params)
        
        if df.empty:
            st.info("Keine Einträge gefunden.")
        else:
            for _, row in df.iterrows():
                with st.container(border=True):
                    c1, c2, c3 = st.columns([3, 2, 1])
                    c1.write(f"**{row['name']}**")
                    status_text = "✅ Frei" if row['status'] == 'Verfügbar' else f"❌ Bei {row['borrower']}"
                    c2.write(f"{row['stufe']} | {status_text}")
                    if c3.button("Details", key=f"mat_{row['id']}"):
                        show_details(row['id'])

    # --- SEITE: ERFASSUNG ---
    elif choice == "➕ Mat-Erfassung":
        st.header("Neues Material inventarisieren")
        with st.form("add_form", clear_on_submit=True):
            n = st.text_input("Bezeichnung")
            s = st.selectbox("Stufe", ["Biber", "WoBi", "Pfadi", "Pio", "Rover"])
            col1, col2, col3 = st.columns(3)
            raum = col1.text_input("Raum")
            regal = col2.text_input("Regal")
            kiste = col3.text_input("Kiste")
            wert = st.number_input("Wert (CHF)", min_value=0.0)
            datum = st.date_input("Kaufdatum")
            
            if st.form_submit_button("Eintrag erstellen"):
                if n:
                    conn = get_db_connection()
                    conn.execute("INSERT INTO materials (name, stufe, raum, regal, kiste, datum, wert, status, borrower) VALUES (?,?,?,?,?,?,?,?,?)",
                                 (n, s, raum, regal, kiste, str(datum), wert, "Verfügbar", ""))
                    conn.commit()
                    st.success(f"{n} wurde hinzugefügt!")
                else:
                    st.error("Bitte einen Namen angeben.")

    # --- SEITE: MEINE AUSLEIHEN ---
    elif choice == "📋 Meine Ausleihen":
        st.header("Was ich gerade habe")
        conn = get_db_connection()
        my_items = pd.read_sql("SELECT name, raum, datum FROM materials WHERE borrower = ?", conn, params=(username,))
        if my_items.empty:
            st.write("Dein Rucksack ist leer.")
        else:
            st.table(my_items)

    # --- SEITE: ADMIN ---
    elif choice == "⚙️ Admin-Panel":
        st.header("Admin-Bereich")
        conn = get_db_connection()
        all_data = pd.read_sql("SELECT * FROM materials", conn)
        
        st.subheader("Gesamtinventar & Status")
        st.dataframe(all_data, use_container_width=True)
        
        # CSV Export
        csv = all_data.to_csv(index=False).encode('utf-8')
        st.download_button("Inventar als CSV herunterladen", csv, "pfadi_inventar.csv", "text/csv")

elif st.session_state["authentication_status"] == False:
    st.error('Benutzername/Passwort ist falsch.')
elif st.session_state["authentication_status"] == None:
    st.info('Bitte Benutzernamen und Passwort eingeben.')
