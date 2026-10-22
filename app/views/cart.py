"""Panier du client connecté : quantités, contrôle du stock et récapitulatif."""

from tkinter import messagebox
import customtkinter
from pathlib import Path
from PIL import Image
from app.accounts import current_user_id
from app.config import ASSETS_DIR
from app.database import DatabaseError
from app.runtime import PageFrame, run_task
from app.navigation import open_page
from app.views.components import Style, setup_window, header, footer, label, button, panel, ResizeObserver
from app.commerce import get_cart, set_basket_quantity


def main(product_id=None, return_to='accueil', parent=None, initial_data=None):
    if parent is None:
        from app.runtime import launch
        return launch('panier', return_to=return_to)
    def fillPanier(product_id, quantity):
        if current_user_id()!=user_id:
            raise ValueError('Reconnectez-vous avant de modifier le panier.')
        set_basket_quantity(user_id, product_id, quantity)
        return True

    user_id = current_user_id()

    ASSETS_PATH = ASSETS_DIR / 'images'

    def relative_to_assets(path: str) -> Path:
        return ASSETS_PATH / Path(path)

    if user_id is None:
        raise ValueError('Reconnectez-vous pour consulter le panier.')

    user_id = user_id #Récupération de l'id de l'utilisateur connecté


    def home(): 
        open_page('accueil', app)

    customtkinter.set_appearance_mode("Light")  # Modes: "System" (standard), "Dark", "Light"

    customtkinter.set_default_color_theme("blue")  # Themes: "blue" (standard), "green", "dark-blue"

    class Panier(PageFrame):
        def __init__(self):
            super().__init__(parent)
        
            # configure window
            self.title("Commander")
            self.geometry("1100x580")
            # Désactiver le redimensionnement si nécessaire
            self.resizable(False, False)
        
            self.setup_ui()

            # configure grid layout (4x4)
            # self.grid_columnconfigure(1, weight=1)
            # self.grid_columnconfigure((2, 3), weight=0)
            # self.grid_rowconfigure((0, 1, 2), weight=1)
        
        def setup_ui(self):
            setup_window(self, 'Mon panier')
            self.resizable(True, True)
            header(self, 'panier')
            footer(self)
            self.frameCommande = customtkinter.CTkScrollableFrame(self, fg_color=Style.bg, corner_radius=0)
            self.frameCommande.grid(row=1, column=0, sticky='nsew', padx=24, pady=16)
            self.frameCommande.grid_columnconfigure(0, weight=3)
            self.frameCommande.grid_columnconfigure(1, weight=1)
            label(self.frameCommande, 'Votre panier', 29, 'bold').grid(row=0, column=0, sticky='w', padx=12, pady=(10, 6))
            label(self.frameCommande, 'Vos choix, avant la dernière étape.', 14, color=Style.muted).grid(row=1, column=0, sticky='w', padx=12, pady=(0, 22))
            self.livraisonFrame = panel(self.frameCommande)
            self.livraisonFrame.grid(row=2, column=0, sticky='new', padx=(8, 18))
            self.livraisonFrame.grid_columnconfigure(0, weight=1)
            self.listProdFrame = customtkinter.CTkFrame(self.livraisonFrame, fg_color='white')
            self.listProdFrame.grid(row=0, column=0, sticky='ew', padx=12, pady=16)
            self.produits = self.get_panier(user_id)
            self.listProduit(self.produits)
            self.recapFrame = panel(self.frameCommande, width=300)
            self.recapFrame.grid(row=2, column=1, sticky='new', padx=(0, 8))
            self.recapFrame.grid_columnconfigure(0, weight=1)
            label(self.recapFrame, 'Récapitulatif', 21, 'bold').grid(row=0, column=0, sticky='w', padx=22, pady=(24, 18))
            self.nbProd = customtkinter.StringVar(value=f'Articles distincts ({len(self.produits)})')
            label(self.recapFrame, textvariable=self.nbProd, color=Style.muted).grid(row=1, column=0, sticky='w', padx=22, pady=4)
            self.coutTotVar = customtkinter.StringVar(value=f'{self.prix_panier(self.produits):,.0f} FCFA'.replace(',', ' '))
            label(self.recapFrame, textvariable=self.coutTotVar, size=27, weight='bold').grid(row=2, column=0, sticky='w', padx=22, pady=(8, 15))
            label(self.recapFrame, 'Livraison calculée à l’étape suivante.', 12, color=Style.muted, wraplength=260).grid(row=3, column=0, sticky='w', padx=22, pady=(0, 20))
            self.boutonCommander = button(self.recapFrame, 'Passer à la livraison  →', self.commander)
            self.boutonCommander.grid(row=4, column=0, sticky='ew', padx=20, pady=(0, 14))
            if not self.produits or self.cart_unavailable:
                self.boutonCommander.configure(state='disabled')
            button(self.recapFrame, 'Continuer mes achats', lambda: open_page('catalogue', self), 'light').grid(row=5, column=0, sticky='ew', padx=20, pady=(0, 24))
            if self.cart_unavailable:
                button(self.livraisonFrame, 'Recharger le panier', lambda: open_page('panier', self), 'light').grid(row=1, column=0, pady=20)

        
    
        

        
            def arrange(width):
                narrow = width < 1000
                self.frameCommande.grid_columnconfigure(1, weight=0 if narrow else 1)
                self.livraisonFrame.grid(row=2, column=0, sticky='new', padx=8)
                self.recapFrame.grid(row=3 if narrow else 2, column=0 if narrow else 1, sticky='new', padx=8, pady=(16, 0) if narrow else 0)
            self._responsive = ResizeObserver(self.frameCommande, arrange)

        def load_image(self, path, size):
            """Charge et redimensionne une image."""
            try:
                with Image.open(path) as source:
                    img = source.resize(size, Image.Resampling.LANCZOS)
                return customtkinter.CTkImage(img, size=size)
            except (OSError, ValueError):
                return None

        
        def get_panier(self, client_id):
            try:
                self.cart_unavailable = False
                return initial_data['cart'] if initial_data is not None else get_cart(client_id)
            except DatabaseError:
                self.cart_unavailable = True
                messagebox.showerror("Panier indisponible", 'Impossible de charger le panier. Réessayez plus tard.')
                return []

        def prix_panier(self,produits):
            self.prix = 0
            for i in produits:
                self.prix = self.prix + i[2]*i[1]
            
            return self.prix


        def change_cart(self, product_id, quantity, updated):
            def ready(result):
                if result is not False:updated()
            return run_task(self,lambda:fillPanier(product_id,quantity),ready,
                            lambda error:messagebox.showerror('Panier',str(error)),
                            tuple(getattr(self,'action_buttons',[])))

        def listProduit(self, produits):
            self.action_buttons=[]
        
            if self.produits == []:
                customtkinter.CTkLabel(self.listProdFrame, text='Panier indisponible' if getattr(self, 'cart_unavailable', False) else 'Votre panier attend vos premières découvertes.',font=customtkinter.CTkFont(size=16), text_color='#66758B').grid(row=0, column=0, sticky='ew', padx=20, pady=30)
            if not self.listProdFrame.winfo_exists():
                print("Erreur : Le cadre self.listProdFrame n'existe pas.")
                return

            for idx, produit in enumerate(produits):
                try:
                    image_path = relative_to_assets(f"{produit[3]}")
                    imgi = self.load_image(image_path, (50, 50))

                    # Affichage de l'image
                    customtkinter.CTkLabel(
                        self.listProdFrame, text="" if imgi else "Image\nindisponible", image=imgi
                    ).grid(row=idx * 4, column=0, rowspan=2, padx=(10, 5), pady=10, sticky="w")

                    # Affichage du nom du produit
                    customtkinter.CTkLabel(
                        self.listProdFrame, text=f"{produit[0]}", wraplength=185, justify="left", font=customtkinter.CTkFont(size=13)
                    ).grid(row=idx * 4, column=1, sticky="w", pady=(10, 0), padx=(10, 5))

                    # Affichage de la quantité
                    quantity_label = customtkinter.CTkLabel(
                        self.listProdFrame, text=f"Quantité : {produit[1]}", font=customtkinter.CTkFont(size=12)
                    )
                    quantity_label.grid(row=idx * 4 + 1, column=1, sticky="w", pady=0, padx=(10, 5))

                                    # Boutons pour gérer la quantité
                    def increase_quantity(x, quantity_label=quantity_label):
                        quantity=produits[x][1]+1
                        def updated():
                            produits[x][1]=quantity
                            quantity_label.configure(text=f"Quantité : {quantity}")
                            self.nbProd.set(f"Articles distincts ({len(produits)})")
                            self.coutTotVar.set(f"{self.prix_panier(produits):,.0f} FCFA".replace(',',' '))
                        self.change_cart(produits[x][-1],quantity,updated)

                    def decrease_quantity(x, quantity_label=quantity_label):
                        if produits[x][1]<=1:return
                        quantity=produits[x][1]-1
                        def updated():
                            produits[x][1]=quantity
                            quantity_label.configure(text=f"Quantité : {quantity}")
                            self.coutTotVar.set(f"{self.prix_panier(produits):,.0f} FCFA".replace(',',' '))
                        self.change_cart(produits[x][-1],quantity,updated)

                    def remove_product(x):
                        if not messagebox.askyesno('Supprimer','Supprimer cet article du panier ?'):return
                        def updated():
                            produits.pop(x)
                            for widget in self.listProdFrame.winfo_children():widget.destroy()
                            self.listProduit(produits)
                            self.nbProd.set(f"Articles distincts ({len(produits)})")
                            self.coutTotVar.set(f"{self.prix_panier(produits):,.0f} FCFA".replace(',',' '))
                            self.boutonCommander.configure(state='normal' if produits else 'disabled')
                        self.change_cart(produits[x][-1],0,updated)

                    # Les contrôles attendent la confirmation de la base avant d'afficher la nouvelle quantité.
                    for text,action,column in [('+',increase_quantity,3),('-',decrease_quantity,4),('×',remove_product,5)]:
                        control=customtkinter.CTkButton(self.listProdFrame,text=text,
                            command=lambda idx=idx,action=action:action(idx),width=30,height=25)
                        control.grid(row=idx*4,column=column,sticky='ne',padx=(2,7),pady=4)
                        self.action_buttons.append(control)

                    # Affichage du self.prix
                    customtkinter.CTkLabel(
                        self.listProdFrame, text=f"{produit[2]:,.0f} FCFA / unité".replace(',', ' '), font=customtkinter.CTkFont(size=12)
                    ).grid(row=idx * 4 + 1, column=3, columnspan=3, sticky="e", padx=(5, 8))

                    # Ligne de séparation
                    customtkinter.CTkFrame(
                        self.listProdFrame, height=2, fg_color="lightgrey", width=1
                    ).grid(row=idx * 4 + 2, column=0, columnspan=6, padx=(12, 0), pady=(2, 10), sticky="ew")

                except Exception as e:
                    print(f"Erreur lors de l'ajout du produit : {produit}. Détails : {e}")

    
        def commander(self):
            if current_user_id() != user_id:
                open_page('connexion', self, return_to='panier')
                return
            if self.produits==[]:
                messagebox.showwarning("Oups!", "Votre panier est vide, veuillez ajoutez des produits pour commander")
            else:
                open_page('commande', self)

    app = Panier()

    return app

