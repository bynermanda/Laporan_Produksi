import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime

URL_KITA = "https://docs.google.com/spreadsheets/d/1uDmbbLhFsMdGSnozbRBMwEDPP2T20HqpEnJGYd2P390/edit"

# Konfigurasi Halaman
st.set_page_config(page_title="Input Produksi", layout="wide")

st.title("📊 SISTEM LAPORAN PRODUKSI PRESS")
st.markdown(f"**Tanggal Operasional:** {datetime.now().strftime('%d-%m-%Y')}")

# 1. Koneksi ke Google Sheets (Database & Endpoint)
# Pastikan URL sheet ada di .streamlit/secrets.toml atau Environment Variables Render
conn = st.connection("gsheets", type=GSheetsConnection)
try:
    # Baca Master Data
    master_df = conn.read(spreadsheet=URL_KITA, worksheet="MasterData", ttl=0)
    list_no = master_df['NO'].tolist()
except Exception as e:
    st.error(f"Gagal memuat Master Data: {e}")
    list_no = ["Data Kosong"]

# --- BAGIAN 2: LOGIKA PENCARIAN OTOMATIS (DI LUAR FORM) ---
# Tampilkan pilihan NO di luar form agar aplikasi bisa "refresh" nilai SPH & Part Name seketika saat dipilih
st.subheader("Pilih Item Produksi")
proses_terpilih = st.selectbox("Pilih NO / Proses Produksi", options=list_no)

# Cari data pasangannya di master_df
if proses_terpilih and "Data Kosong" not in list_no:
    data_row = master_df[master_df['NO'] == proses_terpilih].iloc[0]
    sph_default = int(data_row['SPH'])
    part_name_default = data_row['PART NAME']
else:
    sph_default = 0
    part_name_default = ""

# --- BAGIAN 3: FORM INPUT PRODUKSI ---
with st.form("input_produksi_form"):
    st.info(f"Part Name: **{part_name_default}**") # Menampilkan info part yang terpilih
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        shift = st.selectbox("Shift", ["I", "II"])
        # Kita tampilkan kembali proses yang dipilih sebagai konfirmasi (disabled)
        proses = st.text_input("Proses", value=proses_terpilih, disabled=True)
        waktu_mulai = st.time_input("Waktu Mulai", datetime.now().time())
        waktu_selesai = st.time_input("Waktu Selesai", datetime.now().time())

    with col2:
        # SPH otomatis terisi dari sph_default, tapi tetap bisa diedit jika perlu (atau ganti disabled=True jika ingin kunci)
        sph = st.number_input("SPH (Target)", value=sph_default, disabled=True)
        act = st.number_input("ACT (Realisasi)", min_value=0, value=0)
        ng_setting = st.number_input("NG: Setting Awal", min_value=0, value=0)
        ng_gonogo = st.number_input("NG: Gonogo", min_value=0, value=0)

    with col3:
        line_produksi = st.text_input("Line Produksi", placeholder="Contoh: Line Q4")
        ng_dll = st.number_input("NG: DLL", min_value=0, value=0)
        ng_coil = st.number_input("NG: Coil Akhir", min_value=0, value=0)
        ap_note = st.text_input("AP (Keterangan)", placeholder="Contoh: M1+M+C")

    # Kalkulasi Otomatis
    total_ng = ng_setting + ng_gonogo + ng_dll + ng_coil
    prod_percent = (act / sph * 100) if sph > 0 else 0
    rasio_ng = (total_ng / act * 100) if act > 0 else 0

    submit = st.form_submit_button("Simpan ke Spreadsheet")

# --- BAGIAN 4: LOGIKA PENGIRIMAN DATA ---
if submit:
    new_data = pd.DataFrame([{
        "Tanggal": datetime.now().strftime('%Y-%m-%d'),
        "Shift": shift,
        "Proses": proses_terpilih, # Menggunakan variabel proses_terpilih
        "Part_Name": part_name_default,
        "Jam": f"{waktu_mulai.strftime('%H:%M')} - {waktu_selesai.strftime('%H:%M')}",
        "Line_Produksi": line_produksi,
        "SPH": sph_default, # Menggunakan sph_default yang otomatis terisi
        "ACT": act,
        "Prod_%": f"{prod_percent:.1f}%",
        "NG_Total": total_ng,
        "Rasio_NG": f"{rasio_ng:.3f}%",
        "AP": ap_note
    }])
    
    # Tambahkan kode conn.update Anda di sini
    try:
        # Baca data lama
        existing_data = conn.read(spreadsheet=URL_KITA, worksheet="Sheet1", ttl=0)
        updated_df = pd.concat([existing_data, new_data], ignore_index=True)
            # Menampilkan ringkasan sebelum kirim
        st.success("Data berhasil dihitung!")
        st.table(new_data)
        # Update ke sheet
        conn.update(spreadsheet=URL_KITA, worksheet="Sheet1", data=updated_df)
        st.success("✅ Data berhasil disimpan!")
    except Exception as e:
        st.error(f"Gagal menyimpan data: {e}")