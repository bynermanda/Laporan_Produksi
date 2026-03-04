import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime
import time

# --- KONFIGURASI ---
st.set_page_config(page_title="Sistem Scan Produksi", layout="wide")
URL_KITA = "https://docs.google.com/spreadsheets/d/1uDmbbLhFsMdGSnozbRBMwEDPP2T20HqpEnJGYd2P390/edit"

if 'waktu_end' not in st.session_state:
    st.session_state.waktu_end = datetime.now()
if 'waktu_start' not in st.session_state:
    st.session_state.waktu_start = datetime.now()

# Inisialisasi Koneksi
conn = st.connection("gsheets", type=GSheetsConnection)

# Fungsi Membaca MainData dengan Cache
@st.cache_data(ttl=3600) # Data disimpan di memori selama 1 jam (3600 detik)
def get_main_data(url):
    df = conn.read(spreadsheet=url, worksheet="MainData", ttl=0)
    df.columns = df.columns.str.strip() # Bersihkan nama kolom sekali saja
    return df

# Ambil MainData dan bersihkan nama kolomnya
try:
    main_df = get_main_data(URL_KITA)
except Exception as e:
    st.error(f"Gagal memuat MainData: {e}")
    main_df = pd.DataFrame()

# --- FUNGSI KIRIM DATA ---
def simpan_ke_sheet(data_dict, tipe):
    try:
        # 1. Ambil data terbaru dari sheet Proses
        df_proses = conn.read(spreadsheet=URL_KITA, worksheet="Proses", ttl=0)
        
        if tipe == "START":
            # LOGIKA START: Tambah baris baru seperti biasa
            new_row = pd.DataFrame([data_dict])
            updated_df = pd.concat([df_proses, new_row], ignore_index=True)
            conn.update(spreadsheet=URL_KITA, worksheet="Proses", data=updated_df)
            return True
            
        elif tipe == "FINISH":
            df_proses.columns = df_proses.columns.str.strip()
            # Kita cari index baris terakhir yang dikerjakan operator ini
            mask = (df_proses['Nama'].astype(str) == str(nama_karyawan)) & \
                   (df_proses['Part_No'].astype(str) == str(data_dict['Part_No'])) & \
                   (df_proses['Status'] == 'START')
            
            if mask.any():
                # Ambil index terakhir yang cocok
                idx = df_proses[mask].index[-1]
                
                # Update kolom di baris tersebut
                df_proses.at[idx, 'Waktu_Selesai'] = data_dict['Waktu_Selesai']
                df_proses.at[idx, 'ACT'] = data_dict['ACT']
                df_proses.at[idx, 'NG'] = data_dict['NG']
                df_proses.at[idx, '%_Prod'] = data_dict['%_Prod']
                df_proses.at[idx, 'Rasio_NG'] = data_dict['Rasio_NG']
                df_proses.at[idx, 'Total_Jam'] = data_dict['Total_Jam']
                df_proses.at[idx, 'Status'] = 'FINISH'
                # Update kembali ke sheet
                conn.update(spreadsheet=URL_KITA, worksheet="Proses", data=df_proses)
                return True
            else:
                st.error("❌ Tidak ditemukan data 'START' yang aktif untuk Part ini. Scan Start dulu!")
                return False
            
        elif tipe == "ABNORMAL":
            df_abnormal = conn.read(spreadsheet=URL_KITA, worksheet="ABNORMAL", ttl=0)
            new_row = pd.DataFrame([data_dict])
            updated_df = pd.concat([df_abnormal, new_row], ignore_index=True)
            # Update ke sheet Abnormal
            conn.update(spreadsheet=URL_KITA, worksheet="ABNORMAL", data=updated_df)
            return True

                
    except Exception as e:
        st.error(f"Gagal memproses data: {e}")
        return False

