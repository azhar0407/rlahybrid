import streamlit as st
import pandas as pd
import numpy as np
from sqlalchemy import create_engine
import datetime

# --- 1. KONFIGURASI WEB & TAMPILAN AWAL ---
st.set_page_config(page_title="RLA V7 Screener", layout="wide", page_icon="🛡️")

# MUNCULKAN SIDEBAR LEBIH DULU AGAR WEB LANGSUNG TERLIHAT HIDUP
try:
    ADMIN_PASSWORD = st.secrets["ADMIN_PASS"]
    DB_URL = st.secrets["DB_URL"]
except Exception:
    st.error("⚠️ Brankas Rahasia (Secrets) belum diatur di Streamlit Cloud!")
    st.stop()

# Menu Sidebar
st.sidebar.header("🔐 Area Admin")
admin_input = st.sidebar.text_input("Masukkan Password Admin", type="password")
IS_ADMIN = (admin_input == ADMIN_PASSWORD)

st.sidebar.header("⚙️ Parameter V7")
use_ma200 = st.sidebar.checkbox("Wajib Uptrend MA200?", value=True)
req_foreign = st.sidebar.checkbox("Wajib Asing Net Buy?", value=True)
use_vbf = st.sidebar.checkbox("Gunakan VBF?", value=True)
vbf_multi = st.sidebar.slider("VBF ATR Multiplier", 0.5, 3.0, 1.2, 0.1)
vol_multi = st.sidebar.slider("Minimal Ledakan Volume (x)", 1.0, 5.0, 1.5, 0.1)
liq_min = st.sidebar.number_input("Min Likuiditas (Miliar)", value=10, min_value=0) * 1000000000.0

st.sidebar.markdown("---")
st.sidebar.header("🔍 Mode Eksplorasi")

ticker_mode = st.sidebar.radio("Target Saham:", ["Semua Saham (*All Symbols*)", "Pilih Saham Custom"])
selected_tickers = []
if ticker_mode == "Pilih Saham Custom":
    ticker_input = st.sidebar.text_input("Masukkan Kode Saham (cth: BBCA, BMRI, BJBR)")
    if ticker_input:
        selected_tickers = [t.strip().upper() for t in ticker_input.split(",")]

today = datetime.date.today()
col1, col2 = st.sidebar.columns(2)
with col1:
    start_date = st.date_input("Dari Tanggal", today)
with col2:
    end_date = st.date_input("Sampai Tanggal", today)

explore_btn = st.sidebar.button("🚀 Explore", use_container_width=True)

# JUDUL UTAMA HALAMAN
st.title("📱 RLA Hybrid AST LITE v7 (Elite Defensive)")

# --- 2. MESIN DATABASE ---
@st.cache_resource
def init_connection():
    return create_engine(DB_URL)

engine = init_connection()

@st.cache_data(ttl=3600, show_spinner=False)
def load_all_data():
    temp_engine = create_engine(DB_URL)
    return pd.read_sql_table('data_eod', con=temp_engine)

# --- 3. INFORMASI STATUS DATABASE (DENGAN SPINNER LOADING) ---
with st.spinner("📡 Menyambungkan ke Cloud & Memindai Jutaan Data..."):
    try:
        latest_date_query = pd.read_sql_query('SELECT MAX("Date") as max_date FROM data_eod', con=engine)
        latest_date = latest_date_query['max_date'].iloc[0]
        if latest_date:
            st.success(f"📅 **Status Server:** Database aktif. Data EOD terakhir diupdate pada **{latest_date}**")
        else:
            st.warning("⚠️ Database masih kosong. Silakan login Admin dan upload data pertama Anda.")
    except Exception:
        st.warning("⚠️ Database belum memiliki tabel. Silakan login Admin untuk inisialisasi.")

st.write("---")

# --- 4. PANEL ADMIN (UPLOAD EOD HARIAN) ---
if IS_ADMIN:
    st.sidebar.markdown("---")
    st.sidebar.success("Login Admin Berhasil!")
    st.write("### 🛠️ Panel Update Database")
    
    uploaded_file = st.file_uploader("Pilih file EOD", type=["csv", "xlsx"], label_visibility="hidden")

    if uploaded_file is not None:
        with st.spinner('Menyuntikkan data EOD harian ke Cloud...'):
            df_clean = pd.DataFrame()
            
            if uploaded_file.name.endswith('.csv'):
                df_clean = pd.read_csv(uploaded_file)
                df_clean['Date'] = pd.to_datetime(df_clean['Date'], format='mixed', dayfirst=True).dt.strftime('%Y-%m-%d')
            else:
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
            df_clean.to_sql('data_eod', con=engine, if_exists='append', index=False, chunksize=5000, method='multi')
            load_all_data.clear() 
            st.success("✅ Data Harian berhasil ditambahkan dalam hitungan detik! Refresh web untuk melihat.")

# --- 5. MESIN SCREENER PUBLIK ---
st.write("### 🚀 Hasil Screener V7")

