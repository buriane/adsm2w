import re
import io
from datetime import datetime, timedelta

import pandas as pd
import streamlit as st

st.set_page_config(page_title="Rekap Pengajuan M2W", page_icon="📊", layout="wide")

# ============================================================
# KONSTANTA
# ============================================================

BOT_NUMBER = "+62 813-3050-3034"

# ============================================================
# FUNGSI PARSING
# ============================================================

TS_PATTERN = re.compile(
    r'^\[?(\d{1,2}/\d{1,2}/\d{2,4}),\s*'
    r'(\d{1,2}[.:]\d{2}(?:[.:]\d{2})?\s?(?:[APap][Mm])?)\]?\s*[-\u2013]?\s*'
    r'([^:\n]+):\s*',
    re.MULTILINE
)


def parse_datetime(date_str: str, time_str: str, date_format: str = "MDY"):
    date_str = date_str.replace(".", "/")
    time_str = time_str.replace(".", ":").strip()
    time_str = re.sub(r'\s+', ' ', time_str)

    if date_format == "MDY":
        date_fmts = ("%m/%d/%y", "%m/%d/%Y")
    else:
        date_fmts = ("%d/%m/%y", "%d/%m/%Y")

    time_fmts = ("%I:%M:%S %p", "%I:%M %p", "%H:%M:%S", "%H:%M")

    for dfmt in date_fmts:
        for tfmt in time_fmts:
            try:
                return datetime.strptime(f"{date_str} {time_str}", f"{dfmt} {tfmt}")
            except ValueError:
                continue
    return None


def normalize_text(text: str) -> str:
    """Bersihkan karakter tak-terlihat yang sering disisipkan WhatsApp export
    (zero-width mark, narrow no-break space) yang bikin regex timestamp gagal cocok."""
    text = text.replace("\u200e", "").replace("\u200f", "").replace("\ufeff", "")
    text = text.replace("\u202f", " ")  # narrow no-break space -> spasi biasa
    return text


def split_messages(raw_text: str, date_format: str = "MDY"):
    matches = list(TS_PATTERN.finditer(raw_text))
    messages = []
    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(raw_text)
        isi = raw_text[start:end].strip()
        waktu = parse_datetime(m.group(1), m.group(2), date_format)
        messages.append({"waktu": waktu, "pengirim": m.group(3).strip(), "isi": isi})
    return messages


def extract_field(block: str, label: str):
    match = re.search(rf'\*{label}:\*[ \t]*([^\n🏢👤🏍️📅📍🔗🏷️🎯]*)', block)
    return match.group(1).strip() if match else ""


def filter_by_sender(messages, sender: str):
    return [m for m in messages if m["pengirim"].strip() == sender]


def filter_by_window(messages, start_dt: datetime, end_dt: datetime):
    return [m for m in messages if m["waktu"] and start_dt <= m["waktu"] <= end_dt]


def process_pengajuan(messages):
    pengajuan_list = []
    for m in messages:
        isi = m["isi"]
        if not (isi.startswith("🆕") and "Pengajuan" in isi):
            continue
        jenis_match = re.search(r'Pengajuan\s+(\S+)\s+Baru', isi)
        jenis = jenis_match.group(1) if jenis_match else ""
        if jenis != "M2W":
            continue

        pengajuan_list.append({
            "Waktu": m["waktu"].strftime("%d/%m/%Y %H:%M") if m["waktu"] else "",
            "Cabang": extract_field(isi, "Cabang"),
            "Nama": extract_field(isi, "Nama"),
            "Jaminan": extract_field(isi, "Jaminan"),
            "Tenor/Pencairan": extract_field(isi, "Tenor/Pencairan"),
            "Kota Domisili": extract_field(isi, "Kota Domisili"),
            "Link Admin": extract_field(isi, "Link Admin"),
        })
    return pengajuan_list


def process_chat_masuk(messages):
    chat_list = []
    for m in messages:
        isi = m["isi"]
        if not isi.startswith("💬"):
            continue

        kategori = extract_field(isi, "Kategori")
        prospek = extract_field(isi, "Prospek")

        chat_list.append({
            "Waktu": m["waktu"].strftime("%d/%m/%Y %H:%M") if m["waktu"] else "",
            "Customer": extract_field(isi, "Customer"),
            "Kategori": kategori,
            "Prospek": prospek,
            "Link": extract_field(isi, "Link"),
        })
    return chat_list


def df_to_csv_bytes(df: pd.DataFrame) -> bytes:
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    return buf.getvalue().encode("utf-8-sig")


# ============================================================
# UI - SIDEBAR
# ============================================================

st.title("📊 Rekap Pengajuan M2W - Chat Masuk ADS")
st.caption("Upload hasil export chat WhatsApp (.txt)")

