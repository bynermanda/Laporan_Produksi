
import streamlit as st
import streamlit.components.v1 as components
from streamlit_qrcode_scanner import qrcode_scanner
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import pytz
from datetime import datetime, timedelta, timezone
import time

# SETUP THEME LANGSUNG DI KODE
st.set_page_config(page_title="Laporan Produksi Press PT. ISI", layout="wide")

# Injeksi JavaScript untuk mencegah refresh tak sengaja
components.html(
    """
    <script>
    window.parent.addEventListener('beforeunload', function (e) {
        // Pesan standar browser (beberapa browser modern mungkin tidak menampilkan teks kustom)
        var confirmationMessage = 'Data sedang diproses. Jika refresh, sesi scan akan hilang!';
        (e || window.event).returnValue = confirmationMessage;
        return confirmationMessage;
    });
    </script>
    """,
    height=0,
)

# Suntik CSS untuk warna
st.markdown("""
    <style>
    /* 1. Warna Background Utama */
    .stApp {
        background-color: #261ad6; /* Ganti hitam */
    }
    
    /* 2. Warna Sidebar */
    [data-testid="stSidebar"] {
        background-color: #ff0909; /* Ganti biru */
    }

    /* 3. Warna Semua Teks */
    h1, h2, h3, p, span, label {
        color: #ffffff !important;
    }

    /* 4. Warna Tombol Utama (Primary) */
    div.stButton > button {
        background-color: #00FF00 !important; /* Warna Hijau */
        color: black !important;
        border-radius: 10px;
    }
    </style>
    """, unsafe_allow_html=True)

def get_waktu_wib():
    # Mengambil waktu standar Asia/Jakarta dari database zona waktu pusat
    tz_jkt = pytz.timezone('Asia/Jakarta')
    return datetime.now(tz_jkt).replace(tzinfo=None)

# --- KONFIGURASI ---
st.set_page_config(page_title="Laporan Produksi Press PT ISI", layout="wide")
URL_KITA = "https://docs.google.com/spreadsheets/d/1uDmbbLhFsMdGSnozbRBMwEDPP2T20HqpEnJGYd2P390/edit"

if 'waktu_end' not in st.session_state:
    st.session_state.waktu_end = get_waktu_wib()
if 'waktu_start' not in st.session_state:
    st.session_state.waktu_start = get_waktu_wib()

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
            # CEK TERAKHIR: Apakah di detik ini sudah ada nama + part + status START?
            double_check = df_proses[(df_proses['Nama'] == data_dict['Nama']) & 
                                 (df_proses['Status'] == 'START')]
            
            if not double_check.empty:
                st.error("⚠️ Data START sudah ada di database. Batalkan manual jika salah.")
                return False
            
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
        st.error(f"Gagal memproses data, Catat Laporan dan Lapor Admin: {e}")
        return False
    

# --- FUNGSI BANTU: CARI BARIS AKTIF TERAKHIR UNTUK CHECK-IN/CHECK-OUT ---
def get_last_active_row(df, nama):
    # Cari baris yang Namanya sama DAN kolom 'Check-Out' nya masih kosong/NaN
    active_rows = df[(df['Nama'] == nama) & (df['Check-Out'].isna() | (df['Check-Out'] == ""))]
    if not active_rows.empty:
        # Kembalikan indeks baris terakhir (tambah 2 karena header GSheets + indeks 0)
        return active_rows.index[-1] + 2
    return None


