"""
Gaming History Dashboard (Streamlit)
Enhanced + Live Google Sheets I/O

Features:
- Live Google Sheet sync (read + write)
- Game card view (Steam-like)
- Genre filters
- Achievement badges
- Persistent state (theme, selected game)
- Add new gaming session form
"""

import streamlit as st
import pandas as pd
import datetime
import plotly.express as px
import gspread
from google.oauth2.service_account import Credentials

# ---------- PAGE CONFIG ----------
st.set_page_config(page_title="Gaming History", layout="wide")

# ---------- STYLES ----------
st.markdown(
    """
    <style>
    body, .stApp { background-color: #0b0f14; color: white; font-family: 'Inter', sans-serif; }
    .card {
        background: #111820;
        border-radius: 10px;
        padding: 10px;
        margin-bottom: 12px;
        text-align: center;
        transition: 0.3s;
        box-shadow: 0 2px 10px rgba(0,0,0,0.4);
    }
    .card:hover { transform: translateY(-2px); box-shadow: 0 4px 16px rgba(0,0,0,0.6); }
    img.game-cover { border-radius: 8px; width: 100%; height: 180px; object-fit: cover; }
    .metric-small { color: #9aa6b2; font-size: 13px; }
    </style>
    """,
    unsafe_allow_html=True
)

# ---------- GOOGLE SHEET UTILS ----------

def get_gsheet_client():
    """Authorize Google Sheets from Streamlit secrets (secure)."""
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive"
    ]
    creds = Credentials.from_service_account_info(
        st.secrets["google_service_account"], scopes=scope
    )
    return gspread.authorize(creds)

@st.cache_data(ttl=300)
def load_from_gsheet(sheet_name, tab):
    client = get_gsheet_client()
    sheet = client.open(sheet_name).worksheet(tab)
    data = sheet.get_all_records()
    return pd.DataFrame(data)

def append_to_gsheet(sheet_name, tab, row_dict):
    """Append a row to the Google Sheet tab."""
    client = get_gsheet_client()
    sheet = client.open(sheet_name).worksheet(tab)
    sheet.append_row(list(row_dict.values()))

# ---------- DATA NORMALIZATION ----------

def normalize_log_df(df):
    df.columns = df.columns.str.strip()
    df["Full Start"] = pd.to_datetime(df["Full Start"], errors="coerce")
    df["Full End"] = pd.to_datetime(df["Full End"], errors="coerce")
    df["duration_hours"] = (
        (df["Full End"] - df["Full Start"]).dt.total_seconds() / 3600
    ).round(2)
    df["month"] = pd.to_datetime(df["Full Start"]).dt.to_period("M")
    df["weekday"] = pd.to_datetime(df["Full Start"]).dt.day_name()
    return df

def normalize_register_df(df):
    df.columns = df.columns.str.strip()
    return df

def merge_data(log_df, reg_df):
    if "UID" in log_df.columns and "UID" in reg_df.columns:
        return pd.merge(log_df, reg_df, on="UID", how="left")
    else:
        return pd.merge(log_df, reg_df, left_on="GAME", right_on="Game", how="left")

# ---------- UI HELPERS ----------

def show_summary_metrics(df):
    total_hours = df["duration_hours"].sum()
    total_sessions = len(df)
    unique_games = df["GAME"].nunique() if "GAME" in df.columns else 0
    avg_session = df["duration_hours"].mean() if total_sessions > 0 else 0

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Hours", f"{total_hours:.1f}")
    col2.metric("Sessions", f"{total_sessions}")
    col3.metric("Unique Games", f"{unique_games}")
    col4.metric("Avg Session (hrs)", f"{avg_session:.2f}")

def playtime_achievements(df):
    total_hours = df["duration_hours"].sum()
    milestones = [
        (100, "🎯 Casual Grinder"),
        (250, "🔥 Hardcore Enthusiast"),
        (500, "⚔️ Legendary Gamer"),
        (1000, "👑 God-Tier Completionist"),
    ]
    badges = [
        f"<span style='background:rgba(102,194,255,0.1);border:1px solid #66c2ff;border-radius:8px;padding:6px 10px;margin:5px;display:inline-block;'>{title}</span>"
        for hrs, title in milestones if total_hours >= hrs
    ]
    if badges:
        st.markdown("**Achievements Unlocked:** " + " ".join(badges), unsafe_allow_html=True)

