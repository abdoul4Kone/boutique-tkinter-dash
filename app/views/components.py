"""Identité visuelle et dispositions adaptatives de la boutique."""
from tkinter import messagebox
from functools import lru_cache
import customtkinter as ctk
from PIL import Image, ImageOps, ImageDraw
from app.config import ASSETS_DIR
from app.navigation import open_page
from app.accounts import SessionManager
from app.credits import project_credits


class Style:
    bg = '#F6F5F1'
    paper = '#FFFFFF'
    ink = '#172F39'
    blue = '#245BEA'
    muted = '#596B72'
    line = '#E3E6E3'
    green = '#146854'
    soft = '#EAF0FF'
    sand = '#EEEAE1'


def font(size=14, weight='normal'):
    return ('Segoe UI', size, weight)


def logical_width(widget):
    scale = widget._get_widget_scaling() if hasattr(widget, '_get_widget_scaling') else 1
    return widget.winfo_width() / scale


class ResizeObserver:
    """Regrouper les redimensionnements sans recréer les champs saisis."""
    def __init__(self, widget, callback):
        self.widget, self.callback = widget, callback
        self.pending, self.last_width = None, None
        widget.bind('<Configure>', self.schedule, add='+')
        widget.bind('<Destroy>', self.close, add='+')
        self.schedule()

    def schedule(self, event=None):
        if self.pending:
            self.widget.after_cancel(self.pending)
        self.pending = self.widget.after(75, self.apply)

    def apply(self):
        self.pending = None
        if not self.widget.winfo_exists():
            return
        width = round(logical_width(self.widget))
        if width > 10 and width != self.last_width:
            self.last_width = width
            self.callback(width)

    def close(self, event):
        if event.widget in (self.widget, getattr(self.widget, '_canvas', None)) and self.pending:
            self.widget.after_cancel(self.pending)
            self.pending = None


def setup_window(window, title):
    ctk.set_appearance_mode('light')
    window.title(title + ' - Group9 Store')
    width, height = min(1320, window.winfo_screenwidth()-60), min(880, window.winfo_screenheight()-90)
    if not hasattr(window, '_app_controller'):
        window.geometry(f'{width}x{height}+25+25')
    window.minsize(min(640, width), min(480, height))
    window.configure(**({'fg_color': Style.bg} if isinstance(window, ctk.CTk) else {'bg': Style.bg}))
    window.grid_columnconfigure(0, weight=1)
    window.grid_rowconfigure(1, weight=1)


def label(master, text='', size=14, weight='normal', color=None, **kwargs):
    return ctk.CTkLabel(master, text=text, font=font(size, weight), text_color=color or Style.ink, **kwargs)


def button(master, text, command, kind='primary', **kwargs):
    colors = {'primary': (Style.blue, '#1747C7', '#FFFFFF'), 'secondary': (Style.ink, '#284652', '#FFFFFF'),
              'light': (Style.soft, '#DAE5FF', '#1646C3'), 'nav': (Style.ink, '#284652', '#FFFFFF')}
    fill, hover, ink = colors[kind]
    defaults = dict(height=44, corner_radius=11, font=font(13, 'bold'), fg_color=fill, hover_color=hover, text_color=ink)
    defaults.update(kwargs)
    return ctk.CTkButton(master, text=text, command=command, **defaults)


def panel(master, **kwargs):
    defaults = dict(fg_color=Style.paper, corner_radius=18, border_color=Style.line, border_width=1)
    defaults.update(kwargs)
    return ctk.CTkFrame(master, **defaults)


def field(master, title, placeholder='', row=0, column=0, show=None):
    group = ctk.CTkFrame(master, fg_color='transparent')
    group.grid(row=row, column=column, sticky='ew', padx=12, pady=8)
    group.grid_columnconfigure(0, weight=1)
    label(group, title, 12, 'bold', wraplength=245, anchor='w', justify='left').grid(row=0, column=0, sticky='w', pady=(0, 7))
    entry = ctk.CTkEntry(group, placeholder_text=placeholder, height=43, corner_radius=9, border_color=Style.line,
                         border_width=1, fg_color='#FAFBFD', text_color=Style.ink, font=font(13), show=show)
    entry.grid(row=1, column=0, sticky='ew')
    entry._field_group = group
    return entry