if explore_btn:
    if start_date > end_date:
        st.error("⚠️ 'Dari Tanggal' tidak boleh lebih besar dari 'Sampai Tanggal'.")
    else:
        try:
            with st.spinner('Membaca Memori & Mengeksekusi Algoritma (Lebih Cepat)...'):
                df_db = load_all_data() 
                
                if not df_db.empty:
                    df_db['Date_dt'] = pd.to_datetime(df_db['Date'])
                    df_db = df_db.drop_duplicates(subset=['Ticker', 'Date'], keep='last')
                    df_db = df_db.sort_values(by=['Ticker', 'Date_dt'])
                    
                    df_db['MA200'] = df_db.groupby('Ticker')['Close'].transform(lambda x: x.rolling(200).mean())
                    df_db['AvgVol20'] = df_db.groupby('Ticker')['Volume'].transform(lambda x: x.rolling(20).mean())
                    df_db['AvgVal20'] = df_db.groupby('Ticker').apply(
                        lambda x: (((x['High'] + x['Low'] + x['Close']) / 3) * x['Volume']).rolling(20).mean(),
                        include_groups=False
                    ).reset_index(level=0, drop=True)
                    df_db['NetForeign'] = df_db['ForeignBuy'] - df_db['ForeignSell']
                    df_db['ROC20'] = df_db.groupby('Ticker')['Close'].transform(lambda x: x.pct_change(periods=20) * 100)
                    
                    idx_df = df_db[df_db['Ticker'] == '^JKSE'][['Date_dt', 'Close']].rename(columns={'Close': 'IdxClose'})
                    df_db = pd.merge(df_db, idx_df, on='Date_dt', how='left')
                    df_db['IdxClose'] = df_db['IdxClose'].ffill().bfill()
                    df_db['SafeIdx'] = np.where(df_db['IdxClose'] > 0, df_db['IdxClose'], df_db['Close'])
                    df_db['Ratio'] = df_db['Close'] / df_db['SafeIdx']
                    df_db['RS50'] = df_db.groupby('Ticker')['Ratio'].transform(lambda x: (x / x.rolling(50).mean() - 1) * 100)
                    
                    df_db['PrevClose'] = df_db.groupby('Ticker')['Close'].shift(1)
                    df_db['TR'] = df_db[['High', 'PrevClose']].max(axis=1) - df_db[['Low', 'PrevClose']].min(axis=1)
                    
                    def wilder_smooth(s, window):
                        return s.ewm(alpha=1/window, adjust=False).mean()
                    
                    df_db['ATR14'] = df_db.groupby('Ticker')['TR'].transform(lambda x: wilder_smooth(x, 14))
                    df_db['ATR10'] = df_db.groupby('Ticker')['TR'].transform(lambda x: wilder_smooth(x, 10))
                    
                    df_db['Range_MA20'] = df_db.groupby('Ticker').apply(
                        lambda x: (x['High'] - x['Low']).rolling(20).mean(),
                        include_groups=False
                    ).reset_index(level=0, drop=True)
                    df_db['Range_Wajib'] = df_db['Range_MA20'] + (vbf_multi * df_db['ATR14'])
                    
                    df_explore = df_db[(df_db['Date_dt'].dt.date >= start_date) & (df_db['Date_dt'].dt.date <= end_date)].copy()
                    
                    if ticker_mode == "Pilih Saham Custom" and selected_tickers:
                        df_explore = df_explore[df_explore['Ticker'].isin(selected_tickers)]
                    
                    if df_explore.empty:
                        st.warning("⚠️ Tidak ada data bursa pada rentang tanggal tersebut.")
                    else:
                        cond_trend = (df_explore['Close'] > df_explore['MA200']) if use_ma200 else True
                        cond_vol = (df_explore['Volume'] > (vol_multi * df_explore['AvgVol20'])) & (df_explore['Close'] > df_explore['PrevClose'])
                        cond_foreign = (df_explore['NetForeign'] > 0) if req_foreign else True
                        cond_vbf = ((df_explore['Close'] - df_explore['Low']) > df_explore['Range_Wajib']) if use_vbf else True
                        cond_liq = df_explore['AvgVal20'] > liq_min
                        cond_rs50 = df_explore['RS50'] > 0
                        cond_late = df_explore['ROC20'] < 25
                        
                        final_signal = df_explore[cond_trend & cond_vol & cond_foreign & cond_vbf & cond_liq & cond_rs50 & cond_late].copy()
                        
                        st.info(f"🔎 **Area Pencarian:** {start_date.strftime('%d %b %Y')} s/d {end_date.strftime('%d %b %Y')}")
                        
                        if not final_signal.empty:
                            final_signal['Tanggal'] = final_signal['Date_dt'].dt.strftime('%d/%m/%Y')
                            final_signal['Harga Entry'] = final_signal['Close']
                            final_signal['Risk'] = 2.5 * final_signal['ATR10']
                            final_signal['Max SL (-10%)'] = final_signal['Harga Entry'] * 0.90
                            final_signal['Target TP1'] = final_signal['Harga Entry'] + (final_signal['Risk'] * 1.5)
                            final_signal['Target TP2'] = final_signal['Harga Entry'] + (final_signal['Risk'] * 2.5)
                            final_signal['Vol Surge (x)'] = final_signal['Volume'] / final_signal['AvgVol20']
                            final_signal['RS50 %'] = final_signal['RS50']
                            
                            final_signal = final_signal.sort_values(by=['Date_dt', 'Ticker'], ascending=[False, True])
                            cols_to_show = ['Tanggal', 'Ticker', 'Harga Entry', 'Max SL (-10%)', 'Target TP1', 'Target TP2', 'Vol Surge (x)', 'RS50 %']
                            
                            st.dataframe(final_signal[cols_to_show].style.format({
                                'Harga Entry': "{:,.0f}",
                                'Max SL (-10%)': "{:,.0f}",
                                'Target TP1': "{:,.0f}",
                                'Target TP2': "{:,.0f}",
                                'Vol Surge (x)': "{:.2f}x",
                                'RS50 %': "{:.2f}%"
                            }), use_container_width=True)
                        else:
                            st.error("❌ Tidak ada sinyal saham yang lolos filter ketat V7.")
                else:
                    st.info("Database masih kosong. Hubungi Admin.")

        except Exception as e:
            st.error(f"Terjadi kesalahan saat eksplorasi. (Error: {e})")
else:
    st.info("👈 Silakan atur parameter di menu samping dan tekan tombol **🚀 Explore** untuk memulai.")
