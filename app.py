# app.py
import io
import os
import re
import time
import urllib.error
from datetime import datetime

import pandas as pd
import streamlit as st

# --- (선택) 쓰기 기능용 라이브러리: 서비스 계정이 있을 때만 사용 ---
HAS_SERVICE_ACCOUNT = False
try:
    from google.oauth2.service_account import Credentials
    import gspread
    HAS_SERVICE_ACCOUNT = True
except Exception:
    HAS_SERVICE_ACCOUNT = False

# =========================================================
# 설정 영역
# =========================================================

# 1) 스프레드시트 ID  (여기에 "한 개" ID를 넣으세요)
SPREADSHEET_ID = "1QQvBxuB1v8au2e7u22XzhZ9ov-SSQReutDGMKS31gvQ"

# 2) 각 시트의 gid (탭을 열면 URL 끝의 #gid=XXXXX 값)
GID_STUDENTS = "1030356842"   # 예: 학생명단
GID_LOGS     = "0"            # 예: 상담일지
GID_SCHOLAR  = "1878696825"   # 예: 장학금 지원

# 3) CSV Export Base
BASE = f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/export?format=csv&gid="

# 4) 상담일지 시트 이름(쓰기 모드에서 사용)
SHEET_NAME_LOGS = "상담일지"

# 5) 워드클라우드/키워드용 최소 토큰 길이/불용어(간단)
KOREAN_STOPWORDS = set([
    "이", "그", "저", "것", "수", "등", "들", "및", "제",
    "년", "월", "일", "시", "분", "초", "때", "경우", "때문",
    "사람", "문제", "내용", "정도", "자신", "생각", "말씀",
    "네", "예", "아니요", "음", "어", "아", "저기",
    "그래서", "그러나", "하지만", "그리고", "그런데",
    "좀", "더", "잘", "안", "못", "다", "또", "꼭",
    "참", "정말", "진짜", "너무", "아주", "매우"
])
PARTICLE_REGEX = re.compile(r"(은|는|이|가|을|를|의|에|에게|에서|로|으로|과|와|도|만|보다|처럼|까지|마저|조차|부터|이나|거나|하고|하며|해서|이다|입니다|있다|없다|됩니다|된|하는|있는|없는|적인)$")

# =========================================================
# 유틸 함수
# =========================================================

def csv_url(gid: str) -> str:
    return BASE + str(gid)

def _read_csv(url: str) -> pd.DataFrame:
    # 네트워크/권한 문제 대비: 재시도 + 친절한 에러 메시지
    last_err = None
    for _ in range(2):
        try:
            return pd.read_csv(url)
        except urllib.error.HTTPError as e:
            last_err = e
            time.sleep(0.6)
        except Exception as e:
            last_err = e
            break
    raise last_err

@st.cache_data(ttl=600, show_spinner="구글 시트에서 데이터를 불러오는 중…")
def load_data():
    students = _read_csv(csv_url(GID_STUDENTS))
    logs = _read_csv(csv_url(GID_LOGS))
    scholar = _read_csv(csv_url(GID_SCHOLAR))
    return students, logs, scholar

def has_service_account() -> bool:
    # st.secrets에 gcp_service_account가 있으면 True
    try:
        _ = st.secrets["gcp_service_account"]
        return True and HAS_SERVICE_ACCOUNT
    except Exception:
        return False

def append_log_to_sheet(row_values):
    """
    서비스 계정이 있을 때만 '상담일지' 시트에 행 추가.
    row_values: [타임스탬프, 장소, 학년, 반, 번호, 이름, 상담내용, 녹음파일 주소]
    """
    if not has_service_account():
        return False, "서비스 계정이 설정되지 않아, 현재는 로컬(읽기) 모드입니다."

    try:
        sa_info = dict(st.secrets["gcp_service_account"])
        # 구글 스프레드시트 접근 권한 범위
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
        creds = Credentials.from_service_account_info(sa_info, scopes=scopes)
        gc = gspread.authorize(creds)
        sh = gc.open_by_key(SPREADSHEET_ID)

        try:
            ws = sh.worksheet(SHEET_NAME_LOGS)
        except gspread.WorksheetNotFound:
            ws = sh.add_worksheet(title=SHEET_NAME_LOGS, rows=1000, cols=10)
            ws.append_row(["타임스탬프", "장소", "학년", "반", "번호", "이름", "상담내용", "녹음파일 주소"])

        ws.append_row(row_values)
        return True, "✅ 상담 일지가 시트에 저장되었습니다."
    except Exception as e:
        return False, f"❌ 저장 실패: {e}"

def parse_amount_to_max_per_year(amount_str: str) -> int:
    """
    '연 100~200만원', '월 20~50만원', '분기 최대 300만원' 등에서 대략적 '연간 최대 금액(만원)'을 추정
    """
    if not isinstance(amount_str, str):
        return 0
    nums = re.findall(r"\d+", amount_str)
    if not nums:
        return 0
    maxnum = max(int(n) for n in nums)
    # 단위 환산
    if "월" in amount_str:
        maxnum *= 12
    elif "분기" in amount_str:
        maxnum *= 4
    # '만원' 가정
    return maxnum

