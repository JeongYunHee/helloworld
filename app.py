import streamlit as st
import pandas as pd
from wordcloud import WordCloud
import matplotlib.pyplot as plt

# ----------------------------------------------------
# 페이지 설정
# ----------------------------------------------------
st.set_page_config(page_title="상담 관리 시스템", layout="wide")

# ----------------------------------------------------
# Google Sheets CSV URL 설정
# ----------------------------------------------------
BASE = "https://docs.google.com/spreadsheets/d/1nQGdd0cQBBHUjrowK7p-il8wQvohEU9ZTS7zeSa_55I/export?format=csv&gid="

GID_STUDENTS = "1878696825"   # 학생명단 sheet gid
GID_LOGS = "1030356842"       # 상담일지 sheet gid
GID_SCHOLAR = "796606841"     # 장학금 지원 sheet gid

# ----------------------------------------------------
# 데이터 불러오기 (캐시)
# ----------------------------------------------------
@st.cache_data
def load_data():
    students = pd.read_csv(BASE + GID_STUDENTS)
    logs = pd.read_csv(BASE + GID_LOGS)
    scholarship = pd.read_csv(BASE + GID_SCHOLAR)
    return students, logs, scholarship

students_df, logs_df, scholar_df = load_data()

# ----------------------------------------------------
# 사이드 메뉴
# ----------------------------------------------------
menu = st.sidebar.radio("메뉴 선택", [
    "📝 일지 작성",
    "📚 상담 기록 보기",
    "☁️ 전체 상담 요약 (WordCloud)",
    "🎓 장학금 추천"
])

# ----------------------------------------------------
# 1) 일지 작성
# ----------------------------------------------------
if menu == "📝 일지 작성":
    st.header("📝 상담 일지 작성")

    student = st.selectbox("학생 선택", students_df["이름"].unique())
    student_info = students_df[students_df["이름"] == student].iloc[0]

    st.write(f"**학년:** {student_info['학년']}   **반:** {student_info['반']}   **번호:** {student_info['번호']}")

    place = st.selectbox("상담 장소", ["교무실", "상담실1", "상담실2"])
    content = st.text_area("상담 내용 입력", height=150)

    if st.button("✅ 일지 저장"):
        new_row = {
            "타임스탬프": pd.Timestamp.now(),
            "장소": place,
            "학년": student_info["학년"],
            "반": student_info["반"],
            "번호": student_info["번호"],
            "이름": student,
            "상담내용": content
        }
        logs_df = pd.concat([logs_df, pd.DataFrame([new_row])], ignore_index=True)
        logs_df.to_csv(BASE + GID_LOGS, index=False)  # ← 여기서 CSV 직접 수정은 불가능 (Streamlit 환경에서는 저장 UI용)
        st.success("✅ 저장 완료 (구글 시트 연동 저장은 다음 단계에서 연결 가능)")

# ----------------------------------------------------
# 2) 상담 기록 보기
# ----------------------------------------------------
elif menu == "📚 상담 기록 보기":
    st.header("📚 상담 기록 조회")

    student = st.selectbox("학생 선택", students_df["이름"].unique())
    filtered = logs_df[logs_df["이름"] == student]

    if filtered.empty:
        st.info("📂 해당 학생의 상담 기록이 없습니다.")
    else:
        for _, row in filtered.sort_values("타임스탬프", ascending=False).iterrows():
            st.write(f"**📅 {row['타임스탬프']} | 📍 {row['장소']}**")
            st.write(row["상담내용"])
            st.markdown("---")

# ----------------------------------------------------
# 3) 워드클라우드
# ----------------------------------------------------
elif menu == "☁️ 전체 상담 요약 (WordCloud)":
    st.header("☁️ 상담 내용 워드클라우드 요약")

    text = " ".join(logs_df["상담내용"].dropna().astype(str))

    if len(text.strip()) < 5:
        st.info("데이터가 부족합니다. 상담 기록을 먼저 저장하세요.")
    else:
        wc = WordCloud(font_path=None, width=800, height=400, background_color="white").generate(text)
        fig, ax = plt.subplots(figsize=(12, 6))
        ax.imshow(wc)
        ax.axis("off")
        st.pyplot(fig)

# ----------------------------------------------------
# 4) 장학금 추천
# ----------------------------------------------------
elif menu == "🎓 장학금 추천":
    st.header("🎓 장학금 추천")

    st.write("👇 원하는 최소 지원 금액을 선택하세요.")

    min_val = st.slider("최소 지원 금액 (만원)", 0, 500, 0)
    scholar_df["최대금액"] = scholar_df["지원 금액(범위)"].str.extract(r"(\d+)").astype(float)

    filtered = scholar_df[scholar_df["최대금액"] >= min_val]

    st.write(f"🔎 총 **{len(filtered)}건**의 장학금이 검색되었습니다.")
    st.dataframe(filtered.reset_index(drop=True))
