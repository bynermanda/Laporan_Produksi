import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime, date, timedelta
import re

URL_KITA = "https://docs.google.com/spreadsheets/d/1uDmbbLhFsMdGSnozbRBMwEDPP2T20HqpEnJGYd2P390/edit"
default_time = datetime.strptime("07:00", "%H:%M").time()

# Konfigurasi Halaman
st.set_page_config(page_title="Input Produksi", layout="wide")
st.markdown("""
    <style>
    .block-container {
        padding-top: 1rem;
        padding-bottom: 0rem;
        padding-left: 1rem;
        padding-right: 1rem;
    }
    </style>
    """, unsafe_allow_html=True)

st.title("📊 SISTEM LAPORAN PRODUKSI PRESS")
st.markdown(f"**Tanggal Operasional:** {datetime.now().strftime('%d-%m-%Y')}")

# --- IDENTITAS OPERATOR ---
st.sidebar.header("Identitas Operator")
nama_operator = st.sidebar.text_input("Nama Lengkap", placeholder="Masukkan Nama")
nip_operator = st.sidebar.text_input("NIP / No. Karyawan", placeholder="Masukkan NIP")

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
        waktu_mulai = st.time_input("Waktu Mulai", value=default_time)
        waktu_selesai = st.time_input("Waktu Selesai", value=default_time)

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

    # Proses submit form
    konfirmasi = st.checkbox("Klik centang ini jika data sudah benar")
    submit = st.form_submit_button("Simpan ke Spreadsheet")

# --- BAGIAN 4: LOGIKA PENGIRIMAN DATA ---
if submit:
    # Hitung durasi kerja dalam jam (desimal)
    waktu_mulai_dt = datetime.combine(date.today(), waktu_mulai)
    waktu_selesai_dt = datetime.combine(date.today(), waktu_selesai)
    if waktu_selesai_dt < waktu_mulai_dt:
        waktu_selesai_dt += timedelta(days=1)
    durasi = waktu_selesai_dt - waktu_mulai_dt
    total_jam = durasi.total_seconds() / 3600  # Mengubah detik ke jam (desimal)
    
    # Agar NIP dengan Pola: 2 angka + titik + 6 angka
    pola_nip = r"^\d{2}\.\d{6}$"
    if re.match(pola_nip, nip_operator):
        # Jika NIP sudah benar, lanjutkan simpan data
        st.success("NIP Valid!")
    else:
        st.error("NIP tidak valid! Harus 2 angka, titik, lalu 6 angka.")
        st.stop()  # Hentikan proses jika NIP tidak valid
    
    if not nama_operator or not nip_operator:
        st.error("❌ GAGAL SIMPAN: Nama dan NIP Operator wajib diisi di menu samping (sidebar)!")
    
    elif act <= 0:
        st.warning("⚠️ PERINGATAN: Jumlah ACT belum diisi.")
        
    elif line_produksi == "":
        st.error("❌ GAGAL: Line Produksi harus dipilih/diisi.")

    elif konfirmasi == False:
        st.warning("⚠️ PERINGATAN: Silakan centang kotak konfirmasi sebelum submit.")

    else:
        # Kalkulasi Otomatis
        total_ng = ng_setting + ng_gonogo + ng_dll + ng_coil
        prod_percent = (act / sph * 100) if sph > 0 else 0
        rasio_ng = (total_ng / act * 100) if act > 0 else 0

        #Kirim data jika berhasil
        new_data = pd.DataFrame([{
            "Tanggal": datetime.now().strftime('%Y-%m-%d'),
            "Nama_Operator": nama_operator,
            "NIP": nip_operator,
            "Shift": shift,
            "Proses": proses_terpilih, # Menggunakan variabel proses_terpilih
            "Part_Name": part_name_default,
            "Jam": f"{waktu_mulai.strftime('%H:%M')} - {waktu_selesai.strftime('%H:%M')}",
            "Line_Produksi": line_produksi,
            "SPH": sph_default, # Menggunakan sph_default yang otomatis terisi
            "ACT": act,
            "Prod_%": f"{prod_percent:.1f}%",
            "NG_Total": total_ng,
            "Rasio_NG": f"{rasio_ng:.2f}%",
            "AP": ap_note,
            "Total Jam": f"{total_jam:.2f}"
    }])
    
    # Tambahkan kode conn.update Anda di sini
    try:
        # Baca data lama
        existing_data = conn.read(spreadsheet=URL_KITA, worksheet="Sheet1", ttl=0)
        updated_df = pd.concat([existing_data, new_data], ignore_index=True)
            # Menampilkan ringkasan sebelum kirim
        st.success("Data berhasil dihitung!")
        # Update ke sheet
        conn.update(spreadsheet=URL_KITA, worksheet="Sheet1", data=updated_df)
        st.success("✅ Data berhasil disimpan!")
        st.balloons()
        st.table(new_data)
    except Exception as e:
        st.error(f"Gagal menyimpan data: {e}")