def process_text_for_keywords(text: str, topk: int = 20):
    if not isinstance(text, str) or not text.strip():
        return []
    # 간단 전처리
    text = re.sub(r"[^\w\s가-힣]", " ", text)
    tokens = [t for t in text.split() if len(t) >= 2]
    freq = {}
    for t in tokens:
        # 조사 제거
        t = PARTICLE_REGEX.sub("", t)
        if len(t) < 2: 
            continue
        if t in KOREAN_STOPWORDS:
            continue
        freq[t] = freq.get(t, 0) + 1
    # 상위 N개
    items = sorted(freq.items(), key=lambda x: x[1], reverse=True)[:topk]
    return items

def chips_html(items):
    # 키워드 chip 스타일 HTML
    html = []
    for w, _c in items:
        html.append(f"<span style='display:inline-block;margin:4px 6px;padding:6px 10px;border-radius:16px;background:#e3f2fd;color:#1976d2;font-weight:600'>#{w}</span>")
    return "".join(html)

# =========================================================
# UI
# =========================================================

st.set_page_config(page_title="상담 일지 시스템", layout="wide")

st.sidebar.title("📚 상담 관리")
menu = st.sidebar.radio("메뉴", ["일지 작성", "기록 보기", "전체 요약", "장학금 지원"], index=0)

# GID/ID 빠르게 바꿀 수 있게 사이드바에 표시(편집용)
with st.sidebar.expander("설정(관리자)"):
    st.caption("스프레드시트/시트 GID 확인용")
    st.write("Spreadsheet ID:", SPREADSHEET_ID)
    st.write("학생명단 gid:", GID_STUDENTS)
    st.write("상담일지 gid:", GID_LOGS)
    st.write("장학금 지원 gid:", GID_SCHOLAR)
    st.write("쓰기 가능(서비스계정):", "가능 ✅" if has_service_account() else "읽기 전용 📴")

# 데이터 로드
try:
    students_df, logs_df, scholar_df = load_data()
except Exception as e:
    st.error("❌ 데이터를 불러오지 못했습니다.")
    st.info(
        "확인해주세요:\n"
        "1) 스프레드시트가 '링크가 있는 모든 사용자(보기가능)'로 공유되어 있어야 합니다.\n"
        "2) 각 시트 gid가 맞는지 확인하세요.\n"
        "3) URL 형식은 다음과 같아야 합니다:\n"
        f"   https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/export?format=csv&gid=<GID>\n"
        f"에러: {e}"
    )
    st.stop()

# --- 학생명단 컬럼 표준화(예상 컬럼: 학년, 반, 번호, 이름) ---
expected_cols_students = ["학년", "반", "번호", "이름"]
missing_cols = [c for c in expected_cols_students if c not in students_df.columns]
if missing_cols:
    st.warning(f"학생명단 시트에 다음 컬럼이 필요합니다: {missing_cols}")

# --- 상담일지 표준화(예상 컬럼) ---
expected_cols_logs = ["타임스탬프", "장소", "학년", "반", "번호", "이름", "상담내용", "녹음파일 주소"]
for c in expected_cols_logs:
    if c not in logs_df.columns:
        logs_df[c] = ""  # 없으면 생성

# --- 장학금 지원: 금액 파싱 컬럼 준비 ---
if "maxAmount" not in scholar_df.columns:
    scholar_df["maxAmount"] = scholar_df.get("지원 금액(범위)", "").apply(parse_amount_to_max_per_year)

# =========================================================
# 화면: 일지 작성
# =========================================================
if menu == "일지 작성":
    st.header("📝 상담 일지 작성")
    col_left, col_right = st.columns([1, 1])

    # 학생 선택 (이름으로)
    with col_left:
        names = students_df.get("이름", pd.Series([], dtype=str)).dropna().unique().tolist()
        selected_name = st.selectbox("학생 선택(이름)", names, index=0 if names else None, placeholder="이름을 선택하세요")

        if selected_name:
            row = students_df[students_df["이름"] == selected_name].iloc[0]
            grade = row.get("학년", "")
            cls = row.get("반", "")
            num = row.get("번호", "")
        else:
            grade = cls = num = ""

        c1, c2, c3 = st.columns(3)
        with c1:
            st.text_input("학년", value=str(grade), disabled=True)
        with c2:
            st.text_input("반", value=str(cls), disabled=True)
        with c3:
            st.text_input("번호", value=str(num), disabled=True)

    with col_right:
        location = st.radio("상담 장소", ["교무실", "상담실1", "상담실2"], horizontal=True)
        content = st.text_area("상담 내용(직접 입력)", height=180, placeholder="상담 내용을 입력하세요…")

    # (옵션) 간편 음성 파일 업로드
    st.caption("🎙️ 선택: 음성 파일을 업로드할 수 있습니다(저장은 링크만 기록).")
    audio_file = st.file_uploader("오디오 업로드 (.mp3/.wav/.m4a/.webm 등)", type=["mp3", "wav", "m4a", "webm"], accept_multiple_files=False)

    # 실제 저장(쓰기) 또는 임시 추가(읽기 전용)
    if st.button("💾 일지 저장하기", use_container_width=True):
        if not selected_name:
            st.warning("학생을 선택해주세요.")
        else:
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            audio_url = ""
            if audio_file:
                # Streamlit Cloud엔 공용 파일서버가 없으므로 URL을 만들 수 없음.
                # 실제로 드라이브에 올리려면 서비스계정+Drive API 추가 구현 필요.
                # 여기선 파일명을 메모 형태로만 남깁니다.
                audio_url = f"(첨부 파일명: {audio_file.name})"

            row_vals = [ts, location, str(grade), str(cls), str(num), selected_name, content.strip(), audio_url]

            ok = False
            msg = ""
            if has_service_account():
                ok, msg = append_log_to_sheet(row_vals)
            else:
                msg = "현재는 읽기 전용 모드입니다. (서비스 계정이 설정되면 시트에 직접 저장됩니다.)"

            if ok:
                st.success(msg)
                # 캐시 무효화하여 '기록 보기' 탭 반영
                load_data.clear()
                students_df, logs_df, scholar_df = load_data()
            else:
                # 읽기 전용 모드에선 UI에서 임시 반영만
                st.info(msg)
                with st.expander("이번에 입력한 내용(미리보기)", expanded=True):
                    prev = pd.DataFrame([row_vals], columns=expected_cols_logs)
                    st.dataframe(prev, use_container_width=True)

