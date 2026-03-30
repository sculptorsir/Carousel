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
# CONFIG
# ─────────────────────────────────────────────
HEADER_FONT_PATH = './fonts/GoogleSans-Bold.ttf'
BODY_FONT_PATH = './fonts/GoogleSans-Regular.ttf'
FW, FH = 1080, 1350
ACCENT = "#3B82F6"
ACCENT2 = "#2563EB"
SCROLL_H = 700  # Слегка уменьшил высоту окон, чтобы всё влезало без скролла страницы

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
# TEXT UTILS (Ювелирное выравнивание эмодзи)
# ─────────────────────────────────────────────
def hex_to_rgb(h):
    h = h.lstrip('#')
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))


def parse_rich_text(text):
    """Разбивает текст на сегменты (текст, жирный, эмодзи)"""
    # 1. Сначала ищем жирный текст *...*
    parts = re.split(r'(\*[^*]+\*)', text)
    segs = []
    
    for p in parts:
        if p.startswith('*') and p.endswith('*') and len(p) > 2:
            content = p[1:-1]
            segs.extend(_split_emoji_segs(content, is_bold=True))
        elif p:
            segs.extend(_split_emoji_segs(p, is_bold=False))
    return segs

def _split_emoji_segs(text, is_bold):
    """Внутри сегмента ищет эмодзи"""
    # Убираем Variation Selectors (\uFE0F), которые вызывают квадраты
    clean_text = text.replace('\uFE0F', '').replace('\uFE0E', '')
    
    # Регулярка для поиска эмодзи (простой вариант, покрывающий большинство)
    emoji_pattern = re.compile(r'([\U00010000-\U0010ffff\u2600-\u27bf\u2300-\u23ff\u2b50\u2b06\u2194-\u2199])')
    parts = emoji_pattern.split(clean_text)
    
    final_segs = []
    for p in parts:
        if not p: continue
        is_emoji = bool(emoji_pattern.match(p))
        final_segs.append({
            'text': p,
            'is_bold': is_bold,
            'is_emoji': is_emoji
        })
    return final_segs


def strip_markers(text):
    return text.replace('*', '')


def wrap_pixels_rich(text, font_reg, font_bold, max_w, draw, pmj):
    """Интеллектуальный перенос строк, учитывающий эмодзи и болд"""
    words = text.split(' ')
    if not words:
        return ['']
    
    lines = []
    cur_line_words = [words[0]]
    
    for w in words[1:]:
        test_line = ' '.join(cur_line_words + [w])
        # Заменяем пробелы на неразрывные для точного замера
        measure_text = test_line.replace(' ', '\u00A0')
        
        tw = _measure_rich_line_width(measure_text, font_reg, font_bold, draw, pmj)
            
        if tw <= max_w:
            cur_line_words.append(w)
        else:
            lines.append(' '.join(cur_line_words))
            cur_line_words = [w]
            
    lines.append(' '.join(cur_line_words))
    return lines

def _measure_rich_line_width(text, font_reg, font_bold, draw, pmj):
    """Замеряет ширину сложной строки"""
    segs = parse_rich_text(text)
    total_w = 0
    for seg in segs:
        font = font_bold if seg['is_bold'] else font_reg
        if seg['is_emoji'] and pmj:
            # Эмодзи замеряем через pilmoji, они чуть шире
            total_w += pmj.getsize(seg['text'], font=font)[0]
        else:
            total_w += draw.textlength(seg['text'], font=font)
    return total_w


