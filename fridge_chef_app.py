import streamlit as st
import datetime
import pandas as pd
import sqlite3
import altair as alt
import re
from openai import OpenAI

# ---------------- 基础配置 ----------------
st.set_page_config(page_title="🥕 冰箱里的魔法营养厨师 PRO", page_icon="🥗", layout="wide")
st.title("🥕 冰箱里的魔法营养厨师 PRO")

DAILY_GOALS = {"calories": 2000, "protein": 100, "carbs": 250}
client = OpenAI(base_url="http://localhost:11434/v1", api_key="ollama")

# ---------------- 数据库 ----------------
def init_db():
    conn = sqlite3.connect("meals.db")
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS meals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT,
            meal_type TEXT,
            recipe TEXT,
            calories INTEGER,
            protein INTEGER,
            carbs INTEGER
        )
    """)
    conn.commit()
    conn.close()

def save_meal(date, meal_type, recipe, nutrition):
    conn = sqlite3.connect("meals.db"); c = conn.cursor()
    c.execute("INSERT INTO meals (date, meal_type, recipe, calories, protein, carbs) VALUES (?,?,?,?,?,?)",
              (date, meal_type, recipe, nutrition["calories"], nutrition["protein"], nutrition["carbs"]))
    conn.commit(); conn.close()

def get_meals_by_date(date):
    conn = sqlite3.connect("meals.db"); c=conn.cursor()
    c.execute("SELECT id, meal_type, recipe, calories, protein, carbs FROM meals WHERE date=? ORDER BY meal_type",(date,))
    rows=c.fetchall(); conn.close()
    return pd.DataFrame(rows, columns=["id","餐次","菜谱","calories","protein","carbs"])

def get_totals(days=7):
    conn=sqlite3.connect("meals.db"); c=conn.cursor()
    c.execute("""
        SELECT date, SUM(calories), SUM(protein), SUM(carbs)
        FROM meals
        WHERE date >= date('now', ?)
        GROUP BY date
        ORDER BY date
    """,(f"-{days} day",))
    rows=c.fetchall(); conn.close()
    return pd.DataFrame(rows, columns=["日期","calories","protein","carbs"])

def delete_meal(record_id):
    conn=sqlite3.connect("meals.db"); c=conn.cursor()
    c.execute("DELETE FROM meals WHERE id=?", (record_id,))
    conn.commit(); conn.close()

def update_calories(record_id,new_cals):
    conn=sqlite3.connect("meals.db"); c=conn.cursor()
    c.execute("UPDATE meals SET calories=? WHERE id=?", (new_cals,record_id))
    conn.commit(); conn.close()

# ---------------- LLM生成 ----------------
def generate_meal(model, meal_name, ingredients):
    prompt=f"""
    你是一位营养厨师。请用以下食材设计一份 {meal_name} 菜谱：
    食材: {', '.join(ingredients)}。

    输出格式：
    - 菜名
    - 简单做法
    - 营养估算 (热量 kcal, 蛋白质 g, 碳水 g)
    """
    resp=client.chat.completions.create(model=model,messages=[{"role":"user","content":prompt}],temperature=0.7)
    return resp.choices[0].message.content

def extract_nutrition(text):
    nutri={"calories":0,"protein":0,"carbs":0}
    cal=re.search(r'(\d+)\s*k?cal', text.lower())
    pro=re.search(r'(\d+)\s*g.*蛋白', text.lower())
    carb=re.search(r'(\d+)\s*g.*(碳水|carb)', text.lower())
    if cal:nutri["calories"]=int(cal.group(1))
    if pro:nutri["protein"]=int(pro.group(1))
    if carb:nutri["carbs"]=int(carb.group(1))
    return nutri

# ---------------- 初始化 ----------------
init_db(); today=datetime.date.today().isoformat()

# ---------------- 界面Tabs ----------------
tab1,tab2,tab3 = st.tabs(["🍽️ 今日饮食","📊 趋势分析","📤 数据导出"])

# ----- Tab1 今日饮食 -----
with tab1:
    st.subheader("🥗 输入三餐食材，生成 & 保存")
    model_choice=st.selectbox("选择本地模型",["llama3","mistral"])
    col1,col2,col3=st.columns(3)
    breakfast_ing=col1.text_input("早餐食材","燕麦 牛奶 鸡蛋")
    lunch_ing=col2.text_input("午餐食材","米饭 西红柿 鸡蛋")
    dinner_ing=col3.text_input("晚餐食材","鱼 豆腐 蔬菜")

    if st.button("✨ 生成并保存今日三餐"):
        for meal,ing in {"早餐":breakfast_ing.split(),"午餐":lunch_ing.split(),"晚餐":dinner_ing.split()}.items():
            reply=generate_meal(model_choice, meal, ing)
            nutrition=extract_nutrition(reply)
            save_meal(today, meal, reply, nutrition)
        st.success("今日三餐已生成保存 ✅")
        st.rerun()

    st.subheader("🍳 今日饮食记录")
    df_today=get_meals_by_date(today)
    if not df_today.empty:
        for _,row in df_today.iterrows():
            with st.expander(f"{row['餐次']} | {row['calories']} kcal"):
                st.write(f"**菜谱:** {row['菜谱']}")
                st.write(f"蛋白质: {row['protein']} g | 碳水: {row['carbs']} g")

                new_cals=st.number_input(f"修改热量 - {row['餐次']}", value=int(row["calories"]), key=f"cal{row['id']}")
                if st.button(f"保存修改 {row['餐次']}", key=f"upd{row['id']}"):
                    update_calories(row["id"], new_cals)
                    st.success("修改成功 ✅"); st.rerun()

                if st.button(f"🗑 删除 {row['餐次']}", key=f"del{row['id']}"):
                    delete_meal(row["id"])
                    st.warning(f"{row['餐次']} 已删除"); st.rerun()

        # 总营养
        st.subheader("📊 今日合计")
        total=df_today[["calories","protein","carbs"]].sum()
        col1,col2,col3=st.columns(3)
        for i,(nutrient, goal) in enumerate(DAILY_GOALS.items()):
            val,diff=total[i],total[i]-goal
            with [col1,col2,col3][i]:
                st.metric(nutrient,f"{val}/{goal}",f"{diff:+}")
                st.progress(min(val/goal,1.0))
    else:
        st.info("暂无记录 🍽️")

# ----- Tab2 趋势分析 -----
with tab2:
    st.subheader("📈 最近一周营养趋势")
    df_week=get_totals(7)
    if not df_week.empty:
        df_week["日期"]=pd.to_datetime(df_week["日期"])
        df_melt=df_week.melt("日期",var_name="营养",value_name="数值")
        base=alt.Chart(df_melt).mark_line(point=True).encode(x="日期",y="数值",color="营养")
        goal_df=pd.DataFrame([{"营养":"calories","目标":2000},{"营养":"protein","目标":100},{"营养":"carbs","目标":250}])
        goal_line=alt.Chart(goal_df).mark_rule(strokeDash=[5,5],color="red").encode(y="目标")
        st.altair_chart(base+goal_line,use_container_width=True)

        def score(row):
            s=0
            for k,g in DAILY_GOALS.items():
                diff=abs(row[k]-g)/g
                if diff<=0.1:s+=100
                elif diff<=0.2:s+=80
                else:s+=60
            return round(s/3)
        df_week["健康评分"]=df_week.apply(score,axis=1)
        st.bar_chart(df_week.set_index("日期")["健康评分"])
        st.success(f"近7天均分: {round(df_week['健康评分'].mean(),1)} / 100")
    else:
        st.info("暂无历史数据 📭")

# ----- Tab3 数据导出 -----
with tab3:
    st.subheader("📤 导出饮食记录")
    mode=st.radio("范围",["最近7天","最近30天","自定义"])
    if mode=="最近7天": start=(datetime.date.today()-datetime.timedelta(days=7)).isoformat(); end=datetime.date.today().isoformat()
    elif mode=="最近30天": start=(datetime.date.today()-datetime.timedelta(days=30)).isoformat(); end=datetime.date.today().isoformat()
    else:
        c1,c2=st.columns(2)
        start=c1.date_input("开始日期",datetime.date.today()-datetime.timedelta(days=7)).isoformat()
        end=c2.date_input("结束日期",datetime.date.today()).isoformat()

    if st.button("📥 导出CSV"):
        conn=sqlite3.connect("meals.db"); c=conn.cursor()
        c.execute("SELECT date,meal_type,recipe,calories,protein,carbs FROM meals WHERE date BETWEEN ? AND ? ORDER BY date,meal_type",(start,end))
        rows=c.fetchall(); conn.close()
        if rows:
            df_log=pd.DataFrame(rows,columns=["日期","餐次","菜谱","热量(kcal)","蛋白质(g)","碳水(g)"])
            st.dataframe(df_log)
            csv=df_log.to_csv(index=False).encode("utf-8")
            st.download_button("下载CSV",csv,f"nutrition_{start}_to_{end}.csv","text/csv")
        else: st.warning("该区间无记录 📭")