# =========================================================
# 화면: 기록 보기
# =========================================================
elif menu == "기록 보기":
    st.header("📜 상담 기록 보기")

    names = students_df.get("이름", pd.Series([], dtype=str)).dropna().unique().tolist()
    sel_name = st.selectbox("학생 선택", names, index=0 if names else None)

    if sel_name:
        sub = logs_df[logs_df["이름"] == sel_name].copy()
        if not sub.empty:
            # 최신순으로
            try:
                sub["타임스탬프"] = pd.to_datetime(sub["타임스탬프"], errors="coerce")
            except Exception:
                pass
            sub = sub.sort_values(by="타임스탬프", ascending=False)
            st.dataframe(sub, use_container_width=True)

            # 키워드 간단 추출
            all_text = " ".join(sub.get("상담내용", pd.Series([], dtype=str)).dropna().tolist())
            items = process_text_for_keywords(all_text, topk=15)
            if items:
                st.markdown("**자주 등장한 키워드**")
                st.markdown(chips_html(items), unsafe_allow_html=True)
            else:
                st.info("텍스트에서 키워드를 추출할 수 없습니다.")
        else:
            st.info("저장된 상담 기록이 없습니다.")

# =========================================================
# 화면: 전체 요약
# =========================================================
elif menu == "전체 요약":
    st.header("📊 전체 상담 내용 요약")

    # 연/월 선택 (타임스탬프에서)
    logs_df["__ts"] = pd.to_datetime(logs_df["타임스탬프"], errors="coerce")
    years = sorted([int(y) for y in logs_df["__ts"].dt.year.dropna().unique().tolist()], reverse=True)
    year = st.selectbox("년도", years, index=0 if years else None)
    months = list(range(1, 13))
    month = st.selectbox("월", months, index=datetime.now().month - 1)

    if year and month:
        sub = logs_df[(logs_df["__ts"].dt.year == year) & (logs_df["__ts"].dt.month == month)]
        combined = " ".join(sub.get("상담내용", pd.Series([], dtype=str)).dropna().tolist())
        items = process_text_for_keywords(combined, topk=50)

        if items:
            st.markdown("**워드클라우드(간이) / 키워드 빈도 상위**")
            # 워드클라우드 라이브러리 없이, 간이 바차트 + 칩으로 대체
            top_items = items[:20]
            # 칩
            st.markdown(chips_html(top_items[:15]), unsafe_allow_html=True)
            # 바차트
            chart_df = pd.DataFrame(top_items, columns=["단어", "빈도"]).set_index("단어")
            st.bar_chart(chart_df)
        else:
            st.info("해당 기간 상담 기록이 없거나, 분석할 단어가 부족합니다.")

# =========================================================
# 화면: 장학금 지원
# =========================================================
elif menu == "장학금 지원":
    st.header("🎓 맞춤형 장학금 찾기")

    # 최소 금액(만원) 슬라이더
    min_amount = st.slider("희망 최소 지원 금액(연간, 만원)", 0, 1000, 0, step=10)
    scholar_df["maxAmount"] = pd.to_numeric(scholar_df["maxAmount"], errors="coerce").fillna(0).astype(int)
    filtered = scholar_df[scholar_df["maxAmount"] >= min_amount].copy()

    st.write(f"총 **{len(filtered)}**건의 장학금이 검색되었습니다.")
    # 보기 좋게 몇 컬럼만 노출
    display_cols = []
    for c in ["장학명", "운영 기관", "주요 대상", "선발 기준 / 필요 조건", "지원 금액(범위)", "신청 방식", "maxAmount"]:
        if c in filtered.columns:
            display_cols.append(c)
    if display_cols:
        st.dataframe(filtered[display_cols], use_container_width=True)
    else:
        st.dataframe(filtered, use_container_width=True)
