import html
import json
import os
import threading
import uuid
from datetime import datetime
from pathlib import Path

import streamlit as st

DATA_FILE = Path(__file__).parent / "data" / "items.json"
MAX_NAME = 50
MAX_QTY = 999

st.set_page_config(page_title="쇼핑리스트", page_icon="🛒", layout="centered")

# 파일이 단일 진실 공급원(source of truth)이다.
# 모든 변경은 "파일 읽기 → 수정 → 원자적 저장"을 락 안에서 수행하므로
# 여러 탭/세션이 동시에 써도 서로의 변경을 덮어쓰지 않는다.
_LOCK = threading.Lock()


# ---------- 저장/불러오기 ----------
def load_items():
    try:
        data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return [i for i in data if isinstance(i, dict) and {"id", "name", "qty", "done"} <= i.keys()]
    except (OSError, ValueError):
        pass
    return []


def update(fn):
    """최신 파일 내용에 fn(items)을 적용하고 저장한다. fn의 반환값(에러 메시지 등)을 돌려준다."""
    with _LOCK:
        items = load_items()
        result = fn(items)
        if result is None:  # 에러가 없을 때만 저장
            DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
            tmp = DATA_FILE.with_suffix(".tmp")
            tmp.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(tmp, DATA_FILE)
        return result


if "editing_id" not in st.session_state:
    st.session_state.editing_id = None
    st.session_state.flash = None


# ---------- 동작 ----------
def check(items, name, qty, exclude_id=None):
    """검증 후 (정리된 이름, 에러 메시지) 반환."""
    name = (name or "").strip()
    if not name:
        return None, "이름을 입력해 주세요."
    if len(name) > MAX_NAME:
        return None, f"이름은 {MAX_NAME}자 이하로 입력해 주세요."
    # not (a <= qty <= b) 형태라 NaN/inf도 여기서 걸러진다
    if qty is None or not (1 <= qty <= MAX_QTY):
        return None, f"수량은 1 이상 {MAX_QTY} 이하로 입력해 주세요."
    if qty != int(qty):
        return None, "수량은 정수만 입력할 수 있어요."
    # 중복 이름은 거부 (대소문자 무시)
    for it in items:
        if it["id"] != exclude_id and it["name"].lower() == name.lower():
            return None, f"'{name}'은(는) 이미 목록에 있어요."
    return name, None


def flash(err):
    if err:
        st.session_state.flash = ("warning", err)
    return err


def add_item(name, qty):
    def fn(items):
        clean, err = check(items, name, qty)
        if err:
            return err
        items.append(
            {
                "id": str(uuid.uuid4()),
                "name": clean,
                "qty": int(qty),
                "done": False,
                "created_at": datetime.now().isoformat(timespec="seconds"),
            }
        )

    return flash(update(fn))


def toggle(item_id):
    value = st.session_state[f"chk_{item_id}"]

    def fn(items):
        for it in items:
            if it["id"] == item_id:
                it["done"] = value

    update(fn)


def delete_item(item_id):
    def fn(items):
        items[:] = [i for i in items if i["id"] != item_id]

    update(fn)
    if st.session_state.editing_id == item_id:
        st.session_state.editing_id = None


def start_edit(item_id):
    for it in load_items():
        if it["id"] == item_id:
            st.session_state.editing_id = item_id
            st.session_state[f"name_{item_id}"] = it["name"]
            st.session_state[f"qty_{item_id}"] = float(it["qty"])


def cancel_edit():
    st.session_state.editing_id = None


def save_edit(item_id):
    name = st.session_state[f"name_{item_id}"]
    qty = st.session_state[f"qty_{item_id}"]

    def fn(items):
        clean, err = check(items, name, qty, exclude_id=item_id)
        if err:
            return err
        for it in items:
            if it["id"] == item_id:
                it["name"] = clean
                it["qty"] = int(qty)
                return None
        return "다른 곳에서 이미 삭제된 항목이에요."

    if not flash(update(fn)):
        st.session_state.editing_id = None


def clear_done():
    def fn(items):
        items[:] = [i for i in items if not i["done"]]

    update(fn)