# --- LOGIKA PROSES SCAN ---
def handle_scan():
    raw_scan = st.session_state.barcode_input.strip()
    if not raw_scan:
        return

    # Pecah barcode (Pemisah ;)
    data_pecah = raw_scan.split(';')
    part_no_scanned = raw_scan.split(';')[0].strip()

    match = main_df[main_df['Part_No'] == part_no_scanned]
    # CEK: Apakah operator ini masih punya pekerjaan yang belum selesai? (Status START tapi belum FINISH)
    df_proses = conn.read(spreadsheet=URL_KITA, worksheet="Proses", ttl=0)
    ongoing = df_proses[(df_proses['Nama'] == nama_karyawan) & (df_proses['Status'] == 'START')]
        
    if not ongoing.empty:
        # Jika ada proses yang masih jalan
        if st.session_state.get('status_kerja', 'IDLE') == "IDLE":
            row_terakhir = ongoing.iloc[-1]
            p_no = row_terakhir['Part_No']
        # 1. Cari standar dari Main Data
            match_main = main_df[main_df['Part_No'] == p_no]

        # 2. Rekonstruksi data part yang sedang dikerjakan
            st.session_state.current_part = {
                'part_no': row_terakhir['Part_No'],
                'part_name': row_terakhir['Part_Name'],
                'model': row_terakhir['Model'],
                'urutan_proses': row_terakhir['Urutan_Proses'],
                'line': row_terakhir['Line'],
                'sec_pcs': match_main.iloc[0]['SEC /PCS'] if not match_main.empty else 0
            }
            # 3. Pulihkan Waktu Start
            dt_str = f"{row_terakhir['Tanggal']} {row_terakhir['Waktu_Mulai']}"
            st.session_state.waktu_start = datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
            st.session_state.status_kerja = "RUNNING" # Pulihkan ke Running
            st.success(f"🔄 Sesi {p_no} dipulihkan!")
            st.session_state.barcode_input = ""
            st.rerun()
        
        # Jika statusnya RUNNING, baru boleh lanjut untuk scan FINISH
    if st.session_state.get('status_kerja') == "RUNNING":
        if part_no_scanned == st.session_state.current_part['part_no']:
            st.session_state.status_kerja = "FINISHING"
            st.session_state.waktu_end = get_waktu_wib()
            st.toast("🏁 Scan Finish Berhasil!")
            st.session_state.barcode_input = ""
            st.rerun()
        else:
            st.error(f"❌ Barcode ({part_no_scanned}) berbeda dengan Part yang sedang jalan!")
            return # Berhenti di sini jika salah scan part
    
    if st.session_state.get('status_kerja', 'IDLE') == "IDLE":
        match = main_df[main_df['Part_No'] == part_no_scanned]
        if not match.empty:
            st.session_state.available_processes = match.to_dict('records')
            st.session_state.status_kerja = "SELECTING_PROCESS"
        else:
            st.error(f"❌ Part No {part_no_scanned} tidak terdaftar di MainData!")
    
    
    # Kosongkan input scanner
    st.session_state.barcode_input = ""

# --- FUNGSI HELPER UNTUK UPDATE SHEET WAKTU KERJA ---
def update_aktivitas_kerja(nama, pesan_baru):
    try:
        # 1. Baca data waktu kerja terbaru
        df_waktu = conn.read(spreadsheet=URL_KITA, worksheet="Waktu Kerja", ttl=0)
        
        # 2. Cari baris aktif operator tersebut (Check-Out masih kosong)
        row_idx = get_last_active_row(df_waktu, nama)
        
        if row_idx:
            # Ambil waktu sekarang untuk timestamp aktivitas
            jam_skrg = datetime.now().strftime("%H:%M")
            
            # Ambil aktivitas lama dari dataframe (indeks di DF adalah row_idx - 2)
            # Pastikan kolom 'Aktivitas' ada, jika kosong berikan string kosong
            aktivitas_sebelumnya = df_waktu.iloc[row_idx-2].get('Aktivitas', "")
            if pd.isna(aktivitas_sebelumnya): aktivitas_sebelumnya = ""
            
            # Gabungkan pesan (Gunakan pemisah | atau baris baru)
            separator = " | " if aktivitas_sebelumnya != "" else ""
            catatan_update = f"{aktivitas_sebelumnya}{separator}[{jam_skrg}] {pesan_baru}"
            
            # 3. Update ke Google Sheets (Kolom F adalah kolom Aktivitas)
            conn.update(spreadsheet=URL_KITA, worksheet="Waktu Kerja", cell=f"F{row_idx}", data=catatan_update)
    except Exception as e:
        # Kita gunakan silent error agar proses produksi tidak terhenti hanya karena gagal log aktivitas
        print(f"Error update aktivitas: {e}")

        
# --- TAMPILAN SIDEBAR ---
st.sidebar.title("👤 Operator")
nama_karyawan = st.sidebar.text_input("Nama Karyawan", placeholder="Input Nama Anda")
st.sidebar.caption("Gunakan Kamera Utama untuk Scan Barcode Part")

