import streamlit as st
import textwrap
from PIL import Image, ImageDraw, ImageFont
import io
import zipfile

# ─────────────────── CONFIG ───────────────────
HEADER_FONT = './fonts/GoogleSans-Bold.ttf'
TEXT_FONT = './fonts/GoogleSans-Regular.ttf'
WM_FONT_SIZE = 26
WM_ALPHA = 130
FINAL_W, FINAL_H = 1080, 1350

# ─────────────────── HELPERS ───────────────────
def hex_to_rgb(hex_color):
    hex_color = hex_color.lstrip('#')
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))


def parse_slides(content):
    raw_blocks = content.split('---')
    slides = []
    for block in raw_blocks:
        block = block.strip()
        if not block:
            continue
        lines = block.split('\n')
        title = lines[0].strip()
        body = '\n'.join(l for l in lines[1:]).strip()
        slides.append({"title": title, "text": body})
    return slides


def prepare_bg(bg_file, darken_pct):
    inp = Image.open(bg_file).convert("RGB")
    w, h = inp.size
    ratio = FINAL_W / FINAL_H
    ir = w / h
    if ir > ratio:
        nw = int(h * ratio)
        left = (w - nw) // 2
        crop = inp.crop((left, 0, left + nw, h))
    else:
        nh = int(w / ratio)
        top = (h - nh) // 2
        crop = inp.crop((0, top, w, top + nh))
    base = crop.resize((FINAL_W, FINAL_H), Image.Resampling.LANCZOS).convert("RGBA")
    if darken_pct > 0:
        a = int(255 * darken_pct / 100)
        base.alpha_composite(Image.new('RGBA', (FINAL_W, FINAL_H), (0, 0, 0, a)))
    return base