def genre_filter(df_register):
    genre_cols = [c for c in df_register.columns if c.lower().startswith("genretag")]
    if not genre_cols:
        return df_register

    all_tags = (
        df_register[genre_cols].melt(value_name="tag")["tag"]
        .dropna()
        .unique()
        .tolist()
    )
    selected_tags = st.sidebar.multiselect("🎭 Filter by genre tag", sorted(all_tags))
    if selected_tags:
        mask = df_register[genre_cols].isin(selected_tags).any(axis=1)
        return df_register[mask]
    return df_register

def game_card_view(df_register):
    st.markdown("### 🎮 Game Library")
    df = df_register.copy()
    cols = st.columns(4)
    for i, (_, row) in enumerate(df.iterrows()):
        with cols[i % 4]:
            st.markdown(
                f"""
                <div class='card'>
                    <img class='game-cover' src='{row.get("Game Image","")}' alt='{row["Game"]}'>
                    <div style='margin-top:6px;'>
                        <b>{row['Game']}</b><br>
                        <span class='metric-small'>{row.get('System','')} | {row.get('Genre','')}</span><br>
                        <span class='metric-small'>🕒 {row.get('Total Time',0)} hrs</span><br>
                        <span class='metric-small'>💰 ${row.get('Total Price Paid',0)}</span>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

def main_charts(df):
    with st.expander("📈 Playtime Trends", expanded=True):
        show_summary_metrics(df)
        playtime_achievements(df)

        st.markdown("#### Top Games by Hours")
        top_games = df.groupby("GAME")["duration_hours"].sum().sort_values(ascending=False).head(15)
        fig = px.bar(top_games, x=top_games.values, y=top_games.index, orientation="h", color=top_games.values)
        fig.update_layout(yaxis_title="", xaxis_title="Hours", height=400)
        st.plotly_chart(fig, use_container_width=True)

        st.markdown("#### Hours by Month")
        month_agg = df.groupby(df["month"].astype(str))["duration_hours"].sum().reset_index()
        fig2 = px.area(month_agg, x="month", y="duration_hours")
        fig2.update_layout(height=400)
        st.plotly_chart(fig2, use_container_width=True)

# ---------- SESSION ENTRY FORM ----------

def new_session_form(sheet_name, log_tab):
    st.markdown("### ✏️ Log a New Gaming Session")
    with st.form("add_session"):
        col1, col2 = st.columns(2)
        date = col1.date_input("Date", datetime.date.today())
        system = col1.text_input("System (e.g. PS5, PC)")
        game = col1.text_input("Game Name")
        solo_or_social = col2.selectbox("Solo or Social", ["Solo", "Social"])
        online_or_offline = col2.selectbox("Online or Offline", ["Online", "Offline"])
        start_time = col1.time_input("Start Time")
        end_time = col2.time_input("End Time")

        submitted = st.form_submit_button("Add Session")
        if submitted:
            full_start = datetime.datetime.combine(date, start_time)
            full_end = datetime.datetime.combine(date, end_time)
            duration = round((full_end - full_start).total_seconds() / 3600, 2)

            row = {
                "date": str(date),
                "TIME START": str(start_time),
                "TIME END": str(end_time),
                "SYSTEM": system,
                "GAME": game,
                "SOLO OR SOCIAL": solo_or_social,
                "ONLINE OR OFFLINE": online_or_offline,
                "Full Start": full_start.isoformat(),
                "Full End": full_end.isoformat(),
                "Duration Hours": duration
            }

            append_to_gsheet(sheet_name, log_tab, row)
            st.success(f"✅ Session for {game} logged successfully!")
            st.experimental_rerun()

# ---------- APP ----------

def app():
    st.title("🕹️ Gaming History Dashboard")

    st.sidebar.markdown("## Google Sheet Connection")
    sheet_name = st.sidebar.text_input("Google Sheet name or URL")
    log_tab = st.sidebar.text_input("Log tab name", "log")
    register_tab = st.sidebar.text_input("Register tab name", "register")

    if st.sidebar.button("Load data"):
        try:
            log_df = normalize_log_df(load_from_gsheet(sheet_name, log_tab))
            reg_df = normalize_register_df(load_from_gsheet(sheet_name, register_tab))
            merged = merge_data(log_df, reg_df)
            filtered_register = genre_filter(reg_df)

            main_charts(merged)
            st.markdown("---")
            game_card_view(filtered_register)
            st.markdown("---")
            new_session_form(sheet_name, log_tab)

        except Exception as e:
            st.error(f"Error: {e}")
    else:
        st.info("Enter your Google Sheet name and tab names, then click Load Data.")

if __name__ == "__main__":
    app()