if nama_karyawan:
    st.sidebar.markdown(f"Selamat Bekerja, **{nama_karyawan}**!")
    
    # Tombol Check-In
    if st.sidebar.button("🟢 Check-In Sekarang"):
        df_waktu = conn.read(spreadsheet=URL_KITA, worksheet="Waktu Kerja", ttl=0)
        row_index = get_last_active_row(df_waktu, nama_karyawan)

        if row_index:
            st.sidebar.warning("Anda sudah Check-In sebelumnya!")
        else:
            tgl = datetime.now().strftime("%Y-%m-%d")
            jam = datetime.now().strftime("%H:%M:%S")
            # Create baris baru: Tanggal, Nama, Check-In, Check-Out(Kosong), Total(0), Aktivitas
            new_data = [tgl, nama_karyawan, jam, "", 0, "Mulai Shift"]
            conn.create(spreadsheet=URL_KITA, worksheet="Waktu Kerja", data=[new_data])
            st.sidebar.success(f"Check-In Berhasil: {jam}")

    # Tombol Check-Out
    if st.sidebar.button("🔴 Check-Out Sekarang"):
        df_waktu = conn.read(spreadsheet=URL_KITA, worksheet="Waktu Kerja", ttl=0)
        row_index = get_last_active_row(df_waktu, nama_karyawan)
        
        if row_index:
            jam_out = datetime.now().strftime("%H:%M:%S")
            # Update kolom D (Check-Out) di baris tersebut
            conn.update(spreadsheet=URL_KITA, worksheet="Waktu Kerja", cell=f"D{row_index}", data=jam_out)
            
            # (Opsional) Hitung Total Jam Kerja di sini jika perlu
            st.sidebar.error(f"Check-Out Berhasil: {jam_out}")
            st.balloons()
        else:
            st.sidebar.error("Data Check-In tidak ditemukan!")

# --- TAMPILAN UTAMA ---
st.title("📟 Laporan Produksi Department Press PT Indosafety Sentosa")

if not nama_karyawan == "":
    st.warning("⚠️ Masukkan Nama di sidebar untuk memulai.")
