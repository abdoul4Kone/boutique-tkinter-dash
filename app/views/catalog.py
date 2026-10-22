"""Accueil éditorial et catalogue adaptatif, alimentés par les produits MySQL."""
import json
from pathlib import Path
from functools import lru_cache
import tkinter as tk
import customtkinter as ctk
from app.commerce import get_products
from app.database import DatabaseError
from app.runtime import PageFrame
from app.navigation import open_page
from app.views.components import (Style, font, setup_window, header, footer, label, button,
                                  panel, product_image, icon, ResizeObserver)


@lru_cache(maxsize=1)
def editorial_catalogue():
    return json.loads(Path(__file__).with_name('catalogue_editorial.json').read_text(encoding='utf-8'))


def product_details(product):
    """Les informations éditoriales n'écrasent jamais les prix ni les stocks."""
    return editorial_catalogue().get(product.get('image'), {
        'title': product['nom'].strip(), 'description': 'Découvrez cet article de notre collection.',
        'specs': [], 'use': product['categorie'],
    })


def home_selection(products):
    """Une sélection équilibrée entre usages, indépendante de l'ordre des identifiants."""
    preferences = ['macbook2.png', 'sac_inateck.png', 'veste_noire.png', 'xbox_seriesX.png',
                   'xiaomi_blanc.png', 'valise_noire.png', 'soulier_noir.png', 'bandouliere.png']
    available = {p['image']: p for p in products}
    chosen = [available[name] for name in preferences if name in available]
    seen = {p['id'] for p in chosen}
    return (chosen + [p for p in products if p['id'] not in seen])[:8]