with st.sidebar:
    st.header("⚙️ Pengaturan")

    uploaded_file = st.file_uploader("Upload file export chat (.txt)", type=["txt"])

    st.subheader("Format Tanggal di File")
    date_format_label = st.radio(
        "Sesuaikan dengan format",
        options=["MM/DD/YY", "DD/MM/YY"],
        index=0,
    )
    date_format = "MDY" if date_format_label.startswith("MM/DD") else "DMY"

    st.subheader("Rentang Sesi")
    tanggal_sesi = st.date_input("Tanggal mulai sesi", value=datetime.now().date())
    col1, col2 = st.columns(2)
    with col1:
        jam_mulai = st.time_input("Jam mulai", value=datetime.strptime("20:00", "%H:%M").time())
    with col2:
        jam_selesai = st.time_input("Jam selesai (h+1)", value=datetime.strptime("07:00", "%H:%M").time())

    proses = st.button("🚀 Proses", type="primary", use_container_width=True)

# ============================================================
# PROSES & TAMPILKAN HASIL
# ============================================================

if proses:
    if uploaded_file is None:
        st.warning("Silakan upload file .txt terlebih dahulu di sidebar.")
        st.stop()

    raw_text = uploaded_file.read().decode("utf-8", errors="ignore")
    raw_text = normalize_text(raw_text)

    start_dt = datetime.combine(tanggal_sesi, jam_mulai)
    end_dt = datetime.combine(tanggal_sesi, jam_selesai) + timedelta(days=1)

    all_messages = split_messages(raw_text, date_format)
    bot_messages = filter_by_sender(all_messages, BOT_NUMBER)
    messages_in_window = filter_by_window(bot_messages, start_dt, end_dt)

    pengajuan = process_pengajuan(messages_in_window)
    chat_masuk = process_chat_masuk(messages_in_window)

    st.success(f"Sesi: **{start_dt.strftime('%d/%m/%Y %H:%M')}** s/d **{end_dt.strftime('%d/%m/%Y %H:%M')}**")

    # Ringkasan angka
    per_prospek = {"Hot": 0, "Warm": 0, "Cold": 0, "Blank": 0}
    for c in chat_masuk:
        p = c["Prospek"]
        if p in ("Hot", "Warm", "Cold"):
            per_prospek[p] += 1
        else:
            per_prospek["Blank"] += 1

    m1, m2, m3, m4, m5, m6 = st.columns(6)
    m1.metric("Total Pesan Bot", len(messages_in_window))
    m2.metric("Total Chat Masuk", len(chat_masuk))
    m3.metric("🔥 Hot", per_prospek["Hot"])
    m4.metric("🌤️ Warm", per_prospek["Warm"])
    m5.metric("❄️ Cold", per_prospek["Cold"])
    m6.metric("⬜ Blank", per_prospek["Blank"])

    st.divider()

    # Tab: Pengajuan & Chat Masuk
    tab1, tab2 = st.tabs(["🆕 Pengajuan M2W", "💬 Chat Masuk (Prospek)"])

    with tab1:
        if pengajuan:
            df_pengajuan = pd.DataFrame(pengajuan)

            st.subheader("Rekap per Cabang")
            rekap_cabang = df_pengajuan["Cabang"].value_counts().reset_index()
            rekap_cabang.columns = ["Cabang", "Jumlah"]
            st.dataframe(rekap_cabang, use_container_width=True, hide_index=True)

            st.subheader("Detail Pengajuan")
            st.dataframe(df_pengajuan, use_container_width=True, hide_index=True)

            st.download_button(
                "⬇️ Download CSV Pengajuan",
                data=df_to_csv_bytes(df_pengajuan),
                file_name=f"rekap_pengajuan_m2w_{tanggal_sesi}.csv",
                mime="text/csv",
            )
        else:
            st.info("Tidak ada pengajuan M2W dalam rentang waktu ini.")

    with tab2:
        if chat_masuk:
            df_chat = pd.DataFrame(chat_masuk)

            st.subheader("Rekap per Prospek")
            rekap_prospek = pd.DataFrame(
                {"Prospek": list(per_prospek.keys()), "Jumlah": list(per_prospek.values())}
            )
            st.dataframe(rekap_prospek, use_container_width=True, hide_index=True)

            st.subheader("Detail Chat Masuk")
            st.dataframe(df_chat, use_container_width=True, hide_index=True)

            st.download_button(
                "⬇️ Download CSV Chat Masuk",
                data=df_to_csv_bytes(df_chat),
                file_name=f"rekap_chat_masuk_m2w_{tanggal_sesi}.csv",
                mime="text/csv",
            )
        else:
            st.info("Tidak ada chat masuk M2W dalam rentang waktu ini.")

else:
    st.info("⬅️ Upload file dan atur rentang waktu di sidebar, lalu klik **Proses**.")