# ---------- 스타일 ----------
st.markdown(
    """
<style>
.block-container {max-width: 640px; padding-top: 2rem;}
h1 {text-align: center;}
.item-name {font-size: 1.05rem; word-break: break-word;}
.item-name.done {text-decoration: line-through; opacity: .5;}
.pill {display:inline-block; margin-left:.5rem; padding:.05rem .6rem; border-radius:999px;
       background: rgba(255,75,75,.15); font-size:.85rem; font-weight:600; white-space:nowrap;}
.empty {text-align:center; padding:2.5rem 0; opacity:.6;}
/* 터치하기 쉬운 최소 높이 44px */
div[data-testid="stButton"] button,
div[data-testid="stFormSubmitButton"] button,
[data-testid="stButtonGroup"] button {min-height: 2.75rem;}
[class*="st-key-row_"] [data-testid="stCheckbox"] label {
    min-width: 2.75rem; min-height: 2.75rem; display: flex; align-items: center; justify-content: center;
}
/* Streamlit 기본 푸터 정리 (Deploy 버튼/메뉴는 .streamlit/config.toml의 toolbarMode로 숨김) */
footer {visibility: hidden;}

/* 항목 행: 모바일에서도 [체크 | 이름 | ✏️ | 🗑️] 한 줄 유지 (기본값은 세로로 쌓임) */
[class*="st-key-row_"] [data-testid="stHorizontalBlock"] {
    flex-wrap: nowrap !important; gap: .4rem !important; align-items: center;
}
[class*="st-key-row_"] [data-testid="stColumn"] {
    min-width: 0 !important; width: auto !important; flex: 0 0 auto !important;
}
[class*="st-key-row_"] [data-testid="stColumn"]:nth-child(2) {flex: 1 1 0 !important;}
[class*="st-key-row_"] [data-testid="stButton"] button {
    min-width: 2.75rem; padding: .25rem .5rem;
}
/* 아이콘 버튼: 텍스트 라벨("수정"/"삭제")은 시각적으로만 숨기고 스크린리더에는 남긴다 */
[class*="st-key-edit_"] button p, [class*="st-key-del_"] button p {
    position: absolute; width: 1px; height: 1px; margin: -1px; padding: 0;
    overflow: hidden; clip: rect(0, 0, 0, 0); white-space: nowrap; border: 0;
}
/* 진행 바 색을 버튼/배지의 포인트 컬러와 통일 */
[data-testid="stProgressBarTrack"] > div {background-color: #ff4b4b !important;}
</style>
""",
    unsafe_allow_html=True,
)

# ---------- 화면 ----------
st.title("🛒 쇼핑리스트")

if st.session_state.flash:
    kind, msg = st.session_state.flash
    getattr(st, kind)(msg)
    st.session_state.flash = None

with st.form("add_form", clear_on_submit=True, border=True):
    c1, c2, c3 = st.columns([5, 2, 2], vertical_alignment="bottom")
    new_name = c1.text_input("아이템", placeholder="예: 우유", max_chars=MAX_NAME)
    # min_value를 두지 않는다: 0을 넣어도 조용히 막히지 않고 check()가 경고를 보여준다.
    # 소수를 입력해도 조용히 잘리지 않도록 float로 받고 check()에서 정수 여부를 검증한다.
    new_qty = c2.number_input("수량", value=1.0, step=1.0, format="%g")
    submitted = c3.form_submit_button("추가", use_container_width=True, type="primary")
    if submitted:
        add_item(new_name, new_qty)
        st.rerun()

items = load_items()
total = len(items)
done_cnt = sum(i["done"] for i in items)

if total:
    st.progress(done_cnt / total, text=f"{done_cnt} / {total} 완료")
    if done_cnt == total:
        st.success("모두 담았어요! 🎉")

flt = st.segmented_control("보기", ["전체", "미완료", "완료"], default="전체", label_visibility="collapsed")
flt = flt or "전체"
visible = [i for i in items if flt == "전체" or (flt == "완료") == i["done"]]

if not visible:
    msg = "아직 담은 물건이 없어요" if not total else "해당하는 항목이 없어요"
    st.markdown(f'<div class="empty">🧺<br>{msg}</div>', unsafe_allow_html=True)

for it in visible:
    iid = it["id"]
    if st.session_state.editing_id == iid:
        # st.form: 이름 입력창에서 Enter를 누르면 첫 번째 버튼(저장)이 실행된다.
        with st.form(f"editform_{iid}", border=True):
            e1, e2 = st.columns([4, 1.5])
            e1.text_input("이름", key=f"name_{iid}", max_chars=MAX_NAME)
            e2.number_input("수량", step=1.0, format="%g", key=f"qty_{iid}")
            b1, b2 = st.columns(2)
            b1.form_submit_button("💾 저장", on_click=save_edit, args=(iid,), use_container_width=True, type="primary")
            b2.form_submit_button("취소", on_click=cancel_edit, use_container_width=True)
    else:
        with st.container(border=True, key=f"row_{iid}"):
            c1, c2, c3, c4 = st.columns([0.6, 5, 1, 1], vertical_alignment="center")
            c1.checkbox(f"{it['name']} 완료", value=it["done"], key=f"chk_{iid}", on_change=toggle, args=(iid,), label_visibility="collapsed")
            # st.html은 마크다운/수식/:emoji: 해석을 하지 않는다 → 사용자 입력이 링크·서식으로 변하지 않음
            cls = "item-name done" if it["done"] else "item-name"
            c2.html(f'<span class="{cls}">{html.escape(it["name"])}</span><span class="pill">x{int(it["qty"])}</span>')
            c3.button("수정", icon=":material/edit:", key=f"edit_{iid}", on_click=start_edit, args=(iid,), help="수정")
            c4.button("삭제", icon=":material/delete:", key=f"del_{iid}", on_click=delete_item, args=(iid,), help="삭제")

if total:
    st.button("완료 항목 삭제", on_click=clear_done, disabled=done_cnt == 0, use_container_width=True)