else:
    # --- 1. INPUT BARCODE ---
    st.write("### 📸 Scan Barcode via Kamera HP")

    barcode_data = qrcode_scanner(key='scanner')
    if barcode_data:
        st.success(f"✅ Terdeteksi: {barcode_data}")
        st.session_state.barcode_input = barcode_data
        handle_scan()
        
    # --- 2. KONDISI: PILIH URUTAN PROSES ---
    if st.session_state.get('status_kerja') == "SELECTING_PROCESS":
        list_line = main_df['LINE'].unique().tolist() if 'LINE' in main_df.columns else []
        actual_line = st.sidebar.selectbox("Line", options=list_line)
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
                    "Actual_Line": actual_line,
                    "urutan_proses": detail['URUTAN']
                }
                st.session_state.status_kerja = "RUNNING"
                st.session_state.waktu_start = get_waktu_wib()
                st.rerun()

    # --- 3. KONDISI: SEDANG BERJALAN (START) ---
    elif st.session_state.get('status_kerja') == "RUNNING":
        dp = st.session_state.get('current_part')
        if dp:
            waktu_sekarang = get_waktu_wib()
            durasi_live = waktu_sekarang.replace(tzinfo=None) - st.session_state.waktu_start.replace(tzinfo=None)
            menit_live = int(durasi_live.total_seconds() / 60)
            jam_live = round(durasi_live.total_seconds() / 3600, 2)
            st.info(f"⚡ **Proses Berjalan:** {dp['part_name']} | sec_pcs : {dp['sec_pcs']} | {dp['model']}")
            
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Urutan", dp['urutan_proses'])
            col2.metric("Target Sec/Pcs", dp['sec_pcs'])
            col3.metric("Mulai", st.session_state.waktu_start.strftime('%H:%M:%S'))
            col4.metric("Sudah Berjalan", f"{menit_live} Menit", delta=f"{jam_live} Jam")

            if "is_submitting" not in st.session_state:
                st.session_state.is_submitting = False
            if st.button("🚀 Konfirmasi Kirim Start", use_container_width=True):
                st.session_state.is_submitting = True

                data_start = {
                    "Tanggal": get_waktu_wib().strftime("%Y-%m-%d"),
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
                with st.spinner("Sedang mencatat ke sistem..."):
                    if simpan_ke_sheet(data_start, "START"):
                        st.balloons()
                        st.success("✅ Produksi Dimulai!")
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.session_state.is_submitting = False

    # --- 4. KONDISI: SELESAI (FINISH) ---
    elif st.session_state.get('status_kerja') == "FINISHING":
        dp = st.session_state.get('current_part')
        if dp:
            st.subheader(f"📝 Laporan Akhir: {dp['part_name']}")
            
            waktu_start = st.session_state.get('waktu_start', get_waktu_wib())
            waktu_end = st.session_state.get('waktu_end', get_waktu_wib())
            durasi = waktu_end.replace(tzinfo=None) - waktu_start.replace(tzinfo=None)
            jam_total = round(durasi.total_seconds() / 60, 2)

            c1, c2, c3 = st.columns(3)
            act = c1.number_input("Jumlah ACT", min_value=0, step=1)
            ng = c2.number_input("Jumlah NG", min_value=0, step=1)
            c3.metric("Durasi", f"{jam_total} Menit", delta=f"{round(jam_total/60, 2)} Jam")

            # Kalkulasi SPH
            std_dari_state = float(st.session_state.current_part.get('sec_pcs', 0))
            standar_input = (dp['sec_pcs'] * act) / 60 if act > 0 else 0
            persen_prod = round((standar_input / jam_total) * 100, 2) if jam_total > 0 and std_dari_state > 0  else 0.0
            lost_time = max(0, (jam_total) - standar_input) if act > 0 and std_dari_state > 0 else 0.0

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
                            "%_Prod":f"{persen_prod:.2f}%",
                            "Rasio_NG": f"{(ng/act * 100) if act > 0 else 0:.2f}%",
                            "Total_Jam": f"{round(jam_total/60, 2)}",
                            "Status": "FINISH",
                            "Lost_Time_Menit": round(lost_time, 2),
                        }
                        if simpan_ke_sheet(data_finish, "FINISH"):
                            st.session_state.data_sph_terkirim = True
                            st.success("✅ SPH Terkirim!")
                            time.sleep(1)
                            st.rerun()

            # --- FORM ABNORMAL (Muncul setelah SPH) ---
        if st.session_state.get('data_sph_terkirim'):
            #Tampilan metrik SPH dan Lost Time
            c1, c2, c3 = st.columns(3)
            c1.metric("Persentase Produksi", f"{persen_prod:.2f} %")
            c2.metric("Lost Time", f"{round(lost_time, 2)} Menit", delta=f"{round(lost_time/60, 2)} Jam")
            c3.metric("Rasio NG", f"{(ng/act * 100) if act > 0 else 0:.2f} %")

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
                                "Tanggal": get_waktu_wib().strftime("%Y-%m-%d"),
                                "Mesin": dp.get('line', ''),
                                "Part_No": dp.get('part_no', ''),
                                "Model": dp.get('model', ''),
                                "Part_Name": dp.get('part_name', ''),
                                "Urutan_Proses": dp.get('urutan_proses', ''),
                                "Operator": nama_karyawan,
                                "Kode_Abnormal": item['kode'],
                                "Total_Waktu": item['durasi'],
                                "Keterangan": item['keterangan']
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

    #--- 5. KONDISI: IDLE (AWAL) atau automatic time --- 
    if st.session_state.get('status_kerja') == "RUNNING":
        st.divider()
        col_ref, col_res = st.columns(2)
    
        with col_ref:
            if st.button("🔄 Perbarui Waktu", use_container_width=True):
                st.rerun()
                st.caption("⏱️ Klik untuk update durasi berjalan")
        
        with col_res:
            if st.button("🚫 Batal / Reset Scanner", type="secondary", use_container_width=True):
                keys_to_clean = ['status_kerja', 'current_part', 'data_sph_terkirim', 'available_processes', 'waktu_start', 'waktu_end']
                for k in keys_to_clean:
                    if k in st.session_state: 
                        del st.session_state[k]
                st.rerun()
    else:
    # Jika tidak dalam kondisi RUNNING, cukup tampilkan tombol Reset saja
        if st.button("Batal / Reset Scanner", type="secondary"):
            keys_to_clean = ['status_kerja', 'current_part', 'data_sph_terkirim', 'available_processes']
            for k in keys_to_clean:
                if k in st.session_state: 
                    del st.session_state[k]
            st.rerun()

