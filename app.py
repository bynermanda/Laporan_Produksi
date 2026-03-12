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
if 'nama_terpilih' not in st.session_state:
    st.session_state.nama_terpilih = ""

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
                st.error("⚠️ Data START sudah ada di database atau sedang aktif.")
                st.error("⚠️ klik BATAL/Reset Scanner dan Scan barcode yang sesuai.")
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
                df_proses.at[idx, 'Total Istirahat'] = data_dict['Total Istirahat']
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
    part_no_scanned = raw_scan.split(';')[0].strip()

    match = main_df[main_df['Part_No'] == part_no_scanned]
    
    if st.session_state.get('status_kerja', 'IDLE') == "IDLE":
        match = main_df[main_df['Part_No'] == part_no_scanned]
        # CEK: Apakah operator ini masih punya pekerjaan yang belum selesai? (Status START tapi belum FINISH)
        df_proses = conn.read(spreadsheet=URL_KITA, worksheet="Proses", ttl=0)
        ongoing = df_proses[(df_proses['Nama'] == nama_karyawan) & (df_proses['Status'] == 'START')]
    
        if not ongoing.empty:

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
                'Actual_Line': row_terakhir.get('Actual_Line', 'N/A'),
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
            st.session_state.barcode_input = ""
            return # Berhenti di sini jika salah scan part

    if st.session_state.get('status_kerja', 'IDLE') == "IDLE":
            match = main_df[main_df['Part_No'] == part_no_scanned]
            if not match.empty:
                st.session_state.available_processes = match.to_dict('records')
                st.session_state.status_kerja = "SELECTING_PROCESS"
                st.session_state.barcode_input = ""
                st.rerun()
            else:
                st.error(f"❌ Part No {part_no_scanned} tidak terdaftar!")
                st.session_state.barcode_input = ""

    # Kosongkan input scanner
    st.session_state.barcode_input = ""
        
nama_karyawan = st.session_state.nama_terpilih

is_sudah_checkin = False
if nama_karyawan:
    df_waktu = conn.read(spreadsheet=URL_KITA, worksheet="Waktu Kerja", ttl=0)
    # Cek apakah ada baris aktif (Check-In ada, Check-Out kosong)
    status_absen = get_last_active_row(df_waktu, nama_karyawan)
    
    if status_absen:
        is_sudah_checkin = True
# --- TAMPILAN UTAMA ---
st.title("📟 Laporan Produksi Department Press PT Indosafety Sentosa")

# LAYAR 1: BELUM SCAN NAMA
if not nama_karyawan:
    st.subheader("👋 Selamat Datang! Silakan Scan ID Operator")
    barcode_id = qrcode_scanner(key='scanner_id_operator')
    if barcode_id:
        st.session_state.nama_terpilih = barcode_id
        st.rerun()

# LAYAR 2: SUDAH SCAN NAMA TAPI BELUM CHECK-IN
elif not is_sudah_checkin:
    st.warning(f"⚠️ Halo **{nama_karyawan}**, Anda belum Check-In.")
    if st.button("🟢 KLIK UNTUK CHECK-IN SEKARANG", use_container_width=True):
        # Logika Simpan Check-In ke GSheets
        waktu_skrg = get_waktu_wib()
        new_row = [waktu_skrg.strftime("%Y-%m-%d"), nama_karyawan, waktu_skrg.strftime("%H:%M:%S"), "", 0, "Mulai Shift"]
        df_to_save = conn.read(spreadsheet=URL_KITA, worksheet="Waktu Kerja", ttl=0)
        df_to_save.loc[len(df_to_save)] = new_row
        conn.update(spreadsheet=URL_KITA, worksheet="Waktu Kerja", data=df_to_save)
        
        st.success("Berhasil Check-In! Scanner Part Aktif.")
        st.cache_data.clear()
        st.rerun()