def render_slide(slide, base_img, cfg):
    img = base_img.copy()
    draw = ImageDraw.Draw(img)

    hf, tf, wf = cfg['hf'], cfg['tf'], cfg['wf']
    color = cfg['color']

    h_wrap = max(10, int(1000 / cfg['hs']))
    t_wrap = max(15, int(1120 / cfg['ts']))

    h_lines = textwrap.wrap(slide['title'], width=h_wrap)
    paragraphs = slide['text'].split('\n')
    t_lines = []
    for p in paragraphs:
        p = p.strip()
        if p:
            t_lines.extend(textwrap.wrap(p, width=t_wrap))
        else:
            t_lines.append('')

    title_lh = int(cfg['hs'] * 1.2)
    text_lh = int(cfg['ts'] * 1.5)

    tx, ty = cfg['tx'], cfg['ty']
    cur_y = ty
    shadow = cfg['shadow']

    def draw_line(xy, text, font, fill):
        if shadow:
            draw.text((xy[0]+3, xy[1]+3), text, font=font, fill=(0, 0, 0, 128))
        draw.text(xy, text, font=font, fill=fill)

    for line in h_lines:
        draw_line((tx, cur_y), line, hf, color)
        cur_y += title_lh

    cur_y += cfg['gap']

    for line in t_lines:
        if line:
            draw_line((tx, cur_y), line, tf, color)
        cur_y += text_lh

    # watermark
    wm = cfg.get('wm')
    if wm and (wm['text'] or wm['avatar']):
        wm_text = wm['text']
        av_img = wm['avatar']
        av_sz = wm['av_size']

        bbox_w, bbox_h = 0, 0
        if wm_text:
            bb = draw.textbbox((0, 0), wm_text, font=wf)
            bbox_w = bb[2] - bb[0]
            bbox_h = bb[3] - bb[1]

        total_w = bbox_w + (av_sz + 12 if av_img else 0)
        block_h = max(bbox_h, av_sz if av_img else 0)

        wm_y = FINAL_H - 80 + wm['oy']

        if wm['pos'] == 'Слева':
            wm_x = 60 + wm['ox']
        elif wm['pos'] == 'Справа':
            wm_x = FINAL_W - total_w - 60 + wm['ox']
        else:
            wm_x = (FINAL_W - total_w) // 2 + wm['ox']

        cx = int(wm_x)

        if av_img and av_sz > 0:
            av = av_img.copy().resize((av_sz, av_sz), Image.Resampling.LANCZOS).convert("RGBA")
            mask = Image.new('L', (av_sz, av_sz), 0)
            ImageDraw.Draw(mask).ellipse((0, 0, av_sz-1, av_sz-1), fill=255)
            av.putalpha(mask)
            av_y = int(wm_y + (block_h - av_sz) // 2)
            img.alpha_composite(av, (cx, av_y))
            cx += av_sz + 12
            draw = ImageDraw.Draw(img)

        if wm_text:
            text_y = int(wm_y + (block_h - bbox_h) // 2)
            draw.text((cx, text_y), wm_text, font=wf, fill=(*color[:3], WM_ALPHA))

    return img.convert("RGB")


# ─────────────────── APP ───────────────────
st.set_page_config(page_title="Генератор Каруселей", page_icon="⬛", layout="wide")

st.markdown("""
<style>
    .block-container { padding-top: 2rem; }
    h1 { font-size: 1.6rem !important; margin-bottom: 0.3rem !important; }
    h3 { font-size: 1rem !important; margin-top: 1.2rem !important; margin-bottom: 0.4rem !important; }
    [data-testid="stHorizontalBlock"] > [data-testid="column"]:last-child {
        position: sticky;
        top: 2rem;
        align-self: flex-start;
    }
    section[data-testid="stSidebar"] { display: none; }
    .stSlider label { font-size: 0.85rem; }
</style>
""", unsafe_allow_html=True)

left, right = st.columns([1, 1], gap="large")

# ═══════════════ LEFT COLUMN ═══════════════
with left:
    st.title("Генератор Каруселей")

    # ── ФОНЫ ──
    st.markdown("### Фоны")
    uploaded_bgs = st.file_uploader(
        "Загрузи один или несколько фонов",
        type=['png', 'jpg', 'jpeg'],
        accept_multiple_files=True,
        label_visibility="collapsed"
    )

    bg_darken = st.slider("Затемнение фона", 0, 100, 0, format="%d%%")

    st.divider()

    # ── НИКНЕЙМ И АВАТАРКА ──
    st.markdown("### Никнейм")
    wm_text = st.text_input("Текст", value="", placeholder="@username")

    c1, c2 = st.columns(2)
    with c1:
        wm_pos = st.selectbox("Позиция", ["Слева", "По центру", "Справа"], index=0)
    with c2:
        wm_avatar_file = st.file_uploader("Аватарка", type=['png', 'jpg', 'jpeg'])

    c3, c4, c5 = st.columns(3)
    with c3:
        wm_av_size = st.slider("Размер аватарки", 20, 80, 40, step=2)
    with c4:
        wm_ox = st.slider("Сдвиг X", -200, 200, 0, step=5, key="wm_ox")
    with c5:
        wm_oy = st.slider("Сдвиг Y", -200, 200, 0, step=5, key="wm_oy")

    st.divider()

    # ── ТИПОГРАФИКА ──
    st.markdown("### Типографика")
    tc1, tc2 = st.columns(2)
    with tc1:
        text_color_hex = st.color_picker("Цвет текста", "#FFFFFF")
    with tc2:
        add_shadow = st.toggle("Тень текста", value=False)

    tc3, tc4 = st.columns(2)
    with tc3:
        header_size = st.slider("Заголовок", 30, 120, 70, step=2)
    with tc4:
        text_size = st.slider("Основной текст", 20, 80, 40, step=2)

    space_between = st.slider("Отступ заголовок → текст", 30, 250, 120, step=10)

    st.divider()

    # ── ПОЗИЦИЯ ТЕКСТА ──
    st.markdown("### Позиция текста")
    pc1, pc2 = st.columns(2)
    with pc1:
        text_x = st.slider("X (горизонталь)", 20, 500, 90, step=5)
    with pc2:
        text_y = st.slider("Y (вертикаль)", 50, 1100, 350, step=10)

    st.divider()

    # ── КОНТЕНТ ──
    st.markdown("### Контент")
    st.caption("Разделяй слайды через `---`. Первая строка блока – заголовок, остальное – текст. Пустые строки внутри блока = абзацы.")

    default_text = """ЗАГОЛОВОК 1
Текст первого слайда.

Второй абзац.
---
ЗАГОЛОВОК 2
Текст второго слайда.
---
ЗАГОЛОВОК 3
Текст третьего слайда."""

    text_input = st.text_area("Контент", value=default_text, height=280, label_visibility="collapsed")


# ═══════════════ RIGHT COLUMN ═══════════════
with right:
    st.markdown("### Превью")

    # Load fonts once
    try:
        hf = ImageFont.truetype(HEADER_FONT, header_size)
        tf = ImageFont.truetype(TEXT_FONT, text_size)
        wf = ImageFont.truetype(TEXT_FONT, WM_FONT_SIZE)
        fonts_ok = True
    except IOError:
        fonts_ok = False
        st.error("Шрифты не найдены в ./fonts/")

    # Prepare avatar
    avatar_img = None
    if wm_avatar_file:
        avatar_img = Image.open(wm_avatar_file).convert("RGBA")

    cfg = {
        'hf': hf if fonts_ok else None,
        'tf': tf if fonts_ok else None,
        'wf': wf if fonts_ok else None,
        'color': hex_to_rgb(text_color_hex),
        'hs': header_size,
        'ts': text_size,
        'tx': text_x,
        'ty': text_y,
        'gap': space_between,
        'shadow': add_shadow,
        'wm': {
            'text': wm_text,
            'pos': wm_pos,
            'ox': wm_ox,
            'oy': wm_oy,
            'avatar': avatar_img,
            'av_size': wm_av_size,
        }
    }

    slides_data = parse_slides(text_input) if text_input.strip() else []

    # ── LIVE PREVIEW ──
    if uploaded_bgs and fonts_ok and slides_data:
        bg = prepare_bg(uploaded_bgs[0], bg_darken)
        preview = render_slide(slides_data[0], bg, cfg)
        st.image(preview, use_container_width=True)
    elif not uploaded_bgs:
        st.info("Загрузи фон слева, чтобы увидеть превью")
    elif not slides_data:
        st.info("Добавь контент слева")

    st.divider()

    # ── GENERATE ALL ──
    btn_gen = st.button("Сгенерировать всю карусель", type="primary", use_container_width=True)

    if btn_gen:
        if not uploaded_bgs:
            st.error("Сначала загрузи фоны!")
        elif not slides_data:
            st.error("Добавь контент!")
        elif not fonts_ok:
            st.error("Шрифты не найдены!")
        else:
            with st.spinner("Генерация..."):
                images = []
                for i, slide in enumerate(slides_data):
                    bg_file = uploaded_bgs[i % len(uploaded_bgs)]
                    bg = prepare_bg(bg_file, bg_darken)
                    img = render_slide(slide, bg, cfg)
                    images.append(img)

            st.success(f"Готово – {len(images)} слайд(ов)")

            cols = st.columns(2)
            for idx, img in enumerate(images):
                cols[idx % 2].image(img, caption=f"Слайд {idx+1}", use_container_width=True)

            # ZIP
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "a", zipfile.ZIP_DEFLATED) as zf:
                for idx, img in enumerate(images):
                    b = io.BytesIO()
                    img.save(b, format='JPEG', quality=95)
                    zf.writestr(f"slide_{idx+1}.jpg", b.getvalue())

            st.download_button(
                "Скачать карусель (ZIP)",
                data=buf.getvalue(),
                file_name="carousel.zip",
                mime="application/zip",
                type="primary",
                use_container_width=True
            )
