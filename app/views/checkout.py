"""Livraison, paiement simulé et confirmation de la commande."""

from tkinter import messagebox
import customtkinter
from pathlib import Path
from PIL import Image
from app.accounts import current_user_id
from decimal import Decimal
from app.config import ASSETS_DIR
from app.database import DatabaseError
from app.runtime import PageFrame, run_task
from app.navigation import open_page
from app.views.components import Style, font, setup_window, header, footer, label, button, panel, field, ResizeObserver, field_error, form_notice
from app.commerce import get_cart, get_customer, localities, delivery_rates, place_order


def main(product_id=None, return_to='accueil', parent=None, initial_data=None):
    if parent is None:
        from app.runtime import launch
        return launch('commande', return_to=return_to)
    user_id = current_user_id()

    ASSETS_PATH = ASSETS_DIR / 'images'

    def relative_to_assets(path: str) -> Path:
        return ASSETS_PATH / Path(path)

    if user_id is None:
        raise ValueError('Reconnectez-vous pour consulter la livraison.')

    user_id = user_id #Récupération de l'id de l'utilisateur connecté


    def get_data(client_id):
        global user
        row = initial_data['customer'] if initial_data is not None else get_customer(client_id)
        if row is None:
            raise ValueError('Ce compte est introuvable. Reconnectez-vous.')
        user = ConnectedUser(*row)

    class ConnectedUser:
        def __init__(self,nom, prenoms,sexe,birth_date,email,mdp,tel):
            self.nom = nom
            self.prenoms = prenoms
            self.sexe = sexe
            self.birth_date = birth_date
            self.email = email
            self.mdp = mdp
            self.tel = tel

    def modifierPanier():
        open_page('panier', app)

    def home(): 
        open_page('accueil', app)

    get_data(user_id)

    customtkinter.set_appearance_mode("Light")  # Modes: "System" (standard), "Dark", "Light"

    customtkinter.set_default_color_theme("blue")  # Themes: "blue" (standard), "green", "dark-blue"

    class Commander(PageFrame):
        def __init__(self):
            super().__init__(parent)
        
            # configure window
            self.title("Commander")
            self.geometry(f"{1100}x{580}")
        
        
        
            self.setup_ui()

            # configure grid layout (4x4)
            # self.grid_columnconfigure(1, weight=1)
            # self.grid_columnconfigure((2, 3), weight=0)
            # self.grid_rowconfigure((0, 1, 2), weight=1)
        
        def setup_ui(self):
            setup_window(self, 'Livraison et commande')
            header(self)
            footer(self)
            self.last_keypress = None
            self.frameCommande = customtkinter.CTkScrollableFrame(self, fg_color=Style.bg, corner_radius=0)
            self.frameCommande.grid(row=1, column=0, sticky='nsew', padx=24, pady=16)
            self.frameCommande.grid_columnconfigure(0, weight=3)
            self.frameCommande.grid_columnconfigure(1, weight=2)
            label(self.frameCommande, 'Livraison et commande', 29, 'bold').grid(row=0, column=0, sticky='w', padx=12, pady=(10, 8))
            label(self.frameCommande, '01  Panier     →     02  Livraison     →     03  Confirmation', 12, color=Style.muted).grid(row=1, column=0, sticky='w', padx=12, pady=(0, 22))
            self.InfoFrame = panel(self.frameCommande)
            self.InfoFrame.grid(row=2, column=0, sticky='ew', padx=(8, 18), pady=(0, 16))
            self.InfoFrame.grid_columnconfigure(0, weight=1)
            label(self.InfoFrame, f'{user.prenoms} {user.nom}', 17, 'bold').grid(row=0, column=0, sticky='w', padx=20, pady=(18, 2))
            label(self.InfoFrame, f'{user.email}  ·  {user.tel}', 12, color=Style.muted).grid(row=1, column=0, sticky='w', padx=20, pady=(0, 18))
            self.livraisonFrame = panel(self.frameCommande)
            self.livraisonFrame.grid(row=3, column=0, sticky='ew', padx=(8, 18), pady=(0, 16))
            self.livraisonFrame.grid_columnconfigure((0, 1), weight=1)
            label(self.livraisonFrame, 'Adresse et livraison', 20, 'bold').grid(row=0, column=0, columnspan=2, sticky='w', padx=20, pady=(20, 12))
            self.entry_ville = field(self.livraisonFrame, 'Ville', 'Abidjan', row=1)
            self.entry_quartier = field(self.livraisonFrame, 'Quartier / commune', 'Votre quartier', row=1, column=1)
            self.entry_complement = field(self.livraisonFrame, 'Rue / appartement (facultatif)', 'Précisions utiles', row=2)
            self.modeLivraison_var = customtkinter.StringVar(value='')
            self.pointRelais = customtkinter.CTkRadioButton(self.livraisonFrame, text='Point relais', variable=self.modeLivraison_var, value='relais', font=font(13), text_color=Style.ink, fg_color=Style.blue)
            self.pointRelais.grid(row=3, column=0, sticky='w', padx=20, pady=15)
            self.pointRelais.configure(state='disabled')
            self.selectRelais = customtkinter.CTkComboBox(self.livraisonFrame, values=[''], command=self.update_livraison, height=40, font=font(12), state='disabled')
            self.selectRelais.grid(row=4, column=0, sticky='ew', padx=20)
            self.relaisPrix = customtkinter.IntVar(value=0)
            self.relaisPrixVar = customtkinter.StringVar(value='À renseigner')
            label(self.livraisonFrame, textvariable=self.relaisPrixVar, size=13, weight='bold', color=Style.blue).grid(row=5, column=0, sticky='w', padx=20, pady=(8, 18))
            self.aDomicile = customtkinter.CTkRadioButton(self.livraisonFrame, text='À domicile', variable=self.modeLivraison_var, value='domicile', font=font(13), text_color=Style.ink, fg_color=Style.blue)
            self.aDomicile.grid(row=3, column=1, sticky='w', padx=20, pady=15)
            self.domicilePrix = customtkinter.IntVar(value=0)
            self.domicilePrixVar = customtkinter.StringVar(value='À renseigner')
            label(self.livraisonFrame, textvariable=self.domicilePrixVar, size=13, weight='bold', color=Style.blue).grid(row=4, column=1, sticky='w', padx=20, pady=8)
            self.point = label(self.livraisonFrame, 'Aucun relais pour cette ville. Livraison à domicile disponible.', 11, color=Style.muted, wraplength=460)
            self.livraison, self.livraison_city = self.get_livraisons()
            self.entry_ville.bind('<KeyRelease>', self.on_keyrelease_combined)
            self.paymentFrame = panel(self.frameCommande)
            self.paymentFrame.grid(row=4, column=0, sticky='ew', padx=(8, 18), pady=(0, 16))
            self.paymentFrame.grid_columnconfigure((0, 1, 2), weight=1)
            label(self.paymentFrame, 'Mode de paiement', 20, 'bold').grid(row=0, column=0, columnspan=3, sticky='w', padx=20, pady=(20, 12))
            self.image_buttons = {}
            for index, (name, caption) in enumerate([('Carte Bancaire', 'Carte · démo'), ('Wave', 'Wave · démo'), ('A la livraison', 'À la livraison')]):
                control = button(self.paymentFrame, caption, lambda name=name: self.on_select(name), 'light', width=130)
                control.grid(row=1, column=index, padx=8, pady=(0, 12), sticky='ew')
                self.image_buttons[name] = control
            self.modePaiementInfoFrame1 = customtkinter.CTkFrame(self.paymentFrame, fg_color=Style.soft)
            self.modePaiementInfoFrame1.grid_columnconfigure(0, weight=1)
            self.numeroCarte = field(self.modePaiementInfoFrame1, 'Carte fictive : quatre derniers chiffres uniquement', '4444')
            validator = self.register(lambda value: not value or len(value) <= 4 and value.isascii() and value.isdigit())
            self.numeroCarte.configure(validate='key', validatecommand=(validator, '%P'))
            self.modePaiementInfoFrame2 = customtkinter.CTkFrame(self.paymentFrame, fg_color=Style.soft)
            self.modePaiementInfoFrame2.grid_columnconfigure((0, 1), weight=1)
            self.entry_indicatif = field(self.modePaiementInfoFrame2, 'Indicatif', '+225')
            self.entry_indicatif.insert(0, '+225')
            self.numeroWave = field(self.modePaiementInfoFrame2, 'Numéro de démonstration', '0100000000', column=1)
            self.modePaiementInfoFrame3 = customtkinter.CTkFrame(self.paymentFrame, fg_color=Style.soft)
            label(self.modePaiementInfoFrame3, 'Commande de démonstration : aucun débit n’est effectué.', 12, color=Style.muted, wraplength=460).pack(padx=20, pady=16)
            self.selected_mode, self.detail_paiement = None, None
            label(self.paymentFrame, 'Carte et Wave sont simulés. Ne saisissez aucune donnée bancaire réelle.', 11, color=Style.muted, wraplength=500).grid(row=4, column=0, columnspan=3, sticky='w', padx=20, pady=(12, 20))
            self.recapFrame = panel(self.frameCommande)
            self.recapFrame.grid(row=2, column=1, rowspan=3, sticky='new', padx=(0, 8))
            self.recapFrame.grid_columnconfigure(0, weight=1)
            label(self.recapFrame, 'Votre sélection', 21, 'bold').grid(row=0, column=0, sticky='w', padx=20, pady=(22, 12))
            self.listProdFrame = customtkinter.CTkFrame(self.recapFrame, fg_color='white')
            self.listProdFrame.grid(row=1, column=0, sticky='ew', padx=12, pady=(0, 12))
            self.produits = self.get_panier(user_id)
            self.listProduit(self.produits)
            self.prix_prod = self.prix_panier(self.produits)
            self.Montant, self.prix_liv = self.prix_prod, 0
            label(self.recapFrame, f'Articles : {self.prix_prod:,.0f} FCFA'.replace(',', ' '), 14, color=Style.muted).grid(row=2, column=0, sticky='w', padx=20, pady=6)
            self.coutLivVar = customtkinter.StringVar(value='Livraison : à choisir')
            label(self.recapFrame, textvariable=self.coutLivVar, size=13, color=Style.muted).grid(row=3, column=0, sticky='w', padx=20, pady=6)
            self.coutTotVar = customtkinter.StringVar(value='À confirmer')
            label(self.recapFrame, textvariable=self.coutTotVar, size=26, weight='bold').grid(row=4, column=0, sticky='w', padx=20, pady=(12, 20))
            self.boutonCommander = button(self.recapFrame, 'Confirmer la démonstration  →', self.valider)
            self.boutonCommander.grid(row=5, column=0, sticky='ew', padx=20, pady=(0, 14))
            if self.delivery_unavailable or not self.produits or self.cart_unavailable:
                self.boutonCommander.configure(state='disabled')
            button(self.recapFrame, 'Modifier le panier', lambda: open_page('panier', self), 'light').grid(row=6, column=0, sticky='ew', padx=20, pady=(0, 22))
            self.form_message = label(self.recapFrame,'',12,color='#AD3544',wraplength=300,justify='left')
            self.form_message.grid(row=7,column=0,sticky='ew',padx=20,pady=(0,16))
            self.modeLivraison_var.trace_add('write', self.prixLivraison)
        
    
        

        
            def arrange(width):
                narrow = width < 1050
                self.frameCommande.grid_columnconfigure(1, weight=0 if narrow else 2)
                self.recapFrame.grid(row=5 if narrow else 2, column=0 if narrow else 1, rowspan=1 if narrow else 3, sticky='new', padx=8, pady=(16, 0) if narrow else 0)
            self._responsive = ResizeObserver(self.frameCommande, arrange)

        def load_image(self, path, size):
            """Charge et redimensionne une image."""
            try:
                with Image.open(path) as source:
                    img = source.resize(size, Image.Resampling.LANCZOS)
                return customtkinter.CTkImage(img, size=size)
            except (OSError, ValueError):
                return None

        def on_select(self, selected_option=None):
            for frame in (self.modePaiementInfoFrame1, self.modePaiementInfoFrame2,
                          self.modePaiementInfoFrame3):
                frame.grid_forget()
            for key, mode_button in self.image_buttons.items():
                mode_button.configure(fg_color='#2C65FF' if key == selected_option else '#EAF0FF',
                                 text_color='white' if key == selected_option else '#2C65FF')
            self.selected_mode = None
            self.detail_paiement = None
            options = {"Carte Bancaire": (1, self.modePaiementInfoFrame1),
                       "Wave": (2, self.modePaiementInfoFrame2),
                       "A la livraison": (3, self.modePaiementInfoFrame3)}
            if selected_option in options:
                self.selected_mode, frame = options[selected_option]
                frame.grid(row=3, column=0, columnspan=3, sticky="nsew", pady=10, padx=6)
            
                
        
        def validate_cvv(self, new_value):
            return len(new_value) <= 3 and (not new_value or new_value.isdigit())
        
        def get_panier(self, client_id):
            try:
                self.cart_unavailable = False
                return [(p[0], p[1], p[2], p[3], p[5]) for p in (initial_data['cart'] if initial_data is not None else get_cart(client_id))]
            except DatabaseError:
                self.cart_unavailable = True
                messagebox.showerror('Panier indisponible', 'Impossible de charger le panier. Réessayez plus tard.')
                return []
        


        def listProduit(self,produits):
            if not self.listProdFrame.winfo_exists():
                print("Erreur : Le cadre self.listProdFrame n'existe pas.")
                return
        
            for idx, produit in enumerate(produits):
                try:
                    image_path = relative_to_assets(f"{produit[3]}")
                    imgi = self.load_image(image_path, (50, 50))
                
                    customtkinter.CTkLabel(
                        self.listProdFrame, text="" if imgi else "Image\nindisponible", image=imgi
                    ).grid(row=idx * 3, column=0, rowspan=2, padx=(20, 10), pady=10, sticky="wns")
                
                    customtkinter.CTkLabel(
                        self.listProdFrame, text=f"{produit[0]}", wraplength=230, justify="left", font=customtkinter.CTkFont(size=13)
                    ).grid(row=idx * 3, column=0, sticky="sw", pady=(10, 0), padx=(90, 0))
                
                    customtkinter.CTkLabel(
                        self.listProdFrame, text=f"Quantité : {produit[1]}", font=customtkinter.CTkFont(size=12)
                    ).grid(row=idx * 3 + 1, column=0, sticky="nw", pady=0, padx=(90, 0))
                
                    customtkinter.CTkLabel(
                        self.listProdFrame, text=f"{produit[2]:,.0f} FCFA / unité".replace(',', ' '), font=customtkinter.CTkFont(size=12)
                    ).grid(row=idx * 3 + 1, column=1, sticky="e", padx=(80, 0))

                    customtkinter.CTkFrame(
                        self.listProdFrame, height=2, fg_color="lightgrey"
                    ).grid(row=idx * 3 + 2, column=0, columnspan=2, padx=(20, 0), pady=(2, 10), sticky="ew")
            
                except Exception as e:
                    print(f"Erreur lors de l'ajout du produit : {produit}. Détails : {e}")

    
        
        def get_villeQuartier(self):
            rows = [(city, district) for city, district, price in localities()]
            return ["city", "quartier"], rows
        
        def on_keyrelease(self, event=None):
            """ Déclenché après chaque frappe, mais attend 500 ms avant de vérifier """
            # Annuler l'événement précédent si l'utilisateur tape trop vite
            if self.last_keypress is not None:
                self.entry_ville.after_cancel(self.last_keypress)

            # Lancer la vérification de la ville après 500 ms
            self.last_keypress = self.entry_ville.after(500, self.check_ville_existence)
        
        
        def on_keyrelease2(self, event=None):
            """ Déclenché après chaque frappe, mais attend 500 ms avant de vérifier """
            # Annuler l'événement précédent si l'utilisateur tape trop vite
            if self.last_keypress is not None:
                self.entry_ville.after_cancel(self.last_keypress)

            # Lancer la vérification de la ville après 500 ms
            self.last_keypress = self.entry_ville.after(500, self.update_livraison)

        def check_ville_existence(self):
            ville = self.entry_ville.get().strip().casefold()
            districts = self.delivery_districts.get(ville, [])
            previous_city = getattr(self, "_delivery_city", None)
            selected = self.selectRelais.get()
            if districts:
                self.pointRelais.configure(state="normal")
                self.selectRelais.configure(state="normal", values=districts)
                if previous_city != ville or selected not in districts:
                    self.selectRelais.set(districts[0])
                    if self.modeLivraison_var.get() == "relais":
                        self.modeLivraison_var.set("")
                self.point.grid_forget()
            else:
                self.pointRelais.configure(state="disabled")
                self.selectRelais.configure(state="disabled", values=[" "])
                self.selectRelais.set("")
                self.modeLivraison_var.set("domicile")
                self.point.grid(row=6, column=0, columnspan=2, sticky='w', padx=20, pady=(0,15))
            self._delivery_city = ville
            
        def display_message(self, title, message):
            """ Afficher un message contextuel (comme une boîte de message) """
            messagebox.showinfo(title, message)  # Affichage d'un message contextuel avec info
        
        
    

            
        def get_livraisons(self):
            try:
                rows = initial_data['localities'] if initial_data is not None else localities()
                rates = delivery_rates(rows)
            except DatabaseError:
                self.delivery_unavailable = True
                messagebox.showerror("Livraison indisponible", "Impossible de charger les tarifs. Ressaisissez la ville pour réessayer.")
                return {}, {}
            self.delivery_unavailable = False
            self.delivery_districts = {}
            for city, district, price in rows:
                self.delivery_districts.setdefault(city.strip().casefold(), []).append(district)
            return rates
            
        def update_livraison(self, event=None):
            key = (self.entry_ville.get().strip().casefold(),
                   self.selectRelais.get().strip().casefold())
            tarif = self.livraison.get(key, 6000)
            self.relaisPrix.set(tarif)
            self.relaisPrixVar.set(f"{tarif} FCFA")
            self.prixLivraison()
        
        
        

        def update_livraison2(self, event=None):
            ville = self.entry_ville.get().strip().casefold()
            tarif = self.livraison_city.get(ville, 6000)
            tarif = int(Decimal(str(tarif)) * Decimal("1.2"))
            self.domicilePrix.set(tarif)
            self.domicilePrixVar.set(f"{tarif} FCFA")
            self.prixLivraison()

        def on_keyrelease_combined(self, event=None):
            """Déclenché après chaque frappe, exécute plusieurs actions après un délai."""
            # Annuler l'événement précédent si l'utilisateur tape trop vite
            if self.last_keypress is not None:
                self.entry_ville.after_cancel(self.last_keypress)

            # Lancer les vérifications et mises à jour après 500 ms
            self.last_keypress = self.entry_ville.after(500, self.execute_all_keyrelease_actions)

        def execute_all_keyrelease_actions(self):
            """Exécute toutes les actions nécessaires après un délai."""
            self.last_keypress = None
            self.livraison, self.livraison_city = self.get_livraisons()
            if self.delivery_unavailable:
                self.boutonCommander.configure(state="disabled")
                for variable in (self.relaisPrixVar, self.domicilePrixVar,
                                 self.coutLivVar, self.coutTotVar):
                    variable.set("Indisponible")
                return
            self.check_ville_existence()  # Action 1
            self.update_livraison2()      # Action 2
            self.update_livraison()       # Action 3
            self.boutonCommander.configure(state='normal' if self.produits and not getattr(self, 'cart_unavailable', False) else 'disabled')
        
        def prixLivraison(self,*args):
            if getattr(self, "delivery_unavailable", False):
                self.coutLivVar.set("Indisponible")
                self.coutTotVar.set("Indisponible")
                return
            if self.modeLivraison_var.get() not in ('relais', 'domicile'):
                self.coutLivVar.set('Livraison : à choisir')
                self.coutTotVar.set('À confirmer')
                return
            if self.modeLivraison_var.get() =="relais":
                self.prix_liv = self.relaisPrix.get()
                self.coutLivVar.set(f"{self.prix_liv} FCFA")
                self.Montant = self.prix_liv + self.prix_prod
                self.coutTotVar.set(f"{self.Montant:,.0f} FCFA".replace(',', ' '))
            else: 
                self.prix_liv = self.domicilePrix.get()
                self.coutLivVar.set(f"{self.prix_liv} FCFA")
                self.Montant = self.prix_liv + self.prix_prod
                self.coutTotVar.set(f"{self.Montant:,.0f} FCFA".replace(',', ' '))
            
        
        
            
        def prix_panier(self,produits):
            self.prix = 0
            for i in produits:
                self.prix = self.prix + i[2]*i[1]
            
            return self.prix


        
        def validWave(self):
            if self.selected_mode != 2:
                return True
            indicatif = self.entry_indicatif.get().strip().removeprefix("+")
            numero = self.numeroWave.get().strip()
            return (indicatif.isascii() and indicatif.isdigit() and 1 <= len(indicatif) <= 3
                    and numero.isascii() and numero.isdigit() and 8 <= len(numero) <= 10)

        def validCarte(self):
            if self.selected_mode != 1:
                return True
            numero = self.numeroCarte.get().strip()
            return numero.isascii() and numero.isdigit() and len(numero) == 4

        def valider(self):
            if current_user_id()!=user_id:
                open_page('connexion',self,return_to='panier');return False
            if getattr(self,'delivery_unavailable',False) or getattr(self,'cart_unavailable',False):
                form_notice(self,'Rechargez le panier et les tarifs avant de confirmer.');return False
            for entry in (self.entry_ville,self.entry_quartier,self.numeroCarte,self.entry_indicatif,self.numeroWave):field_error(entry)
            if not self.entry_ville.get().strip() or not self.entry_quartier.get().strip():
                if not self.entry_ville.get().strip():field_error(self.entry_ville,'Renseignez la ville.')
                if not self.entry_quartier.get().strip():field_error(self.entry_quartier,'Renseignez le quartier ou la commune.')
                form_notice(self,'Complétez votre adresse.');return False
            if self.modeLivraison_var.get() not in ('relais','domicile'):
                form_notice(self,'Choisissez un mode de livraison.');return False
            if self.selected_mode not in (1,2,3):
                form_notice(self,'Choisissez un mode de paiement de démonstration.');return False
            if not self.validCarte():
                field_error(self.numeroCarte,'Saisissez exactement quatre chiffres fictifs.');return False
            if not self.validWave():
                field_error(self.numeroWave,'Indicatif et numéro de 8 à 10 chiffres attendus.');return False
            details={}
            if self.selected_mode==1:details['carte_fin']=self.numeroCarte.get().strip()
            elif self.selected_mode==2:details['telephone']=self.entry_indicatif.get().strip()+' '+self.numeroWave.get().strip()
            request=dict(city=self.entry_ville.get(),district=self.entry_quartier.get(),residence=self.entry_complement.get(),
                         delivery_mode=self.modeLivraison_var.get(),relay=self.selectRelais.get(),displayed_total=self.Montant,
                         payment_mode=self.selected_mode,payment_details=details)
            products=list(self.produits)
            form_notice(self,'Enregistrement de votre commande…')
            def save():
                if current_user_id()!=user_id:raise ValueError('Reconnectez-vous avant de confirmer.')
                return place_order(user_id,products,**request)
            def ready(result):
                self.detail_paiement=result['payment']
                open_page(f"confirmation:{result['id']}",self,receipt=result)
            def failed(error):
                if getattr(self,'form_message',None) is not None:form_notice(self,str(error))
                else:messagebox.showerror('Commande non enregistrée',str(error))
            return run_task(self,save,ready,failed,(getattr(self,'boutonCommander',None),))

    app = Commander()

    return app