class CatalogPage:
    def __init__(self, home=False, window=None, initial_data=None):
        self.home, self.products, self.selected = home, [], None
        self.window = window if window is not None else tk.Tk()
        self.window._view = self
        self.initial_data = initial_data
        setup_window(self.window, 'Accueil' if home else 'Catalogue')
        header(self.window, 'accueil' if home else 'catalogue')
        footer(self.window)
        self.scroll = ctk.CTkScrollableFrame(self.window, fg_color=Style.bg, corner_radius=0)
        self.scroll.grid(row=1, column=0, sticky='nsew', padx=18)
        self.scroll.grid_columnconfigure(0, weight=1)
        self.categories = {'Tout': None, 'Tech': 'Ordinateurs & téléphones', 'Mode': 'Vêtements',
                           'Consoles': 'Jeux & consoles', 'Bagagerie': 'Sacs & valises', 'Chaussures': 'Chaussures'}
        self.card_widgets, self.filter_widgets, self.columns = [], [], 0
        self._render_job = None
        if home:
            self.make_hero()
            self.make_collections()
        self.controls = ctk.CTkFrame(self.scroll, fg_color='transparent')
        self.controls.grid(row=2, column=0, sticky='ew', padx=10, pady=(24, 12))
        self.controls.grid_columnconfigure(0, weight=1)
        self.heading = label(self.controls, 'Des idées pour votre quotidien' if home else 'Toute la collection', 26, 'bold', anchor='w')
        self.heading.grid(row=0, column=0, sticky='w')
        self.search = ctk.CTkEntry(self.controls, placeholder_text='Rechercher un produit', height=44,
                                  width=275, fg_color='white', border_color=Style.line, font=font(13))
        self.search.grid(row=0, column=1, padx=12)
        self.search.bind('<KeyRelease>', self.schedule_search)
        self.sort = ctk.CTkOptionMenu(self.controls, values=['Notre sélection', 'Prix croissant', 'Prix décroissant', 'En stock'],
                                     command=lambda value: self.render_products(), width=165, height=44,
                                     fg_color=Style.ink, button_color=Style.ink, font=font(12))
        self.sort.grid(row=0, column=2)
        self.filters = ctk.CTkFrame(self.scroll, fg_color='transparent')
        self.filters.grid(row=3, column=0, sticky='ew', padx=10, pady=(0, 8))
        for title, category in self.categories.items():
            control = button(self.filters, title, lambda value=category: self.select_category(value), 'light', width=102, height=36)
            self.filter_widgets.append(control)
        self.count = label(self.scroll, '', 12, color=Style.muted, anchor='w')
        self.count.grid(row=4, column=0, sticky='ew', padx=12, pady=(0, 12))
        self.cards = ctk.CTkFrame(self.scroll, fg_color='transparent')
        self.cards.grid(row=5, column=0, sticky='ew', padx=3, pady=(0, 16))
        self.more = button(self.scroll, 'Voir toute la collection', lambda: open_page('catalogue', self.window), 'secondary', width=225)
        if home:
            self.more.grid(row=6, column=0, pady=(4, 28))
        self.controls._responsive = ResizeObserver(self.controls, self.arrange_controls)
        self.filters._responsive = ResizeObserver(self.filters, self.arrange_filters)
        self.cards._responsive = ResizeObserver(self.cards, self.arrange_cards)
        self.reload()

    def make_hero(self):
        hero = ctk.CTkFrame(self.scroll, fg_color=Style.ink, corner_radius=22)
        hero.grid(row=0, column=0, sticky='ew', padx=10, pady=(20, 12))
        hero.grid_columnconfigure(0, weight=1)
        copy = ctk.CTkFrame(hero, fg_color='transparent')
        copy.grid(row=0, column=0, sticky='nsew', padx=30, pady=26)
        label(copy, 'LA COLLECTION GROUP9 / 01', 11, 'bold', color='#C5D7DD').pack(anchor='w', pady=(0, 14))
        title = label(copy, 'Des objets utiles.\nDes envies à explorer.', 38, 'bold', color='white', justify='left', anchor='w')
        title.pack(fill='x')
        caption = label(copy, 'Pour travailler, sortir ou changer d’horizon.\nTrouvez la pièce qui accompagne votre quotidien.', 14,
                        color='#D0DDE0', justify='left', anchor='w', wraplength=440)
        caption.pack(fill='x', pady=(14, 20))
        button(copy, 'Explorer la collection', lambda: open_page('catalogue', self.window), width=225,
               image=icon('arrow', 18, '#FFFFFF'), compound='right').pack(anchor='w')
        label(copy, 'TECH  /  MODE  /  VOYAGE', 10, 'bold', color='#AEC4CB').pack(anchor='w', pady=(22, 0))
        visual = panel(hero, fg_color='#FFFFFF', border_width=0)
        visual.grid(row=0, column=1, sticky='nsew', padx=(0, 24), pady=24)
        image = product_image('macbook2.png', (310, 225))
        label(visual, '' if image else 'Collection Tech', image=image).pack(padx=16, pady=(16, 0))
        label(visual, 'CRÉER. TRAVAILLER. AVANCER.', 10, 'bold', color=Style.muted).pack(pady=(0, 18))
        def arrange(width):
            compact = width < 790
            title.configure(font=font(30 if compact else 38, 'bold'), wraplength=max(280, width-80 if compact else width-440))
            caption.configure(wraplength=max(270, width-80 if compact else width-440))
            if compact:
                visual.grid_remove()
            else:
                visual.grid()
        hero._responsive = ResizeObserver(hero, arrange)

    def make_collections(self):
        row = ctk.CTkFrame(self.scroll, fg_color='transparent')
        row.grid(row=1, column=0, sticky='ew', padx=3, pady=(0, 4))
        tiles = []
        for index, (kicker, title, category, symbol) in enumerate([
            ('01 / TECH', 'Créer & travailler', 'Ordinateurs & téléphones', 'screen'),
            ('02 / VOYAGE', 'Partir & bouger', 'Sacs & valises', 'travel'),
            ('03 / STYLE', 'Trouver son allure', 'Vêtements', 'bag')]):
            tile = panel(row, fg_color=Style.paper)
            tile.grid_columnconfigure(1, weight=1)
            label(tile, '', image=icon(symbol, 25, Style.blue), width=40).grid(row=0, column=0, rowspan=2, padx=(16, 8), pady=18)
            label(tile, kicker, 10, 'bold', color=Style.muted, anchor='w').grid(row=0, column=1, sticky='w', pady=(18, 0))
            button(tile, title, lambda value=category: self.select_collection(value), 'light', height=32,
                   fg_color='white', hover_color=Style.soft, text_color=Style.ink, anchor='w', width=175).grid(row=1, column=1, sticky='ew', padx=(0, 12), pady=(0, 16))
            tiles.append(tile)
        def arrange(width):
            columns = 3 if width >= 900 else (2 if width >= 610 else 1)
            for i in range(3):
                row.grid_columnconfigure(i, weight=1 if i < columns else 0, uniform='collections' if i < columns else '', minsize=0)
            for i, tile in enumerate(tiles):
                tile.grid(row=i//columns, column=i%columns, sticky='ew', padx=7, pady=6)
        row._responsive = ResizeObserver(row, arrange)

    def select_collection(self, category):
        self.select_category(category)
        def reveal_selection():
            canvas = self.scroll._parent_canvas
            canvas.yview_moveto(max(0, self.controls.winfo_y()-12)/max(1, self.scroll.winfo_height()))
        self.window.after_idle(reveal_selection)

    def arrange_controls(self, width):
        narrow = width < 970
        self.heading.configure(wraplength=max(260, width-25 if narrow else width-490), font=font(23 if width < 650 else 26, 'bold'))
        self.search.grid(row=1 if narrow else 0, column=0 if narrow else 1, sticky='ew', padx=(0, 12), pady=(14, 0) if narrow else 0)
        self.sort.grid(row=1 if narrow else 0, column=1 if narrow else 2, sticky='e', pady=(14, 0) if narrow else 0)
        self.heading.grid(columnspan=2 if narrow else 1)

    def arrange_filters(self, width):
        columns = max(1, min(6, int(width//114)))
        for i in range(6):
            self.filters.grid_columnconfigure(i, weight=0)
        for i, widget in enumerate(self.filter_widgets):
            widget.grid(row=i//columns, column=i%columns, padx=(0, 8), pady=4)

    def arrange_cards(self, width):
        columns = max(1, min(4, int(width//265)))
        for i in range(4):
            self.cards.grid_columnconfigure(i, weight=1 if i < columns else 0, uniform='products' if i < columns else '')
        for i, card in enumerate(self.card_widgets):
            card.grid(row=i//columns, column=i%columns, sticky='nsew', padx=7, pady=8)
        self.columns = columns

    def schedule_search(self, event=None):
        if self._render_job:
            self.window.after_cancel(self._render_job)
        self._render_job = self.window.after(180, self.render_products)

    def reload(self):
        try:
            self.products = self.initial_data['products'] if self.initial_data is not None else get_products()
        except DatabaseError:
            self.count.configure(text='Le catalogue est momentanément indisponible.')
            for widget in self.cards.winfo_children():
                widget.destroy()
            button(self.cards, 'Réessayer', self.reload).grid(row=0, column=0, pady=25)
            return
        self.select_category(self.selected)

    def select_category(self, category):
        self.selected = category
        for widget, value in zip(self.filter_widgets, self.categories.values()):
            widget.configure(fg_color=Style.blue if value == category else Style.soft,
                             text_color='white' if value == category else '#1646C3')
        self.render_products()

    def render_products(self):
        self._render_job = None
        for widget in self.cards.winfo_children():
            widget.destroy()
        self.card_widgets = []
        query = self.search.get().strip().casefold()
        products = [p for p in self.products if (not self.selected or p['categorie'] == self.selected)
                    and query in (p['nom']+' '+product_details(p)['title']).casefold()]
        order = self.sort.get()
        if order == 'En stock':
            products = [p for p in products if p['stock'] > 0]
        elif order.startswith('Prix'):
            products.sort(key=lambda p: p['prix'], reverse=order == 'Prix décroissant')
        selection = self.home and not query and not self.selected and order == 'Notre sélection'
        if selection:
            products = home_selection(products)
        self.count.configure(text=(f'{len(products)} idées choisies parmi {len(self.products)} produits' if selection else f'{len(products)} produit(s)')+' - Prix en FCFA')
        if not products:
            label(self.cards, 'Aucun produit trouvé. Essayez un autre mot ou une autre catégorie.', 15,
                  color=Style.muted, wraplength=400).grid(row=0, column=0, padx=15, pady=40)
        for product in products:
            details = product_details(product)
            card = panel(self.cards)
            card.grid_columnconfigure(0, weight=1)
            card.grid_rowconfigure(3, weight=1)
            image = product_image(product['image'], (210, 178))
            target = f"produit:{product['id']}"
            photo = label(card, '' if image else 'Visuel indisponible', image=image, height=190, cursor='hand2')
            photo.grid(row=0, column=0, padx=12, pady=(12, 0))
            photo.bind('<Button-1>', lambda event, destination=target: open_page(destination, self.window))
            label(card, details['use'].upper(), 10, 'bold', color=Style.muted, anchor='w').grid(row=1, column=0, sticky='w', padx=17, pady=(5, 4))
            label(card, details['title'], 16, 'bold', wraplength=218, height=51, justify='left', anchor='nw').grid(row=2, column=0, sticky='ew', padx=17)
            label(card, details['description'], 12, color=Style.muted, wraplength=218, height=54, justify='left', anchor='nw').grid(row=3, column=0, sticky='ew', padx=17, pady=(2, 8))
            label(card, f"{product['prix']:,.0f} FCFA".replace(',', ' '), 21, 'bold').grid(row=4, column=0, sticky='w', padx=17, pady=(4, 3))
            label(card, f"Disponible - {product['stock']} en stock" if product['stock'] > 0 else 'Rupture de stock',
                  11, color=Style.green if product['stock'] > 0 else '#AC3742').grid(row=5, column=0, sticky='w', padx=17, pady=(0, 14))
            button(card, 'Découvrir', lambda destination=target: open_page(destination, self.window), 'secondary', width=205,
                   image=icon('arrow', 16, '#FFFFFF'), compound='right').grid(row=6, column=0, sticky='ew', padx=15, pady=(0, 16))
            self.card_widgets.append(card)
        self.arrange_cards(max(270, self.cards.winfo_width()/self.cards._get_widget_scaling()))


def main(parent=None, initial_data=None, **options):
    if parent is None:
        from app.runtime import launch
        return launch('catalogue')
    page = CatalogPage(window=PageFrame(parent), initial_data=initial_data)
    return page.window
