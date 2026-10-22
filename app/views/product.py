"""Fiche produit commune à toutes les références du catalogue."""

import tkinter as tk
import customtkinter as ctk
from tkinter import messagebox

from app.accounts import SessionManager
from app.commerce import get_cart, set_basket_quantity, get_products
from app.database import DatabaseError
from app.runtime import PageFrame, run_task
from app.navigation import open_page
from app.views.components import Style, font, setup_window, header, footer, label, button, panel, product_image, ResizeObserver, icon
from app.views.catalog import product_details


class ProductPage:
    def __init__(self, product_id, window=None, initial_data=None):
        self.product_id = int(product_id)
        products = initial_data['products'] if initial_data is not None else get_products(self.product_id)
        if not products:
            raise ValueError('Ce produit n’est plus disponible dans le catalogue.')
        self.product = products[0]
        self.session = SessionManager()
        self.window = window if window is not None else tk.Tk()
        self.window._view = self
        setup_window(self.window, 'Fiche produit')
        header(self.window)
        footer(self.window)
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        details = product_details(self.product)
        self.scroll = scroll = ctk.CTkScrollableFrame(self.window, fg_color=Style.bg, corner_radius=0)
        scroll.grid(row=1, column=0, sticky='nsew', padx=18, pady=14)
        scroll.grid_columnconfigure(0, weight=1)
        label(scroll, 'COLLECTION / '+self.product['categorie'].upper(), 11, 'bold', color=Style.muted).grid(row=0, column=0, sticky='w', padx=12, pady=(8, 16))
        content = panel(scroll)
        content.grid(row=1, column=0, sticky='ew', padx=10)
        content.grid_columnconfigure(0, weight=1)
        content.grid_columnconfigure(1, weight=1)
        visual = ctk.CTkFrame(content, fg_color='#FFFFFF', corner_radius=18)
        visual.grid(row=0, column=0, sticky='nsew', padx=22, pady=24)
        visual.grid_columnconfigure(0, weight=1)
        visual.grid_rowconfigure(1, weight=1)
        label(visual, details['use'].upper(), 10, 'bold', color=Style.muted).grid(row=0, column=0, pady=(0, 12))
        picture = product_image(self.product['image'], (360, 310))
        photo = label(visual, '' if picture else 'Visuel indisponible', image=picture, height=320)
        photo.grid(row=1, column=0, sticky='nsew', pady=10)
        button(visual, 'Voir le visuel', self.enlarge_image, 'light', height=34, width=180).grid(row=2, column=0, pady=(10, 0))
        copy = ctk.CTkFrame(content, fg_color='transparent')
        copy.grid(row=0, column=1, sticky='new', padx=24, pady=25)
        copy.grid_columnconfigure(0, weight=1)
        label(copy, self.product['categorie'].upper(), 10, 'bold', color=Style.blue).grid(row=0, column=0, sticky='w', pady=(0, 10))
        title = label(copy, details['title'], 31, 'bold', wraplength=450, justify='left', anchor='w')
        title.grid(row=1, column=0, sticky='ew')
        description = label(copy, details['description'], 14, color=Style.muted, wraplength=440, justify='left', anchor='w')
        description.grid(row=2, column=0, sticky='ew', pady=(12, 14))
        label(copy, f"{self.product['prix']:,.0f} FCFA".replace(',', ' '), 33, 'bold').grid(row=3, column=0, sticky='w', pady=(0, 8))
        label(copy, f"Disponible - {self.product['stock']} en stock" if self.product['stock'] else 'Rupture de stock',
              12, color=Style.green if self.product['stock'] else '#AC3742').grid(row=4, column=0, sticky='w', pady=(0, 20))
        label(copy, 'Quantité dans votre panier', 12, 'bold', color=Style.muted).grid(row=5, column=0, sticky='w')
        self.quantity = tk.IntVar(master=self.window, value=0)
        self.counter_frame = ctk.CTkFrame(copy, fg_color=Style.soft, corner_radius=11)
        self.counter_frame.grid(row=6, column=0, sticky='w', pady=(8, 16))
        minus = button(self.counter_frame, '-', lambda: self.change_quantity(max(0, self.quantity.get()-1)), 'light', width=45)
        minus.grid(row=0, column=0)
        label(self.counter_frame, textvariable=self.quantity, width=55, size=17, weight='bold').grid(row=0, column=1)
        plus = button(self.counter_frame, '+', lambda: self.change_quantity(self.quantity.get()+1), 'light', width=45)
        plus.grid(row=0, column=2)
        add = button(copy, 'Ajouter à mon panier', self.add, image=icon('bag', 18, '#FFFFFF'), compound='left')
        add.grid(row=7, column=0, sticky='ew', pady=(0, 16))
        shipping = label(copy, 'Livraison calculée à l’étape suivante. Carte et Wave : démonstration sans débit.', 12,
                         color=Style.muted, justify='left', wraplength=430, anchor='w')
        shipping.grid(row=8, column=0, sticky='ew', pady=(0, 4))
        self.refs = {'_add_button': add, '_minus': minus, '_plus': plus, '_images': [picture]}
        def arrange(width):
            wide = width >= 900
            content.grid_columnconfigure(1, weight=1 if wide else 0)
            visual.grid(row=0, column=0, sticky='nsew', padx=22, pady=(24, 10))
            copy.grid(row=0 if wide else 1, column=1 if wide else 0, sticky='new', padx=24, pady=25)
            wrap = max(280, width/2-65 if wide else width-60)
            title.configure(wraplength=wrap, font=font(31 if wide else 27, 'bold'))
            description.configure(wraplength=wrap)
            shipping.configure(wraplength=wrap)
            photo.configure(image=product_image(self.product['image'], (360, 310) if wide else (300, 205)), height=320 if wide else 215)
        content._responsive = ResizeObserver(content, arrange)
        specification = panel(scroll)
        specification.grid(row=2, column=0, sticky='ew', padx=10, pady=(16, 0))
        specification.grid_columnconfigure(0, weight=1)
        label(specification, 'La référence en détail', 22, 'bold').grid(row=0, column=0, sticky='w', padx=24, pady=(20, 8))
        full_name = label(specification, self.product['nom'].strip(), 13, color=Style.muted, justify='left', anchor='w', wraplength=900)
        full_name.grid(row=1, column=0, sticky='ew', padx=24, pady=(0, 14))
        for index, (name, value) in enumerate(details['specs']):
            row = ctk.CTkFrame(specification, fg_color='#F6F7F5' if index%2 == 0 else '#FFFFFF', corner_radius=6)
            row.grid(row=index+2, column=0, sticky='ew', padx=20, pady=2)
            row.grid_columnconfigure(1, weight=1)
            label(row, name, 12, 'bold', width=160, anchor='w', wraplength=155, justify='left').grid(row=0, column=0, sticky='w', padx=12, pady=10)
            value_label = label(row, value, 13, color=Style.muted, anchor='w', justify='left', wraplength=280)
            value_label.grid(row=0, column=1, sticky='ew', padx=12, pady=10)
            row._responsive = ResizeObserver(row, lambda width, item=value_label: item.configure(wraplength=max(150, width-205)))
        label(specification, 'Caractéristiques reprises de la référence catalogue.', 11, color=Style.muted).grid(row=len(details['specs'])+2, column=0, sticky='w', padx=24, pady=(10, 20))
        specification._responsive = ResizeObserver(specification, lambda width: full_name.configure(wraplength=max(280, width-55)))
        button(scroll, 'Continuer mes achats', lambda: open_page('catalogue', self.window), 'light', width=220).grid(row=3, column=0, sticky='w', padx=10, pady=20)
        self.display_quantity(0)
        if self.session.is_authenticated:
            try:
                quantity = next((row[1] for row in (initial_data['cart'] if initial_data is not None else get_cart(self.session.user.id))
                                 if int(row[-1]) == self.product_id), 0)
                self.display_quantity(quantity)
            except DatabaseError as error:
                messagebox.showerror("Panier", str(error), parent=self.window)

    def enlarge_image(self):
        popup = ctk.CTkToplevel(self.window)
        popup.title(self.product['nom'].strip())
        popup.geometry('600x570')
        popup.minsize(420, 420)
        popup.transient(self.window.winfo_toplevel())
        popup.grid_columnconfigure(0, weight=1)
        popup.grid_rowconfigure(1, weight=1)
        label(popup, product_details(self.product)['title'], 23, 'bold', wraplength=470).grid(row=0, column=0, padx=25, pady=20)
        picture = product_image(self.product['image'], (390, 370))
        label(popup, '' if picture else 'Visuel indisponible', image=picture).grid(row=1, column=0, sticky='nsew', padx=10)
        button(popup, 'Fermer', popup.destroy, 'secondary', width=160).grid(row=2, column=0, pady=20)
        popup.after(100, popup.lift)

    def login(self):
        open_page("connexion", self.window, return_to=f"produit:{self.product_id}")

    def cart(self):
        if self.session.is_authenticated:
            open_page("panier", self.window)
        else:
            open_page("connexion", self.window, return_to="panier")

    def add(self):
        if not self.session.is_authenticated:
            self.login()
        elif self.quantity.get():
            self.cart()
        else:
            self.change_quantity(max(1, self.quantity.get()))

    def display_quantity(self, quantity):
        self.quantity.set(quantity)
        self.refs['_minus'].configure(state='normal' if quantity else 'disabled')
        self.refs['_add_button'].configure(text='Voir mon panier  →' if quantity else 'Ajouter à mon panier  →',
                                           state='normal' if quantity or self.product['stock'] > 0 else 'disabled')

    def change_quantity(self, quantity):
        if not self.session.is_authenticated:
            self.login()
            return False
        user_id = self.session.user.id
        def save():
            from app.accounts import current_user_id
            if current_user_id() != user_id:
                raise ValueError('La session a changé. Reconnectez-vous.')
            return set_basket_quantity(user_id, self.product_id, quantity)
        def failed(error):
            messagebox.showerror('Panier', str(error), parent=self.window)
        controls=tuple(control for key,control in getattr(self,'refs',{}).items() if key in ('_add_button','_minus','_plus'))
        return run_task(self.window, save,
                        lambda result:self.display_quantity(quantity), failed, controls)

    def close(self):
        self.window.destroy()


def main(product_id=None, parent=None, initial_data=None, **options):
    if parent is None:
        from app.runtime import launch
        return launch(f'produit:{product_id}')
    page=ProductPage(product_id, window=PageFrame(parent), initial_data=initial_data)
    return page.window
