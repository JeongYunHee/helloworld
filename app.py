import streamlit as st
import pandas as pd
from datetime import datetime
from wordcloud import WordCloud
import matplotlib.pyplot as plt
import os

st.set_page_config(page_title="상담 관리 시스템", layout="wide")

# 파일 경로
STUDENTS_FILE = "students.csv"
LOGS_FILE = "counseling_logs.csv"
SCHOLAR_FILE = "scholarships.csv"

# 학생 목록 불러오기
students = pd.read_csv(STUDENTS_FILE)

# 상담 기록 파일 생성 없으면 생성
if not os.path.exists(LOGS_FILE):
    pd.DataFrame(columns=["타임스탬프","장소","학년","반","번호","이름","상담내용","녹음파일"]).to_csv(LOGS_FILE, index=False)

logs = pd.read_csv(LOGS_FILE)


# --------------------------------------------------
# 메뉴 UI
# --------------------------------------------------
menu = st.sidebar.radio("메뉴 선택", ["일지 작성", "기록 보기", "전체 요약 (워드클라우드)", "장학금 추천"])


# --------------------------------------------------
# 1) 상담 일지 작성
# --------------------------------------------------
if menu == "일지 작성":
    st.header("📝 상담 일지 작성")

    name_input = st.text_input("학생 이름 검색")

    matches = students[students["이름"].str.contains(name_input)] if name_input else pd.DataFrame()

    if len(matches) > 0:
        student = matches.iloc[0]
        st.write(f"➡️ **{student['학년']}학년 {student['반']}반 {student['번호']}번 {student['이름']}** 선택됨")

        location = st.radio("상담 장소", ["교무실", "상담실1", "상담실2"])
        text = st.text_area("상담 내용 입력")

        if st.button("💾 저장하기"):
            new_row = {
                "타임스탬프": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "장소": location,
                "학년": student["학년"],
                "반": student["반"],
                "번호": student["번호"],
                "이름": student["이름"],
                "상담내용": text,
                "녹음파일": ""
            }
            logs = logs.append(new_row, ignore_index=True)
            logs.to_csv(LOGS_FILE, index=False)
            st.success("✅ 상담 기록 저장 완료!")


# --------------------------------------------------
# 2) 상담 기록 보기
# --------------------------------------------------
elif menu == "기록 보기":
    st.header("📚 상담 기록 조회")

    name = st.selectbox("학생 선택", sorted(students["이름"].unique()))

    student_logs = logs[logs["이름"] == name]

    if len(student_logs) == 0:
        st.info("📭 상담 기록 없음")
    else:
        for _, row in student_logs.iloc[::-1].iterrows():
            st.write(f"**[{row['타임스탬프']}]** | **{row['장소']}**")
            st.write(row["상담내용"])
            st.markdown("---")


# --------------------------------------------------
# 3) 워드클라우드
# --------------------------------------------------
elif menu == "전체 요약 (워드클라우드)":
    st.header("🔍 상담 내용 키워드 요약 (WordCloud)")

    text_data = " ".join(logs["상담내용"].astype(str))

    if text_data.strip():
        wc = WordCloud(width=800, height=400, background_color="white").generate(text_data)
        fig, ax = plt.subplots(figsize=(10,6))
        ax.imshow(wc); ax.axis("off")
        st.pyplot(fig)
    else:
        st.info("📭 상담 내용이 아직 없습니다.")


# --------------------------------------------------
# 4) 장학금 추천
# --------------------------------------------------
elif menu == "장학금 추천":
    st.header("💰 장학금 추천")

    scholar = pd.read_csv(SCHOLAR_FILE)

    min_amount = st.slider("최소 희망 금액 (만원)", 0, 500, 0)

    filtered = scholar[scholar["지원 금액(범위)"].str.contains(str(min_amount)) | (min_amount == 0)]

    st.write(f"🔎 총 **{len(filtered)}건** 검색됨")

    for _, row in filtered.iterrows():
        st.subheader(row["장학명"])
        st.write(row["운영 기관"])
        st.write(row["주요 대상"])
        st.write(f"💰 {row['지원 금액(범위)']}")
        st.write(f"📝 {row['신청 방식']}")
        st.markdown("---")