# LAYAR 3 & 4: SUDAH CHECK-IN (AREA PRODUKSI)
else:
    st.success(f"👷 Operator: **{nama_karyawan}** | Sesi Aktif")
    
    status_kerja = st.session_state.get('status_kerja', 'IDLE')

    # --- KONDISI: IDLE (Siap Scan Part Baru) ---
    if status_kerja == "IDLE":
        st.write("### 📸 Scan Barcode Part untuk Mulai")
        barcode_part = qrcode_scanner(key='scanner_part_prod')
        if barcode_part:
            st.session_state.barcode_input = barcode_part
            handle_scan()
        
        # TOMBOL CHECK-OUT MUNCUL DI SINI (Saat tidak sedang scan part)
        st.divider()
        st.write("Jika sudah selesai semua pekerjaan shift ini:")
        with st.popover("🔴 SELESAI SHIFT (CHECK-OUT)", use_container_width=True):
            st.write("### Konfirmasi Check-Out")
            st.warning("Apakah Anda yakin ingin mengakhiri shift sekarang?")

            # 1. Validasi: Cek apakah masih ada pekerjaan yang berstatus 'START'
            df_proses = conn.read(spreadsheet=URL_KITA, worksheet="Proses", ttl=0)
            pekerjaan_menggantung = df_proses[(df_proses['Nama'] == nama_karyawan) & (df_proses['Status'] == 'START')]

            if not pekerjaan_menggantung.empty:
                # Jika masih ada kerjaan yang belum di-FINISH
                part_no_aktif = pekerjaan_menggantung.iloc[0]['Part_No']
                st.error(f"❌ Tidak bisa Check-Out! Anda masih memiliki pekerjaan aktif pada Part: **{part_no_aktif}**. Silakan Finish-kan dulu.")
            else:
                # Jika semua sudah FINISH, baru tombol konfirmasi muncul
                st.success("✅ Semua pekerjaan sudah selesai.")
                if st.button("YA, SAYA YAKIN CHECK-OUT", type="primary", use_container_width=True):
                    with st.spinner("Memproses Check-Out..."):
                        waktu_out = get_waktu_wib()
                        df_waktu = conn.read(spreadsheet=URL_KITA, worksheet="Waktu Kerja", ttl=0)
                        row_idx = get_last_active_row(df_waktu, nama_karyawan)
                        tgl_hari_ini = waktu_out.strftime("%Y-%m-%d")

                        # Ambil data proses
                        df_proses = conn.read(spreadsheet=URL_KITA, worksheet="Proses", ttl=0)

                        # Filter: Cari semua kerjaan operator ini yang dilakukan HARI INI
                        summary_kerja = df_proses[
                            (df_proses['Nama'] == nama_karyawan) & 
                            (df_proses['Tanggal'] == tgl_hari_ini)
                        ]
                        # Buat ringkasan aktivitas kerja hari ini
                        if not summary_kerja.empty:
                            # Contoh hasil: "PART-A (100pcs), PART-B (50pcs)"
                            list_aktivitas = []
                            for _, row in summary_kerja.iterrows():
                                # Hanya masukkan yang sudah FINISH agar akurat
                                status_txt = "OK" if row['Status'] == "FINISH" else "PENDING"
                                list_aktivitas.append(f"{row['Part_No']} ({row['ACT']}pcs)-{status_txt}")

                            gabungan_aktivitas = " | ".join(list_aktivitas)
                        else:
                            gabungan_aktivitas = "Tidak ada aktivitas produksi"

                        df_waktu = conn.read(spreadsheet=URL_KITA, worksheet="Waktu Kerja", ttl=0)
                        row_idx = get_last_active_row(df_waktu, nama_karyawan)

                        if row_idx:
                            idx_pd = row_idx - 2
                            tgl_in = df_waktu.loc[idx_pd, 'Tanggal']
                            jam_in = df_waktu.loc[idx_pd, 'Check-In']

                            # Hitung Total Jam
                            dt_in = datetime.strptime(f"{tgl_in} {jam_in}", "%Y-%m-%d %H:%M:%S")
                            total_jam_shift = round((waktu_out - dt_in).total_seconds() / 3600, 2)

                            # Update GSheets
                            df_waktu.loc[idx_pd, 'Check-Out'] = waktu_out.strftime("%H:%M:%S")
                            df_waktu.loc[idx_pd, 'Total_Jam'] = total_jam_shift
                            df_waktu.loc[idx_pd, 'Aktivitas'] = gabungan_aktivitas
                            conn.update(spreadsheet=URL_KITA, worksheet="Waktu Kerja", data=df_waktu)

                            # Reset Sesi
                            st.session_state.nama_terpilih = ""
                            st.success("Check-Out Berhasil & Aktivitas Dirangkum!")
                            time.sleep(2)
                            st.rerun()
                        else:
                            st.sidebar.error("❌ Data Check-In tidak ditemukan untuk nama ini!")
            st.divider()
                 # 2. TOMBOL BACK / LOGOUT (Hanya Ganti Nama tanpa catat absen)
            if st.button("⬅️ Ganti Operator / Salah Scan Nama", use_container_width=True):
                # Pastikan tidak ada data current_part yang menggantung
                st.session_state.nama_terpilih = "" 
                # Bersihkan state lainnya jika perlu
                if 'status_kerja' in st.session_state: st.session_state.status_kerja = "IDLE"
                st.rerun()


    # --- KONDISI: SELECTING_PROCESS ---
    elif status_kerja == "SELECTING_PROCESS":
        if st.session_state.get('status_kerja') == "SELECTING_PROCESS":
            st.subheader("🔍 Pilih Urutan Proses")
            data_pilihan = st.session_state.get('available_processes', [])
            list_line = main_df['LINE'].unique().tolist() if 'LINE' in main_df.columns else []
        
        if data_pilihan:
            # Pilihan Actual Line
            actual_line = st.selectbox("Pilih Line Produksi (Actual Line)", options=list_line)
            # Tampilkan pilihan urutan proses berdasarkan part yang discan
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


    # --- KONDISI: RUNNING (Sedang Kerja) ---
    elif status_kerja == "RUNNING":
        dp = st.session_state.get('current_part')
        if dp:
            waktu_sekarang = get_waktu_wib()
            durasi_live = waktu_sekarang.replace(tzinfo=None) - st.session_state.waktu_start.replace(tzinfo=None)
            menit_live = int(durasi_live.total_seconds() / 60)
            jam_live = round(durasi_live.total_seconds() / 3600, 2)
            st.info(f"⚡ **Proses Berjalan:** {dp['part_name']} | sec_pcs : {dp['sec_pcs']} | {dp['model']}")
            
            col1, col2, col3, col4, col5 = st.columns(5)
            col1.metric("Urutan", dp['urutan_proses'])
            col2.metric("Target Sec/Pcs", dp['sec_pcs'])
            col3.metric("Mulai", st.session_state.waktu_start.strftime('%H:%M:%S'))
            col4.metric("Sudah Berjalan", f"{menit_live} Menit", delta=f"{jam_live} Jam")
            col5.metric("Actual Line", dp.get('Actual_Line', ''))

            st.divider()

            if not st.session_state.get('sudah_start_diklik'):
                st.write("### Langkah 1: Konfirmasi Mulai Kerja")

                if "is_submitting" not in st.session_state:
                    st.session_state.is_submitting = False
                if st.button("🚀 Konfirmasi Kirim Start", use_container_width=True, disabled=st.session_state.is_submitting):
                    st.session_state.is_submitting = True
                    data_start = {
                        "Tanggal": get_waktu_wib().strftime("%Y-%m-%d"),
                        "Nama": nama_karyawan,
                        "Part_No": dp['part_no'],
                        "Part_Name": dp['part_name'],
                        "Model": dp['model'],
                        "Line": dp['line'],
                        "Urutan_Proses": dp['urutan_proses'],
                        "Actual_Line": dp.get('Actual_Line', ""),
                        "Waktu_Mulai": st.session_state.waktu_start.strftime("%H:%M:%S"),
                        "Waktu_Selesai": "",
                        "ACT": 0, "NG": 0, "Status": "START"
                    }
                    with st.spinner("Sedang mencatat ke sistem..."):
                        if simpan_ke_sheet(data_start, "START"):
                            st.session_state.sudah_start_diklik = True # Tandai sudah start
                            st.session_state.status_kerja = "IDLE" # Reset ke IDLE untuk mencegah klik start lagi
                            if 'current_part' in st.session_state:
                                del st.session_state.current_part

                            st.session_state.is_submitting = False # Reset flag submit
                            st.balloons()
                            st.success("✅ Produksi Dimulai!")
                            time.sleep(1)
                            st.rerun()
                        else:
                            st.session_state.is_submitting = False # Reset jika gagal
                            st.error("❌ Gagal mencatat Start. Coba lagi!")

                    # --- BAGIAN B: JIKA SUDAH START (Muncul Scanner Finish) ---
                else:
                    st.write("### Langkah 2: Scan Barcode yang SAMA untuk FINISH")
                    barcode_data = qrcode_scanner(key='scanner_finish_part')
                    if barcode_data:
                        st.session_state.barcode_input = barcode_data
                        handle_scan() # Memproses perbandingan barcode di fungsi handle_sca

    # --- KONDISI: FINISHING (Input Hasil) ---
    elif status_kerja == "FINISHING":
        dp = st.session_state.get('current_part')
        if dp:
            st.subheader(f"📝 Laporan Akhir: {dp['part_name']}")
            
            waktu_start = st.session_state.get('waktu_start', get_waktu_wib())
            waktu_end = st.session_state.get('waktu_end', get_waktu_wib())
            durasi = waktu_end.replace(tzinfo=None) - waktu_start.replace(tzinfo=None)
            jam_total = round(durasi.total_seconds() / 60, 2)

            c1, c2, c3 = st.columns(3)
            act_raw = c1.text_input("Jumlah ACT", value="0")
            ng_raw = c2.text_input("Jumlah NG", value="0")
            try:
                act = int(act_raw)
                ng = int(ng_raw)
            except ValueError:
                act = 0
                ng = 0
            c3.metric("Durasi", f"{jam_total} Menit", delta=f"{round(jam_total/60, 2)} Jam")

            # --- LOGIKA POTONGAN ISTIRAHAT ---
            st.write("---")
            st.write("### ☕ Potongan Waktu Istirahat")
            st.caption("Pilih istirahat yang diambil selama pengerjaan part ini:")
            DAFTAR_BREAK = {
                "Break 1 (10m)": 10,
                "Break 2 (10m)": 10,
                "Istirahat (40m)": 40,
                "Extra Break (15m)": 15,
                "2S (15m)": 15
            }

            pilihan_break = st.multiselect("Pilih Istirahat yang diambil:", options=list(DAFTAR_BREAK.keys()))
            extra_custom = st.number_input("Istirahat Lainnya (Menit)", min_value=0, step=1, value=0)

            # Hitung total potongan
            total_potongan = sum([DAFTAR_BREAK[item] for item in pilihan_break]) + extra_custom

            # Kalkulasi SPH
            std_dari_state = float(st.session_state.current_part.get('sec_pcs', 0))
            standar_input = (dp['sec_pcs'] * act) / 60 if act > 0 else 0
            ## Dari sini Jam_Total dikurangi potongan istirahat
            durasi_bersih = max(0, jam_total - total_potongan)
            st.info(f"⏱️ **Durasi Bersih:** {durasi_bersih} Menit (Sudah dipotong {total_potongan} menit)")
            persen_prod = round((standar_input / durasi_bersih) * 100, 2) if durasi_bersih > 0 and std_dari_state > 0 else 0.0

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
                            "Total Istirahat": total_potongan,
                            "Rasio_NG": f"{(ng/act * 100) if act > 0 else 0:.2f}%",
                            "Total_Jam": f"{round(durasi_bersih/60, 2)}",
                            "Status": "FINISH"
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
            c2.metric("Total Jam", f"{round(durasi_bersih/60, 2)} Jam")
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