def draw_rich_line_segmented(target, x, y, text, f_reg, f_bold, color, shadow, draw, pmj):
    """Отрисовывает строку сегмент за сегментом, выравнивая эмодзи по высоте"""
    segs = parse_rich_text(text)
    cx = x
    
    # Определяем визуальный центр шрифта (на сколько поднять эмодзи)
    # 0.35 - это эмпирический коэффициент для Google Sans, чтобы отцентровать по строке
    emoji_lift = int(f_reg.size * 0.35) 

    for seg in segs:
        font = f_bold if seg['is_bold'] else f_reg
        txt = seg['text']
        
        # Заменяем пробел на неразрывный во время отрисовки, чтобы он не пропадал
        render_txt = txt.replace(' ', '\u00A0')
        
        # Определяем Y-координату: текст на базовой линии, эмодзи приподнимаем
        render_y = y - emoji_lift if seg['is_emoji'] else y
        
        # 1. Тень
        if shadow:
            if pmj and seg['is_emoji']:
                pmj.text((cx + 3, render_y + 3), render_txt, font=font, fill=(0, 0, 0, 128))
            else:
                draw.text((cx + 3, render_y + 3), render_txt, font=font, fill=(0, 0, 0, 128))
        
        # 2. Основной текст
        if pmj and seg['is_emoji']:
            pmj.text((cx, render_y), render_txt, font=font, fill=color)
            adv = pmj.getsize(render_txt, font=font)[0]
        else:
            draw.text((cx, render_y), render_txt, font=font, fill=color)
            adv = draw.textlength(render_txt, font=font)
            
        cx += adv


# ─────────────────────────────────────────────
# SLIDES
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


def prepare_bg(f, darken):
    img = Image.open(f).convert("RGB")
    w, h = img.size
    r = FW / FH
    ir = w / h
    if ir > r:
        nw = int(h * r)
        lx = (w - nw) // 2
        c = img.crop((lx, 0, lx + nw, h))
    else:
        nh = int(w / r)
        ty = (h - nh) // 2
        c = img.crop((0, ty, w, ty + nh))
    base = c.resize((FW, FH), Image.Resampling.LANCZOS).convert("RGBA")
    if darken > 0:
        a = int(255 * darken / 100)
        base.alpha_composite(Image.new('RGBA', (FW, FH), (0, 0, 0, a)))
    return base


def render_slide(slide, base, cfg):
    img = base.copy()
    draw = ImageDraw.Draw(img)

    hf, tf, bf = cfg['hf'], cfg['tf'], cfg['bf']
    color = cfg['color']
    shadow = cfg['shadow']
    use_pm = cfg['use_pilmoji']

    # ВАЖНО: Убираем глобальный emoji_position_offset, 
    # так как теперь выравниваем каждый сегмент вручную в draw_rich_line_segmented
    pmj_context = Pilmoji(img) if (use_pm and HAS_PILMOJI) else None

    with ExitStack() as stack:
        pmj = stack.enter_context(pmj_context) if pmj_context else None

        # Перенос строк с учетом сложного контента
        h_lines = wrap_pixels_rich(slide['title'], hf, hf, cfg['hw'], draw, pmj)

        body_lines = []
        for para in slide['text'].split('\n'):
            para = para.strip()
            if para:
                body_lines.extend(wrap_pixels_rich(para, tf, bf, cfg['bw'], draw, pmj))
            else:
                body_lines.append('')

        title_lh = int(cfg['hs'] * cfg['h_spacing'])
        text_lh = int(cfg['ts'] * cfg['t_spacing'])

        tx, ty = cfg['tx'], cfg['ty']
        cur_y = ty

        # Отрисовка заголовка
        for line in h_lines:
            draw_rich_line_segmented(img, tx, cur_y, line, hf, hf, color, shadow, draw, pmj)
            cur_y += title_lh

        cur_y += cfg['gap']

        # Отрисовка тела
        for line in body_lines:
            if line:
                draw_rich_line_segmented(img, tx, cur_y, line, tf, bf, color, shadow, draw, pmj)
            cur_y += text_lh

        # Вотермарки
        for wm in cfg.get('wms', []):
            if wm and (wm['text'] or wm['avatar']):
                # Для вотермарок пока оставляем старый метод отрисовки, там эмодзи редкость
                _draw_wm_legacy(img, wm, color, draw, pmj)

    return img.convert("RGB")