# --- LOGIKA PROSES SCAN ---
def handle_scan():
    raw_scan = st.session_state.barcode_input.strip()
    if not raw_scan:
        return

    # Pecah barcode (Pemisah ;)
    data_pecah = raw_scan.split(';')
    part_no_scanned = raw_scan.split(';')[0].strip()

    match = main_df[main_df['Part_No'] == part_no_scanned]

    if not match.empty:
        if st.session_state.get('status_kerja', 'IDLE') == "IDLE":
            st.session_state.available_processes = match.to_dict('records')
            st.session_state.status_kerja = "SELECTING_PROCESS"
            st.toast(f"✅ Part {part_no_scanned} ditemukan. Pilih urutan!")
        
        # CEK: Jika saat ini RUNNING, berarti scan barcode yang sama untuk FINISH
        elif st.session_state.get('status_kerja') == "RUNNING":
            time.sleep(1) # Memberikan jeda sedikit agar tidak terlalu berat
            st.empty()
            # Pastikan yang di-scan adalah Part_No yang sama dengan yang sedang jalan
            if part_no_scanned == st.session_state.current_part['part_no']:
                st.session_state.status_kerja = "FINISHING"
                st.session_state.waktu_end = datetime.now()
                st.toast("🏁 Scan Finish Berhasil!")
            else:
                st.error("❌ Barcode berbeda dengan Part yang sedang berjalan!")
    else:
        st.error(f"❌ Part No {part_no_scanned} tidak terdaftar di MainData!")
    
    # Kosongkan input scanner
    st.session_state.barcode_input = ""

# --- TAMPILAN SIDEBAR ---
st.sidebar.title("👤 Operator")
nama_karyawan = st.sidebar.text_input("Nama Karyawan", placeholder="Scan Nama Karyawan")

# --- TAMPILAN UTAMA ---
st.title("📟 Laporan Produksi Department Press PT Indosafety Sentosa")

if nama_karyawan == "":
    st.warning("⚠️ Masukkan Nama di sidebar untuk memulai.")