def field_error(entry, message=''):
    group=getattr(entry,'_field_group',None)
    if group is None:return
    entry.configure(border_color='#AD3544' if message else Style.line)
    error=getattr(entry,'_error_label',None)
    if error is None:
        error=label(group,'',11,color='#AD3544',anchor='w',justify='left',wraplength=250)
        entry._error_label=error
        error._responsive=ResizeObserver(group,lambda width:error.configure(wraplength=max(160,width-5)))
    error.configure(text=message)
    if message:error.grid(row=2,column=0,sticky='ew',pady=(5,0))
    else:error.grid_remove()


def form_notice(owner, text):
    notice=getattr(owner,'form_message',None)
    if notice is not None:notice.configure(text=text)
    else:return text


@lru_cache(maxsize=64)
def _product_pixels(filename):
    with Image.open(ASSETS_DIR / 'images' / filename) as source:
        picture = ImageOps.exif_transpose(source).convert('RGBA')
    bounds = picture.getbbox()
    return picture.crop(bounds) if bounds else picture


def product_image(filename, size=(220, 160)):
    """Cadrage homogène, proportions conservées, agrandissement plafonné."""
    try:
        picture = _product_pixels(filename).copy()
        ratio = min(size[0]/picture.width, size[1]/picture.height, 1.35)
        picture = picture.resize((max(1, round(picture.width*ratio)), max(1, round(picture.height*ratio))), Image.Resampling.LANCZOS)
        canvas = Image.new('RGBA', size, '#FFFFFF')
        canvas.alpha_composite(picture, ((size[0]-picture.width)//2, (size[1]-picture.height)//2))
        return ctk.CTkImage(light_image=canvas, dark_image=canvas, size=size)
    except (OSError, ValueError, TypeError):
        return None


def icon(name, size=20, color=None):
    """Pictogrammes dessinés dans le code, indépendants des polices de symboles."""
    color, factor = color or Style.ink, size*3/24
    image = Image.new('RGBA', (size*3, size*3))
    draw = ImageDraw.Draw(image)
    def line(points):
        draw.line([(round(x*factor), round(y*factor)) for x, y in points], fill=color, width=max(2, round(size/4)), joint='curve')
    def box(coords):
        draw.rounded_rectangle(tuple(round(v*factor) for v in coords), radius=2*factor, outline=color, width=max(2, round(size/4)))
    if name == 'bag':
        box((5, 8, 19, 21)); line([(8, 8), (8, 4), (16, 4), (16, 8)])
    elif name == 'screen':
        box((3, 4, 21, 16)); line([(12, 17), (12, 21), (7, 21), (17, 21)])
    elif name == 'travel':
        box((5, 6, 19, 21)); line([(9, 6), (9, 3), (15, 3), (15, 6)]); line([(9, 10), (9, 17)]); line([(15, 10), (15, 17)])
    elif name == 'check':
        line([(5, 12), (10, 17), (20, 6)])
    else:
        line([(4, 12), (20, 12), (15, 7), (20, 12), (15, 17)])
    return ctk.CTkImage(light_image=image, dark_image=image, size=(size, size))


def split_panels(container, first, second, breakpoint=830, first_weight=1, second_weight=1):
    def arrange(width):
        wide = width >= breakpoint
        container.grid_columnconfigure(0, weight=first_weight, uniform='panels' if wide else '', minsize=0)
        container.grid_columnconfigure(1, weight=second_weight if wide else 0, uniform='panels' if wide else '', minsize=0)
        if wide:
            first.grid(row=0, column=0, sticky='nsew', padx=(0, 18), pady=(0, 18))
        else:
            first.grid_remove()
        second.grid(row=0, column=1 if wide else 0, sticky='nsew', padx=0, pady=(0, 18))
    return ResizeObserver(container, arrange)


def show_credits(window):
    credits = project_credits()
    popup = ctk.CTkToplevel(window)
    popup.title('Équipe et contribution - Group9')
    popup.geometry('580x560')
    popup.minsize(420, 420)
    popup.transient(window.winfo_toplevel())
    body = ctk.CTkScrollableFrame(popup, fg_color=Style.bg)
    body.pack(fill='both', expand=True, padx=12, pady=12)
    label(body, 'UN PROJET COLLABORATIF', 11, 'bold', color=Style.blue).pack(anchor='w', padx=20, pady=(20, 10))
    label(body, credits['signature'], 25, 'bold').pack(anchor='w', padx=20)
    label(body, credits['title'], 14, color=Style.muted).pack(anchor='w', padx=20, pady=(0, 18))
    for title, text in [('Contribution', credits['contribution']), ('Équipe du groupe 9', '\n'.join(credits['team'])),
                        ('Cadre du projet', credits['context']+'\nSupervision : '+credits['supervisor'])]:
        label(body, title, 14, 'bold').pack(anchor='w', padx=20, pady=(12, 6))
        control = label(body, text, 13, color=Style.muted, justify='left', anchor='w', wraplength=490)
        control.pack(fill='x', padx=20)
        ResizeObserver(body, lambda width, item=control: item.configure(wraplength=max(240, width-50)))
    button(body, 'Fermer', popup.destroy, 'secondary').pack(anchor='w', padx=20, pady=24)
    popup.after(100, popup.lift)


def header(window, active=''):
    bar = ctk.CTkFrame(window, fg_color=Style.ink, corner_radius=0)
    bar.grid(row=0, column=0, sticky='ew')
    brand = ctk.CTkFrame(bar, fg_color='transparent')
    brand.grid(row=0, column=0, padx=22, pady=14, sticky='w')
    label(brand, 'g9', 23, 'bold', color='white', fg_color=Style.blue, corner_radius=11, width=46, height=44).pack(side='left', padx=(0, 12))
    label(brand, 'GROUP9 / STORE', 15, 'bold', color='white').pack(side='left')
    links = ctk.CTkFrame(bar, fg_color='transparent')
    session = SessionManager()
    links.grid(row=0, column=1, sticky='w')
    destinations = [('Accueil', 'accueil'), ('Catalogue', 'catalogue')]
    if session.is_authenticated:
        destinations.append(('Mes commandes', 'mes-commandes'))
    for title, route in destinations:
        control = button(links, title, lambda route=route: open_page(route, window), 'nav', width=135 if route == 'mes-commandes' else 96, height=40)
        control.pack(side='left', padx=3)
        if active == route:
            control.configure(fg_color='#2A4652', text_color='#D0E0FF')
    account = ctk.CTkFrame(bar, fg_color='transparent')
    account.grid(row=0, column=3, sticky='e', padx=18, pady=10)
    bar.grid_columnconfigure(2, weight=1)
    session = SessionManager()
    target = 'panier' if session.is_authenticated else 'connexion'
    button(account, 'Mon panier', lambda: open_page(target, window, return_to='panier'), 'nav', width=116,
           image=icon('bag', 18, '#FFFFFF'), compound='left', height=40).pack(side='left', padx=4)
    if session.is_authenticated:
        def logout():
            try:
                session.logout()
                open_page('accueil', window)
            except OSError:
                messagebox.showerror('Session', 'Impossible de fermer la session locale.', parent=window)
        button(account, 'Déconnexion', logout, 'nav', width=108, height=40).pack(side='left', padx=4)
    else:
        button(account, 'Se connecter', lambda: open_page('connexion', window), width=120, height=40).pack(side='left', padx=4)
    def arrange(width):
        narrow = width < 1000
        scale = bar._get_widget_scaling()
        window.minsize(min(round(640*scale), window.winfo_screenwidth()-30),
                       min(round(480*scale), window.winfo_screenheight()-70))
        links.grid(row=1 if narrow else 0, column=0 if narrow else 1, columnspan=4 if narrow else 1,
                   sticky='w', padx=22 if narrow else 0, pady=(0, 10) if narrow else 0)
        account.grid(row=1 if width < 570 else 0, column=3, sticky='e', padx=12, pady=10)
    bar._responsive = ResizeObserver(bar, arrange)
    return bar


def footer(window):
    bar = ctk.CTkFrame(window, fg_color=Style.bg, corner_radius=0)
    bar.grid(row=2, column=0, sticky='ew')
    bar.grid_columnconfigure(0, weight=1)
    signature = label(bar, 'Abdoulaye KONE - Analyste Statisticien', 11, color=Style.muted, anchor='w')
    signature.grid(row=0, column=0, sticky='w', padx=24, pady=(9, 0))
    context = label(bar, 'Projet collaboratif - Groupe 9 / ENSEA - Paiements simulés', 10, color=Style.muted, anchor='w')
    context.grid(row=1, column=0, sticky='w', padx=24, pady=(0, 10))
    button(bar, 'Équipe & crédits', lambda: show_credits(window), 'light', width=130, height=32,
           font=font(11, 'bold')).grid(row=0, column=1, rowspan=2, padx=20, pady=10)
    def arrange(width):
        signature.configure(wraplength=max(220, width-195))
        context.configure(wraplength=max(220, width-195))
    bar._responsive = ResizeObserver(bar, arrange)
    return bar
