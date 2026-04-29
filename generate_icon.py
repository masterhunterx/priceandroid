"""Genera el icono de FreshCart (carrito + rayo) en todos los tamaños Android."""
from PIL import Image, ImageDraw
import os

BG_DARK    = (13, 17, 23)
GREEN      = (34, 197, 94)
GREEN_DARK = (21, 128, 61)
YELLOW     = (253, 224, 71)
YELLOW_DK  = (161, 98, 7)
WHITE      = (255, 255, 255)
GRAY       = (156, 163, 175)

def draw_rounded_rect(draw, x0, y0, x1, y1, r, fill):
    draw.rectangle([x0+r, y0, x1-r, y1], fill=fill)
    draw.rectangle([x0, y0+r, x1, y1-r], fill=fill)
    for cx, cy in [(x0+r, y0+r), (x1-r, y0+r), (x0+r, y1-r), (x1-r, y1-r)]:
        draw.ellipse([cx-r, cy-r, cx+r, cy+r], fill=fill)

def make_icon(size):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    s = size

    # Fondo redondeado
    r_bg = int(s * 0.20)
    draw_rounded_rect(d, 0, 0, s, s, r_bg, BG_DARK)

    # --- Carrito de supermercado ---
    # Medidas proporcionales
    m = s * 0.10          # margen lateral
    top = s * 0.18        # top del basket
    bot = s * 0.62        # bottom del basket
    lft = m               # izquierda
    rgt = s - m           # derecha
    t   = max(2, int(s * 0.055))  # grosor lineas

    # Basket (trapecio verde relleno, mas ancho abajo)
    trap_top_off = s * 0.06
    basket = [
        (lft + trap_top_off, top),
        (rgt - trap_top_off, top),
        (rgt, bot),
        (lft, bot),
    ]
    d.polygon(basket, fill=GREEN)

    # Borde blanco del basket
    d.line([
        (lft + trap_top_off, top),
        (rgt - trap_top_off, top),
        (rgt, bot),
        (lft, bot),
        (lft + trap_top_off, top),
    ], fill=WHITE, width=t)

    # Handle (manija) - arco superior
    hx0 = s * 0.32
    hx1 = s * 0.68
    hy_bot = top
    hy_top = s * 0.10
    handle_t = max(2, int(t * 0.9))
    # Arco como dos verticales + horizontal
    d.line([(hx0, hy_bot), (hx0, hy_top)], fill=WHITE, width=handle_t)
    d.line([(hx0, hy_top), (hx1, hy_top)], fill=WHITE, width=handle_t)
    d.line([(hx1, hy_top), (hx1, hy_bot)], fill=WHITE, width=handle_t)

    # Lineas horizontales dentro del basket (efecto rejilla)
    n_lines = 2
    for i in range(1, n_lines + 1):
        frac = i / (n_lines + 1)
        ly = top + (bot - top) * frac
        lx_l = lft + trap_top_off * (1 - frac)
        lx_r = rgt - trap_top_off * (1 - frac)
        d.line([(lx_l, ly), (lx_r, ly)], fill=GREEN_DARK, width=max(1, t//2))

    # Ruedas
    wr = int(s * 0.075)
    wy = bot + wr * 1.3
    for wx in [s * 0.27, s * 0.73]:
        d.ellipse([wx-wr, wy-wr, wx+wr, wy+wr], fill=WHITE)
        d.ellipse([wx-wr*0.42, wy-wr*0.42, wx+wr*0.42, wy+wr*0.42], fill=BG_DARK)

    # --- Rayo centrado sobre el basket ---
    bx = s * 0.50   # centro x
    zt = top - s*0.01          # top del rayo (toca el borde del basket)
    zb = bot + s*0.01          # bottom del rayo
    zh = zb - zt               # altura total
    zw = s * 0.19              # semi-ancho

    bolt = [
        (bx + zw*0.30,  zt),               # top-right
        (bx - zw*0.55,  zt + zh*0.50),     # mid-left
        (bx + zw*0.08,  zt + zh*0.45),     # mid-center
        (bx - zw*0.30,  zb),               # bottom-left
        (bx + zw*0.55,  zt + zh*0.52),     # mid-right
        (bx - zw*0.05,  zt + zh*0.57),     # mid-center-2
    ]

    # Sombra
    sh = [(x + s*0.015, y + s*0.015) for x, y in bolt]
    d.polygon(sh, fill=(0, 0, 0, 100))
    # Rayo principal
    d.polygon(bolt, fill=YELLOW)
    # Borde oscuro
    d.line(bolt + [bolt[0]], fill=YELLOW_DK, width=max(1, int(s*0.012)))

    return img

def make_round(size):
    base = make_icon(size)
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse([0, 0, size-1, size-1], fill=255)
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    out.paste(base, mask=mask)
    return out

# Tamaños normales (ic_launcher.png, ic_launcher_round.png)
SIZES = {
    "mipmap-mdpi":    48,
    "mipmap-hdpi":    72,
    "mipmap-xhdpi":   96,
    "mipmap-xxhdpi":  144,
    "mipmap-xxxhdpi": 192,
}

# Tamaños adaptive icon foreground (108dp equivalente en cada densidad)
# El foreground es 108dp; el contenido debe quedar en el centro 72dp (safe zone).
ADAPTIVE_SIZES = {
    "mipmap-mdpi":    108,
    "mipmap-hdpi":    162,
    "mipmap-xhdpi":   216,
    "mipmap-xxhdpi":  324,
    "mipmap-xxxhdpi": 432,
}

BASE = r"c:\Users\Cris\Desktop\Nueva carpeta\frontend\freshcart---smart-grocery-assistant\android\app\src\main\res"

def make_foreground(adaptive_size):
    """Ícono centrado en la safe zone (66.7%) sobre fondo transparente."""
    icon_size = int(adaptive_size * 72 / 108)  # safe zone
    icon = make_icon(icon_size)
    canvas = Image.new("RGBA", (adaptive_size, adaptive_size), (0, 0, 0, 0))
    offset = (adaptive_size - icon_size) // 2
    canvas.paste(icon, (offset, offset))
    return canvas

for folder, size in SIZES.items():
    path = os.path.join(BASE, folder)
    os.makedirs(path, exist_ok=True)
    make_icon(size).convert("RGB").save(os.path.join(path, "ic_launcher.png"))
    make_round(size).save(os.path.join(path, "ic_launcher_round.png"))

    # Adaptive icon foreground (reemplaza el X azul de Capacitor)
    fg_size = ADAPTIVE_SIZES[folder]
    make_foreground(fg_size).save(os.path.join(path, "ic_launcher_foreground.png"))
    print(f"  {folder}: {size}px normal, {fg_size}px foreground OK")

# Preview grande
make_icon(512).save(r"c:\Users\Cris\Desktop\Nueva carpeta\freshcart_icon_preview.png")
print("Listo! Preview en freshcart_icon_preview.png")