else:
    # --- 1. INPUT BARCODE ---
    st.text_input("TEMBAK BARCODE DI SINI", key="barcode_input", on_change=handle_scan)

    # --- 2. KONDISI: PILIH URUTAN PROSES ---
    if st.session_state.get('status_kerja') == "SELECTING_PROCESS":
        st.subheader("🔍 Pilih Urutan Proses")
        data_pilihan = st.session_state.get('available_processes', [])
        
        if data_pilihan:
            opsi_display = {f"{p['URUTAN']} | {p['Part_Name']}": p for p in data_pilihan}
            pilihan_user = st.selectbox("Pilih Urutan Proses Produksi?", options=list(opsi_display.keys()))

            if st.button("Konfirmasi & Mulai Kerja"):
                detail = opsi_display[pilihan_user]
                st.session_state.current_part = {
                    "part_no": detail['Part_No'],
                    "part_name": detail['Part_Name'],
                    "model": detail['MODEL'],
                    "sec_pcs": detail['SEC /PCS'],
                    "line": detail['LINE'],
                    "urutan_proses": detail['URUTAN']
                }
                st.session_state.status_kerja = "RUNNING"
                st.session_state.waktu_start = datetime.now()
                st.rerun()

    # --- 3. KONDISI: SEDANG BERJALAN (START) ---
    elif st.session_state.get('status_kerja') == "RUNNING":
        dp = st.session_state.get('current_part')
        if dp:
            waktu_sekarang = datetime.now()
            durasi_live = waktu_sekarang - st.session_state.waktu_start
            menit_live = int(durasi_live.total_seconds() / 60)
            jam_live = round(durasi_live.total_seconds() / 3600, 2)
            st.info(f"⚡ **Proses Berjalan:** {dp['part_name']} | sec_pcs : {dp['sec_pcs']} | {dp['model']}")
            
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Urutan", dp['urutan_proses'])
            col2.metric("Target Sec/Pcs", dp['sec_pcs'])
            col3.metric("Mulai", st.session_state.waktu_start.strftime('%H:%M:%S'))
            col4.metric("Sudah Berjalan", f"{menit_live} Menit", delta=f"{jam_live} Jam")

            if st.button("🚀 Konfirmasi Kirim Start", use_container_width=True):
                data_start = {
                    "Tanggal": datetime.now().strftime("%Y-%m-%d"),
                    "Nama": nama_karyawan,
                    "Part_No": dp['part_no'],
                    "Part_Name": dp['part_name'],
                    "Model": dp['model'],
                    "Line": dp['line'],
                    "Urutan_Proses": dp['urutan_proses'],
                    "Waktu_Mulai": st.session_state.waktu_start.strftime("%H:%M:%S"),
                    "Waktu_Selesai": "",
                    "ACT": 0, "NG": 0, "Status": "START"
                }
                if simpan_ke_sheet(data_start, "START"):
                    st.balloons()
                    st.success("✅ Produksi Dimulai!")
                    time.sleep(1)
                    st.rerun()

    # --- 4. KONDISI: SELESAI (FINISH) ---
    elif st.session_state.get('status_kerja') == "FINISHING":
        dp = st.session_state.get('current_part')
        if dp:
            st.subheader(f"📝 Laporan Akhir: {dp['part_name']}")
            
            waktu_start = st.session_state.get('waktu_start', datetime.now())
            waktu_end = st.session_state.get('waktu_end', datetime.now())
            durasi = waktu_end - waktu_start
            jam_total = round(durasi.total_seconds() / 3600, 2)

            c1, c2, c3 = st.columns(3)
            act = c1.number_input("Jumlah ACT", min_value=0, step=1)
            ng = c2.number_input("Jumlah NG", min_value=0, step=1)
            c3.metric("Durasi", f"{jam_total} Jam")

            # Kalkulasi SPH
            standar_input = (dp['sec_pcs'] * act) / 60 if act > 0 else 0
            persen_prod = (standar_input / (jam_total * 60) * 100) if jam_total > 0 else 0

            if not st.session_state.get('data_sph_terkirim'):
                if st.button("🚀 Kirim Data SPH", use_container_width=True):
                    if act <= 0:
                        st.error("⚠️ Isi ACT dulu!")
                    else:
                        data_finish = {
                            "Part_No": dp['part_no'],
                            "Waktu_Selesai": waktu_end.strftime("%H:%M:%S"),
                            "ACT": act,
                            "NG": ng,
                            "Standar Input": standar_input,
                            "%_Prod": f"{persen_prod:.2f}%",
                            "Rasio_NG": f"{(ng/act * 100) if act > 0 else 0:.2f}%",
                            "Total_Jam": jam_total,
                            "Status": "FINISH"
                        }
                        if simpan_ke_sheet(data_finish, "FINISH"):
                            st.session_state.data_sph_terkirim = True
                            st.success("✅ SPH Terkirim!")
                            time.sleep(1)
                            st.rerun()

            # --- FORM ABNORMAL (Muncul setelah SPH) ---
        if st.session_state.get('data_sph_terkirim'):
            st.divider()
            with st.form("form_abnormal_baru"):
                st.subheader("⚠️ Input Detail Abnormal")
                st.write("Silakan pilih kode, isi menit, dan keterangan (jika ada).")

                list_kode = ["", "A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K", "L", "M", "N", "O"]
                baris_input_abnormal = []

            # Membuat 10 baris input
                for i in range(1, 11):
                    col_kode, col_menit, col_ket = st.columns([2, 1, 3])
            
                    with col_kode:
                        kode_sel = st.selectbox(f"Kode {i}", options=list_kode, key=f"ab_kode_{i}")
                    with col_menit:
                        menit_val = st.number_input(f"Jumlah Menit", min_value=0, step=1, key=f"ab_menit_{i}")
                    with col_ket:
                        ket_val = st.text_input(f"Keterangan {i}", placeholder="Contoh: Ganti Tool", key=f"ab_ket_{i}")
            
            # Simpan hanya jika kode dipilih dan menit > 0
                    if kode_sel != "" and menit_val > 0:
                        baris_input_abnormal.append({
                        "kode": kode_sel,
                        "durasi": menit_val,
                        "keterangan": ket_val
                    })

                if st.form_submit_button("🏁 KONFIRMASI & RESET SCANNER"):
                    if baris_input_abnormal:
                        for item in baris_input_abnormal:
                            row_ab = {
                                "Tanggal": datetime.now().strftime("%Y-%m-%d"),
                                "Mesin": dp.get('line', ''),
                                "Part_No": dp.get('part_no', ''),
                                "Model": dp.get('model', ''),
                                "Part_Name": dp.get('part_name', ''),
                                "Urutan_Proses": dp.get('urutan_proses', ''),
                                "Operator": nama_karyawan,
                                "Kode_Abnormal": item['kode'],
                                "Total_Waktu": item['durasi'],
                                "Keterangan": item['keterangan'] # Pastikan kolom ini ada di Google Sheet
                            }
                            simpan_ke_sheet(row_ab, "ABNORMAL")
                        st.success(f"✅ {len(baris_input_abnormal)} Data Abnormal Berhasil Disimpan!")
                        
                        # RESET SEMUA
                        for k in ['status_kerja', 'current_part', 'waktu_start', 'waktu_end', 'data_sph_terkirim', 'available_processes']:
                            if k in st.session_state: del st.session_state[k]
                        
                        st.balloons()
                        st.success("✅ Semua Laporan Selesai!")
                        time.sleep(2)
                        st.rerun()

    # Tombol Reset Manual
    if st.button("Batal / Reset Scanner", type="secondary"):
        for k in ['status_kerja', 'current_part', 'data_sph_terkirim']:
            if k in st.session_state: del st.session_state[k]
        st.rerun()

