import streamlit as st
import pandas as pd
import numpy as np
from sqlalchemy import create_engine

# --- 1. KONFIGURASI WEB & DATABASE ---
st.set_page_config(page_title="RLA V7 Screener", layout="wide", page_icon="🛡️")
st.title("📱 RLA Hybrid AST LITE v7 (Elite Defensive)")

# Mengambil rahasia dari Brankas (Secrets)
ADMIN_PASSWORD = st.secrets["ADMIN_PASS"]
DB_URL = st.secrets["DB_URL"]

# Membuat Mesin Koneksi Database SQL
@st.cache_resource
def init_connection():
    return create_engine(DB_URL)

engine = init_connection()

# --- 2. SISTEM LOGIN ADMIN ---
st.sidebar.header("🔐 Area Admin")
admin_input = st.sidebar.text_input("Masukkan Password Admin", type="password")
IS_ADMIN = (admin_input == ADMIN_PASSWORD)

# --- 3. MENU PARAMETER PUBLIK ---
st.sidebar.header("⚙️ Parameter V7")
use_ma200 = st.sidebar.checkbox("Wajib Uptrend MA200?", value=True)
req_foreign = st.sidebar.checkbox("Wajib Asing Net Buy?", value=True)
use_vbf = st.sidebar.checkbox("Gunakan VBF?", value=True)
vbf_multi = st.sidebar.slider("VBF ATR Multiplier", 0.5, 3.0, 1.2, 0.1)
vol_multi = st.sidebar.slider("Minimal Ledakan Volume (x)", 1.0, 5.0, 1.5, 0.1)

# --- 4. PANEL ADMIN (UPLOAD DATA KE SQL) ---
if IS_ADMIN:
    st.sidebar.success("Login Admin Berhasil!")
    st.write("### 🛠️ Panel Update Database (Admin Only)")
    st.info("Upload file Historis (CSV) atau file EOD Harian (XLSX). Data otomatis tersimpan permanen di Supabase PostgreSQL.")
    
    uploaded_file = st.file_uploader("", type=["csv", "xlsx"])

    if uploaded_file is not None:
        with st.spinner('Memproses data dan mengirim ke Database Cloud...'):
            df_clean = pd.DataFrame()
            
            # CEK & BERSIHKAN FORMAT FILE
            if uploaded_file.name.endswith('.csv'):
                # Format CSV (Amibroker)
                df_clean = pd.read_csv(uploaded_file)
                df_clean['Date'] = pd.to_datetime(df_clean['Date'], format='mixed', dayfirst=True).dt.strftime('%Y-%m-%d')
            else:
                # Format XLSX (HP/Raw)
                df_raw = pd.read_excel(uploaded_file)
                df_clean['Ticker'] = df_raw['Kode Saham']
                df_clean['Date'] = pd.to_datetime(df_raw['Tanggal Perdagangan Terakhir']).dt.strftime('%Y-%m-%d')
                df_clean['Open'] = df_raw['Open Price']
                df_clean['High'] = df_raw['Tertinggi']
                df_clean['Low'] = df_raw['Terendah']
                df_clean['Close'] = df_raw['Penutupan']
                df_clean['Volume'] = df_raw['Volume']
                df_clean['ForeignBuy'] = df_raw['Foreign Buy']
                df_clean['ForeignSell'] = df_raw['Foreign Sell']
                df_clean = df_clean[df_clean['Volume'] > 0]

            # MENGGABUNGKAN KE DATABASE PERMANEN
            try:
                # Tarik data lama dari SQL
                df_history = pd.read_sql_table('data_eod', con=engine)
                df_full = pd.concat([df_history, df_clean], ignore_index=True)
            except ValueError:
                # Jika tabel belum ada (baru pertama kali upload)
                df_full = df_clean.copy()

            # Cegah duplikasi data
            df_full = df_full.drop_duplicates(subset=['Ticker', 'Date'], keep='last')
            
            # Tembak kembali ke Supabase SQL
            df_full.to_sql('data_eod', con=engine, if_exists='replace', index=False)
            st.success("✅ Database Supabase berhasil diperbarui!")

# --- 5. MESIN SCREENER PUBLIK (AI ENGINE) ---
st.write("---")
st.write("### 🚀 Hasil Screener V7")

try:
    with st.spinner('Menarik data dari Supabase & Menghitung Algoritma...'):
        # Menarik data bersih dari database
        df_db = pd.read_sql_table('data_eod', con=engine)
        
        if not df_db.empty:
            df_db['Date_dt'] = pd.to_datetime(df_db['Date'])
            df_db = df_db.sort_values(by=['Ticker', 'Date_dt'])
            
            # Kalkulasi AI (MA200, Volume, Foreign)
            df_db['MA200'] = df_db.groupby('Ticker')['Close'].transform(lambda x: x.rolling(200).mean())
            df_db['AvgVol20'] = df_db.groupby('Ticker')['Volume'].transform(lambda x: x.rolling(20).mean())
            df_db['NetForeign'] = df_db['ForeignBuy'] - df_db['ForeignSell']
            
            # Kalkulasi VBF
            df_db['PrevClose'] = df_db.groupby('Ticker')['Close'].shift(1)
            df_db['TR'] = df_db[['High', 'PrevClose']].max(axis=1) - df_db[['Low', 'PrevClose']].min(axis=1)
            df_db['ATR14'] = df_db.groupby('Ticker')['TR'].transform(lambda x: x.rolling(14).mean())
            
            df_db['Range_MA20'] = df_db.groupby('Ticker').apply(lambda x: (x['High'] - x['Low']).rolling(20).mean()).reset_index(level=0, drop=True)
            df_db['Range_Wajib'] = df_db['Range_MA20'] + (vbf_multi * df_db['ATR14'])
            
            # Ambil data hari bursa terakhir saja
            last_date = df_db['Date_dt'].max()
            df_today = df_db[df_db['Date_dt'] == last_date].copy()
            
            if df_today['MA200'].isnull().all():
                st.warning("⚠️ Menunggu Admin mengupload Base Data Historis 200 Hari...")
            else:
                # Menerapkan Filter Elite Defensive v7
                cond_trend = (df_today['Close'] > df_today['MA200']) if use_ma200 else True
                cond_vol = (df_today['Volume'] > (vol_multi * df_today['AvgVol20'])) & (df_today['Close'] > df_today['PrevClose'])
                cond_foreign = (df_today['NetForeign'] > 0) if req_foreign else True
                cond_vbf = ((df_today['Close'] - df_today['Low']) > df_today['Range_Wajib']) if use_vbf else True
                
                final_signal = df_today[cond_trend & cond_vol & cond_foreign & cond_vbf]
                
                st.info(f"📅 **Data Update Terakhir:** {last_date.strftime('%d %B %Y')}")
                
                if not final_signal.empty:
                    cols_to_show = ['Ticker', 'Close', 'NetForeign', 'Volume']
                    st.dataframe(final_signal[cols_to_show].style.format({
                        'Volume': "{:,.0f}", 
                        'NetForeign': "{:,.0f}"
                    }), use_container_width=True)
                else:
                    st.error("Tidak ada saham yang lolos filter ketat V7 hari ini.")
        else:
            st.info("Database masih kosong. Hubungi Admin.")

except ValueError:
    st.info("Database Server belum memiliki tabel. Silakan login sebagai Admin dan upload data pertama Anda.")
except Exception as e:
    st.error(f"Gagal terhubung ke Database Supabase. Pastikan link koneksi di st.secrets sudah benar. \n(Error: {e})")