def _draw_wm_legacy(img, wm, default_color, draw, pmj):
    """Старый метод отрисовки вотермарок (без посегментного выравнивания)"""
    wf = wm['font']
    if not wf:
        return
    alpha = wm['alpha']
    text = wm['text']
    av = wm['avatar']
    av_sz = wm['av_size']

    # Замер ширины через pilmoji (если есть)
    clean_text = text.replace('\uFE0F', '').replace('\uFE0E', '')
    measure_txt = clean_text.replace(' ', '\u00A0')
    if pmj:
        tw = pmj.getsize(measure_txt, font=wf)[0]
    else:
        tw = draw.textlength(measure_txt, font=wf)
        
    bb = draw.textbbox((0, 0), strip_markers(text), font=wf)
    th = bb[3] - bb[1]

    total_w = int(tw) + (av_sz + 12 if av else 0)
    bh = max(th, av_sz if av else 0)
    wy = FH - 80 + wm['oy']

    if wm['pos'] == 'Слева':
        wx = 60 + wm['ox']
    elif wm['pos'] == 'Справа':
        wx = FW - total_w - 60 + wm['ox']
    else:
        wx = (FW - total_w) // 2 + wm['ox']

    cx = int(wx)

    if av and av_sz > 0:
        a = av.copy().resize((av_sz, av_sz), Image.Resampling.LANCZOS).convert("RGBA")
        mask = Image.new('L', (av_sz, av_sz), 0)
        ImageDraw.Draw(mask).ellipse((0, 0, av_sz - 1, av_sz - 1), fill=255)
        a.putalpha(mask)
        ay = int(wy + (bh - av_sz) // 2)
        img.alpha_composite(a, (cx, ay))
        cx += av_sz + 12

    if text:
        ty = int(wy + (bh - th) // 2)
        fill = (*default_color[:3], alpha)
        
        # Тень вотермарка (без пилмоджи для простоты)
        draw.text((cx + 2, ty + 2), clean_text, font=wf, fill=(0, 0, 0, 70))
        
        if pmj:
            pmj.text((cx, ty), clean_text, font=wf, fill=fill)
        else:
            draw.text((cx, ty), clean_text, font=wf, fill=fill)


# ─────────────────────────────────────────────
# WATERMARK UI
# ─────────────────────────────────────────────
def wm_block(label, prefix):
    with st.container(border=True):
        st.markdown(f"### {label}")
        text = st.text_input("Текст", value="", placeholder="@username", key=f"{prefix}_t", label_visibility="collapsed")
        c1, c2 = st.columns(2)
        with c1:
            pos = st.selectbox("Позиция", ["Слева", "По центру", "Справа"], key=f"{prefix}_p")
        with c2:
            av_file = st.file_uploader("Аватарка", type=['png', 'jpg', 'jpeg'], key=f"{prefix}_a")
        c3, c4 = st.columns(2)
        with c3:
            av_sz = st.slider("Аватарка px", 20, 120, 44, step=2, key=f"{prefix}_as")
        with c4:
            fsz = st.slider("Размер текста", 14, 60, 26, step=1, key=f"{prefix}_fs")
        c5, c6, c7 = st.columns(3)
        with c5:
            alpha = st.slider("Прозрачность", 30, 255, 140, step=5, key=f"{prefix}_al")
        with c6:
            ox = st.slider("X", -300, 300, 0, step=5, key=f"{prefix}_ox")
        with c7:
            oy = st.slider("Y", -300, 300, 0, step=5, key=f"{prefix}_oy")

    av_img = None
    if av_file:
        av_img = Image.open(av_file).convert("RGBA")

    return {
        'text': text, 'pos': pos,
        'avatar': av_img, 'av_size': av_sz,
        'font_size': fsz, 'alpha': alpha,
        'ox': ox, 'oy': oy, 'font': None,
    }


# ─────────────────────────────────────────────
# LAYOUT
# ─────────────────────────────────────────────
left_col, right_col = st.columns([5, 4], gap="large")

# ═══════════════ LEFT ═══════════════
with left_col:
    with st.container(height=SCROLL_H):

        with st.container(border=True):
            st.markdown("### Фоны")
            uploaded_bgs = st.file_uploader(
                "bg", type=['png', 'jpg', 'jpeg'],
                accept_multiple_files=True, label_visibility="collapsed"
            )
            bg_darken = st.slider("Затемнение", 0, 100, 0, format="%d%%")

        wm1 = wm_block("Никнейм 1", "w1")
        wm2 = wm_block("Никнейм 2", "w2")

        with st.container(border=True):
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
                text_size = st.slider("Текст", 20, 80, 40, step=2)
            space_gap = st.slider("Отступ заголовок → текст", 10, 250, 100, step=10)

        with st.container(border=True):
            st.markdown("### Межстрочный интервал")
            lc1, lc2 = st.columns(2)
            with lc1:
                h_spacing = st.slider("Заголовок", 1.0, 2.5, 1.25, step=0.05, key="hsp")
            with lc2:
                t_spacing = st.slider("Текст", 1.0, 3.0, 1.55, step=0.05, key="tsp")

        with st.container(border=True):
            st.markdown("### Контейнер текста")
            kc1, kc2 = st.columns(2)
            with kc1:
                header_w = st.slider("Ширина заголовка", 300, 1040, 900, step=10)
            with kc2:
                body_w = st.slider("Ширина текста", 300, 1040, 900, step=10)
            pc1, pc2 = st.columns(2)
            with pc1:
                text_x = st.slider("Позиция X", 20, 500, 90, step=5)
            with pc2:
                text_y = st.slider("Позиция Y", 50, 1100, 350, step=10)

        with st.container(border=True):
            st.markdown("### Контент")
            st.caption("Слайды: `---` · 1-я строка = заголовок · `*жирный*` · пустая строка = абзац")
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

# ═══════════════ RIGHT ═══════════════
with right_col:
    with st.container(height=SCROLL_H):

        fonts_ok = True
        try:
            hf = ImageFont.truetype(HEADER_FONT_PATH, header_size)
            tf = ImageFont.truetype(BODY_FONT_PATH, text_size)
            # Болд для тела берем из жирного шрифта заголовка, но размером тела
            bf = ImageFont.truetype(HEADER_FONT_PATH, text_size)
        except IOError:
            fonts_ok = False
            st.error("Шрифты не найдены – GoogleSans-Bold.ttf / GoogleSans-Regular.ttf в ./fonts/")

        if fonts_ok:
            try:
                wm1['font'] = ImageFont.truetype(BODY_FONT_PATH, wm1['font_size'])
                wm2['font'] = ImageFont.truetype(BODY_FONT_PATH, wm2['font_size'])
            except IOError:
                pass

        use_pilmoji = HAS_PILMOJI
        if not HAS_PILMOJI:
            st.caption("⚡ `pip install pilmoji` – для эмодзи")

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
            'wms': [wm1, wm2],
        }

        slides_data = parse_slides(text_input) if text_input.strip() else []

        # ── PREVIEW (Чистый и компактный макет) ──
        with st.container(border=True):
            # Убрали заголовок "### Превью"
            if uploaded_bgs and fonts_ok and slides_data:
                bg = prepare_bg(uploaded_bgs[0], bg_darken)
                preview = render_slide(slides_data[0], bg, cfg)
                # Уменьшили превью, зафиксировав ширину (width=340)
                st.image(preview, width=340)
            elif not uploaded_bgs:
                st.info("← Загрузи фон")
            elif not slides_data:
                st.info("← Добавь контент")

        # ── GENERATE ──
        # Убрали лишние отступы, кнопка теперь выше
        btn = st.button("Сгенерировать карусель", type="primary", use_container_width=True)

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
                        bg = prepare_bg(uploaded_bgs[i % len(uploaded_bgs)], bg_darken)
                        images.append(render_slide(slide, bg, cfg))

                st.success(f"Готово – {len(images)} слайд(ов)")
                
                # Показываем результаты в скроллящейся области
                cols = st.columns(2)
                for idx, im in enumerate(images):
                    cols[idx % 2].image(im, caption=f"Слайд {idx+1}", use_container_width=True)

                buf = io.BytesIO()
                with zipfile.ZipFile(buf, "a", zipfile.ZIP_DEFLATED) as zf:
                    for idx, im in enumerate(images):
                        b = io.BytesIO()
                        im.save(b, format='JPEG', quality=95)
                        zf.writestr(f"slide_{idx+1}.jpg", b.getvalue())

                st.download_button(
                    "Скачать карусель (ZIP)",
                    data=buf.getvalue(),
                    file_name="carousel.zip",
                    mime="application/zip",
                    type="primary",
                    use_container_width=True,
                )
