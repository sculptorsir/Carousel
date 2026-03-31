import streamlit as st
from PIL import Image, ImageDraw, ImageFont
import io
import zipfile
import re
from contextlib import ExitStack

# ── pilmoji ──
try:
    from pilmoji import Pilmoji
    HAS_PILMOJI = True
except ImportError:
    HAS_PILMOJI = False

# ─────────────────────────────────────────────
# CONFIG & STATE INIT
# ─────────────────────────────────────────────
HEADER_FONT_PATH = './fonts/GoogleSans-Bold.ttf'
BODY_FONT_PATH = './fonts/GoogleSans-Regular.ttf'
FW, FH = 1080, 1350
ACCENT = "#3B82F6"
ACCENT2 = "#2563EB"
SCROLL_H = 780

if 'generated_images' not in st.session_state:
    st.session_state.generated_images = None
if 'zip_buffer' not in st.session_state:
    st.session_state.zip_buffer = None

# ─────────────────────────────────────────────
# CSS
# ─────────────────────────────────────────────
st.set_page_config(page_title="Carousel Gen", page_icon="⬛", layout="wide")

st.markdown(f"""
<style>
    .block-container {{
        padding-top: 0.6rem !important;
        padding-bottom: 0 !important;
    }}
    .stButton > button[kind="primary"],
    .stDownloadButton > button[kind="primary"],
    button[kind="primary"] {{
        background-color: {ACCENT} !important;
        border-color: {ACCENT} !important;
        color: white !important;
        font-weight: 600 !important;
        border-radius: 10px !important;
        padding: 0.5rem 1rem !important;
    }}
    .stButton > button[kind="primary"]:hover,
    .stDownloadButton > button[kind="primary"]:hover {{
        background-color: {ACCENT2} !important;
        border-color: {ACCENT2} !important;
    }}
    h3 {{
        font-size: 0.88rem !important;
        margin-top: 0.3rem !important;
        margin-bottom: 0.15rem !important;
        color: {ACCENT} !important;
        letter-spacing: 0.03em;
        text-transform: uppercase;
    }}
    div[data-testid="stVerticalBlock"] > div[data-testid="stVerticalBlockBorderWrapper"] {{
        border-radius: 12px !important;
        border-color: rgba(59,130,246,0.15) !important;
    }}
    .stSlider label {{ font-size: 0.8rem; }}
    .stCaption {{ font-size: 0.72rem !important; opacity: 0.65; }}
    header[data-testid="stHeader"] {{ display: none; }}
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────
# TEXT UTILS
# ─────────────────────────────────────────────
def hex_to_rgb(h):
    h = h.lstrip('#')
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))


def parse_bold(text):
    parts = re.split(r'(\*[^*]+\*)', text)
    segs = []
    for p in parts:
        if p.startswith('*') and p.endswith('*') and len(p) > 2:
            segs.append((p[1:-1], True))
        elif p:
            segs.append((p, False))
    return segs


def strip_markers(text):
    return text.replace('*', '')


def get_advance(d, text, font):
    clean = text.replace('\uFE0F', '').replace('\uFE0E', '')
    adv = 0
    buf = ""
    for c in clean:
        cp = ord(c)
        if cp >= 0x2600 or cp in (0x23E9, 0x23EA): 
            if buf:
                adv += d.textlength(buf.replace(' ', '\u00A0'), font=font)
                buf = ""
            adv += font.size * 1.15
        else:
            buf += c
    if buf:
        adv += d.textlength(buf.replace(' ', '\u00A0'), font=font)
    return adv


def wrap_pixels(text, font, max_w, draw):
    # Распределяем жирность для переноса по одному слову
    def distribute_bold(match):
        content = match.group(1)
        return ' '.join([f'*{w}*' for w in content.split()])
    
    processed_text = re.sub(r'\*([^*]+)\*', distribute_bold, text)
    words = processed_text.split()
    
    if not words:
        return ['']
    lines, cur = [], [words[0]]
    for w in words[1:]:
        test = strip_markers(' '.join(cur + [w]))
        tw = get_advance(draw, test.replace('\uFE0F', ''), font)
        if tw <= max_w:
            cur.append(w)
        else:
            lines.append(' '.join(cur))
            cur = [w]
    lines.append(' '.join(cur))
    return lines


def draw_rich_line(target, x, y, text, f_reg, f_bold, color, shadow, use_pilmoji, pmj_context):
    segs = parse_bold(text)
    cx = x
    d = ImageDraw.Draw(target)

    for txt, bold in segs:
        font = f_bold if bold else f_reg
        clean_txt = txt.replace('\uFE0F', '').replace('\uFE0E', '')
        if use_pilmoji and pmj_context:
            if shadow:
                pmj_context.text((cx + 3, y + 3), clean_txt, font=font, fill=(0, 0, 0, 128))
            pmj_context.text((cx, y), clean_txt, font=font, fill=color)
        else:
            if shadow:
                d.text((cx + 3, y + 3), clean_txt, font=font, fill=(0, 0, 0, 128))
            d.text((cx, y), clean_txt, font=font, fill=color)
            
        cx += get_advance(d, clean_txt, font)


# ─────────────────────────────────────────────
# CORE LOGIC
# ─────────────────────────────────────────────
def parse_slides(content):
    blocks = content.split('---')
    slides = []
    for b in blocks:
        b = b.strip()
        if not b:
            continue
        lines = b.split('\n')
        title = lines[0].strip()
        body = '\n'.join(lines[1:]).strip()
        slides.append({"title": title, "text": body})
    return slides


@st.cache_data(show_spinner=False)
def prepare_bg_cached(file_bytes, darken, final_w, final_h):
    img = Image.open(io.BytesIO(file_bytes)).convert("RGB")
    w, h = img.size
    r = final_w / final_h
    ir = w / h
    if ir > r:
        nw = int(h * r)
        lx = (w - nw) // 2
        c = img.crop((lx, 0, lx + nw, h))
    else:
        nh = int(w / r)
        ty = (h - nh) // 2
        c = img.crop((0, ty, w, ty + nh))
    base = c.resize((final_w, final_h), Image.Resampling.LANCZOS).convert("RGBA")
    if darken > 0:
        a = int(255 * darken / 100)
        base.alpha_composite(Image.new('RGBA', (final_w, final_h), (0, 0, 0, a)))
    return base


def _draw_logo(img, logo_bytes, size, x, y, alpha):
    logo = Image.open(io.BytesIO(logo_bytes)).convert("RGBA")
    w, h = logo.size
    ratio = size / float(w)
    new_h = int((float(h) * float(ratio)))
    logo = logo.resize((size, new_h), Image.Resampling.LANCZOS)

    if alpha < 255:
        r, g, b, a = logo.split()
        a = a.point(lambda p: int(p * (alpha / 255.0)))
        logo = Image.merge("RGBA", (r, g, b, a))

    img.alpha_composite(logo, (x, y))


def render_slide(slide, base, cfg):
    img = base.copy()
    draw = ImageDraw.Draw(img)

    hf, tf, bf = cfg['hf'], cfg['tf'], cfg['bf']
    color = cfg['color']
    shadow = cfg['shadow']
    use_pm = cfg['use_pilmoji']
    emoji_dy = cfg['emoji_dy']

    pmj_context = Pilmoji(img, emoji_position_offset=(0, emoji_dy)) if (use_pm and HAS_PILMOJI) else None

    with ExitStack() as stack:
        if pmj_context:
            stack.enter_context(pmj_context)

        h_lines = wrap_pixels(slide['title'], hf, cfg['hw'], draw)

        body_lines = []
        for para in slide['text'].split('\n'):
            para = para.strip()
            if para:
                body_lines.extend(wrap_pixels(para, tf, cfg['bw'], draw))
            else:
                body_lines.append('')

        title_lh = int(cfg['hs'] * cfg['h_spacing'])
        text_lh = int(cfg['ts'] * cfg['t_spacing'])

        tx, ty = cfg['tx'], cfg['ty']
        cur_y = ty

        for line in h_lines:
            draw_rich_line(img, tx, cur_y, line, hf, hf, color, shadow, use_pm, pmj_context)
            cur_y += title_lh

        cur_y += cfg['gap']

        for line in body_lines:
            if line:
                draw_rich_line(img, tx, cur_y, line, tf, bf, color, shadow, use_pm, pmj_context)
            cur_y += text_lh

        if cfg.get('logo_bytes'):
            _draw_logo(img, cfg['logo_bytes'], cfg['logo_size'], cfg['logo_x'], cfg['logo_y'], cfg['logo_alpha'])

    return img.convert("RGB")


# ─────────────────────────────────────────────
# LAYOUT
# ─────────────────────────────────────────────
left_col, right_col = st.columns([5, 4], gap="large")

with left_col:
    with st.container(height=SCROLL_H):

        with st.container(border=True):
            st.markdown("### Фоны")
            uploaded_bgs = st.file_uploader(
                "bg", type=['png', 'jpg', 'jpeg'],
                accept_multiple_files=True, label_visibility="collapsed"
            )
            bg_darken = st.slider("Затемнение", 0, 100, 0, format="%d%%")

        with st.container(border=True):
            st.markdown("### Логотип / Вотермарк")
            st.caption("Рекомендуется PNG с прозрачным фоном")
            logo_file = st.file_uploader("Логотип", type=['png', 'jpg', 'jpeg'], label_visibility="collapsed")
            
            lc_1, lc_2 = st.columns(2)
            with lc_1:
                # ОБНОВЛЕНЫ ДЕФОЛТНЫЕ ЗНАЧЕНИЯ ЛОГОТИПА
                logo_size = st.slider("Ширина (px)", 50, 800, 390, step=10)
            with lc_2:
                logo_alpha = st.slider("Прозрачность", 0, 255, 230, step=5)
                
            lc_3, lc_4 = st.columns(2)
            with lc_3:
                logo_x = st.slider("Позиция X (Лого)", -100, 1080, 90, step=10)
            with lc_4:
                logo_y = st.slider("Позиция Y (Лого)", -100, 1350, 1210, step=10)

        with st.container(border=True):
            st.markdown("### Типографика")
            tc1, tc2 = st.columns(2)
            with tc1:
                text_color_hex = st.color_picker("Цвет текста", "#FFFFFF")
            with tc2:
                add_shadow = st.toggle("Тень текста", value=False)
            tc3, tc4 = st.columns(2)
            with tc3:
                # ОБНОВЛЕНЫ ЗНАЧЕНИЯ ШРИФТОВ
                header_size = st.slider("Заголовок", 30, 120, 70, step=2)
            with tc4:
                text_size = st.slider("Текст", 20, 80, 40, step=2)
            
            # ОБНОВЛЕНЫ ОТСТУПЫ И ЭМОДЗИ
            space_gap = st.slider("Отступ заголовок → текст", 10, 250, 50, step=10)
            emoji_dy = st.slider("Высота эмодзи", -40, 40, -28, step=1)

        with st.container(border=True):
            st.markdown("### Межстрочный интервал")
            lc1, lc2 = st.columns(2)
            with lc1:
                # ОБНОВЛЕН ИНТЕРВАЛ
                h_spacing = st.slider("Заголовок", 1.0, 2.5, 1.25, step=0.05, key="hsp")
            with lc2:
                t_spacing = st.slider("Текст", 1.0, 3.0, 1.35, step=0.05, key="tsp")

        with st.container(border=True):
            st.markdown("### Контейнер текста")
            kc1, kc2 = st.columns(2)
            with kc1:
                # ОБНОВЛЕНА ШИРИНА
                header_w = st.slider("Ширина заголовка", 300, 1040, 800, step=10)
            with kc2:
                body_w = st.slider("Ширина текста", 300, 1040, 760, step=10)
            pc1, pc2 = st.columns(2)
            with pc1:
                # ОБНОВЛЕНЫ КООРДИНАТЫ
                text_x = st.slider("Позиция X", 20, 500, 90, step=5)
            with pc2:
                text_y = st.slider("Позиция Y", 50, 1100, 130, step=10)

        with st.container(border=True):
            st.markdown("### Контент")
            st.caption("Кликни мимо поля, чтобы обновить превью")
            default_text = """ЗАГОЛОВОК 1
Текст первого слайда. ⚡

Второй абзац с *жирным* словом.
---
ЗАГОЛОВОК 2
📌 *Сохрани*, чтобы вернуться.
💬 *Отправь* тому, кто грызет себя.
🔹 *Подписывайся* на Instagram.
---
ЗАГОЛОВОК 3
Текст третьего слайда."""
            text_input = st.text_area("c", value=default_text, height=220, label_visibility="collapsed")


with right_col:
    with st.container(height=SCROLL_H):

        fonts_ok = True
        try:
            hf = ImageFont.truetype(HEADER_FONT_PATH, header_size)
            tf = ImageFont.truetype(BODY_FONT_PATH, text_size)
            bf = ImageFont.truetype(HEADER_FONT_PATH, text_size)
        except IOError:
            fonts_ok = False
            st.error("Шрифты не найдены")

        use_pilmoji = HAS_PILMOJI
        if not HAS_PILMOJI:
            st.caption("Установи pilmoji для эмодзи")

        cfg = {
            'hf': hf if fonts_ok else None,
            'tf': tf if fonts_ok else None,
            'bf': bf if fonts_ok else None,
            'color': hex_to_rgb(text_color_hex),
            'hs': header_size, 'ts': text_size,
            'hw': header_w, 'bw': body_w,
            'tx': text_x, 'ty': text_y,
            'gap': space_gap,
            'shadow': add_shadow,
            'h_spacing': h_spacing,
            't_spacing': t_spacing,
            'use_pilmoji': use_pilmoji,
            'emoji_dy': emoji_dy,
            'logo_bytes': logo_file.getvalue() if logo_file else None,
            'logo_size': logo_size,
            'logo_alpha': logo_alpha,
            'logo_x': logo_x,
            'logo_y': logo_y
        }

        slides_data = parse_slides(text_input) if text_input.strip() else []

        st.write("") 
        if uploaded_bgs and fonts_ok and slides_data:
            bg = prepare_bg_cached(uploaded_bgs[0].getvalue(), bg_darken, FW, FH)
            preview = render_slide(slides_data[0], bg, cfg)
            
            pad_left, img_col, pad_right = st.columns([0.025, 0.95, 0.025])
            with img_col:
                st.image(preview, use_container_width=True)
        elif not uploaded_bgs:
            st.info("← Загрузи фон")
        elif not slides_data:
            st.info("← Добавь контент")

        st.write("---") 
        btn = st.button("🚀 Сгенерировать карусель", type="primary", use_container_width=True)

        if btn:
            if not uploaded_bgs:
                st.error("Загрузи фоны!")
            elif not slides_data:
                st.error("Добавь контент!")
            elif not fonts_ok:
                st.error("Шрифты!")
            else:
                with st.spinner("Генерация..."):
                    images = []
                    for i, slide in enumerate(slides_data):
                        bg = prepare_bg_cached(uploaded_bgs[i % len(uploaded_bgs)].getvalue(), bg_darken, FW, FH)
                        images.append(render_slide(slide, bg, cfg))

                st.session_state.generated_images = images

                buf = io.BytesIO()
                with zipfile.ZipFile(buf, "a", zipfile.ZIP_DEFLATED) as zf:
                    for idx, im in enumerate(images):
                        b = io.BytesIO()
                        im.save(b, format='PNG')
                        zf.writestr(f"{idx+1:02d}_slide.png", b.getvalue())

                st.session_state.zip_buffer = buf.getvalue()

        if st.session_state.generated_images:
            st.success(f"Готово – {len(st.session_state.generated_images)} слайд(ов)")
            
            cols = st.columns(2)
            for idx, im in enumerate(st.session_state.generated_images):
                cols[idx % 2].image(im, caption=f"Слайд {idx+1}", use_container_width=True)

            st.download_button(
                "📥 Скачать карусель (ZIP)",
                data=st.session_state.zip_buffer,
                file_name="carousel.zip",
                mime="application/zip",
                type="primary",
                use_container_width=True,
            )
