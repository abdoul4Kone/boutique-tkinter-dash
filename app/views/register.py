"""Création d'un compte client avec validation partagée côté service."""
import tkinter as tk
import customtkinter as ctk
from app.accounts import register_customer
from app.forms import registration_errors
from app.runtime import PageFrame, run_task
from app.navigation import open_page, normalize_return
from app.views.components import Style, font, setup_window, header, footer, label, button, panel, field, ResizeObserver, field_error, form_notice


def main(product_id=None, return_to='accueil', parent=None, initial_data=None):
    if parent is None:
        from app.runtime import launch
        return launch('inscription', return_to=return_to)
    RETURN_PAGE = normalize_return(return_to)

    class Register(PageFrame):
        def __init__(self):
            super().__init__(parent)
            setup_window(self, 'Créer un compte')
            header(self)
            footer(self)
            scroll = ctk.CTkScrollableFrame(self, fg_color=Style.bg, corner_radius=0)
            scroll.grid(row=1, column=0, sticky='nsew', padx=18, pady=20)
            scroll.grid_columnconfigure(0, weight=1)
            label(scroll, 'Bienvenue chez Group9.', 29, 'bold').grid(row=0, column=0, sticky='w', padx=15, pady=(10, 6))
            label(scroll, 'Un compte pour retrouver votre panier et poursuivre vos achats.', 14, color=Style.muted, wraplength=520, anchor='w', justify='left').grid(row=1, column=0, sticky='w', padx=15, pady=(0, 22))
            form = panel(scroll)
            form.grid(row=2, column=0, sticky='ew', padx=10)
            form.grid_columnconfigure((0, 1), weight=1, uniform='fields')
            self.entry_nom = field(form, 'Nom', 'Votre nom', row=0)
            self.entry_prenom = field(form, 'Prénoms', 'Vos prénoms', row=0, column=1)
            self.entry_email = field(form, 'Adresse électronique', 'vous@exemple.com', row=1)
            self.entry_birth = field(form, 'Date de naissance', 'AAAA-MM-JJ', row=1, column=1)
            self.entry_password = field(form, 'Mot de passe · 12 caractères minimum', 'Créer un mot de passe', row=2, show='•')
            self.entry_password_confirm = field(form, 'Confirmer le mot de passe', 'Saisir à nouveau', row=2, column=1, show='•')
            self.entry_indicatif = field(form, 'Indicatif', '+225', row=3)
            self.entry_indicatif.insert(0, '+225')
            self.entry_tel = field(form, 'Téléphone', '0100000000', row=3, column=1)
            group = ctk.CTkFrame(form, fg_color='transparent')
            group.grid(row=4, column=0, sticky='ew', padx=12, pady=12)
            label(group, 'Sexe', 12, 'bold').pack(anchor='w', pady=(0, 8))
            self.selected_sexe = tk.StringVar(self, value='Masculin')
            ctk.CTkOptionMenu(group, values=['Masculin', 'Feminin'], variable=self.selected_sexe,
                              fg_color=Style.ink, button_color=Style.ink, height=42).pack(fill='x')
            self.conditions_var = tk.BooleanVar(self, value=False)
            ctk.CTkCheckBox(form, text='Je confirme les informations saisies.', variable=self.conditions_var,
                            font=font(12), text_color=Style.ink, fg_color=Style.blue).grid(row=5, column=0, columnspan=2, sticky='w', padx=20, pady=(16, 10))
            self.submit_button = button(form, 'Créer mon compte  →', self.valid3)
            self.submit_button.grid(row=6, column=0, columnspan=2, sticky='ew', padx=20, pady=(10, 12))
            button(form, 'J’ai déjà un compte', lambda: open_page('connexion', self, return_to=RETURN_PAGE), 'light').grid(row=7, column=0, columnspan=2, sticky='ew', padx=20, pady=(0, 22))

            self.form_message = label(form,'',12,color='#AD3544',wraplength=480,justify='left')
            self.form_message.grid(row=8,column=0,columnspan=2,sticky='ew',padx=20,pady=(0,12))
            fields = [self.entry_nom, self.entry_prenom, self.entry_email, self.entry_birth,
                      self.entry_password, self.entry_password_confirm, self.entry_indicatif, self.entry_tel]
            trailing = [child for child in form.winfo_children() if child not in [entry._field_group for entry in fields]]
            def arrange(width):
                narrow = width < 620
                form.grid_columnconfigure(0, weight=1, uniform='' if narrow else 'fields', minsize=0)
                form.grid_columnconfigure(1, weight=0 if narrow else 1, uniform='' if narrow else 'fields', minsize=0)
                for i, entry in enumerate(fields):
                    entry._field_group.grid(row=i if narrow else i//2, column=0 if narrow else i%2, sticky='ew')
                for child in trailing:
                    info = getattr(child, '_wide_grid', None)
                    if info is None:
                        info = dict(child.grid_info())
                        child._wide_grid = info
                    child.grid(row=int(info['row'])+(4 if narrow else 0), column=int(info['column']),
                               columnspan=1 if narrow else int(info['columnspan']))
            self._responsive = ResizeObserver(form, arrange)

        def valid3(self):
            values={'nom':self.entry_nom.get(),'prenoms':self.entry_prenom.get(),'email':self.entry_email.get(),
                    'birth':self.entry_birth.get(),'password':self.entry_password.get(),'confirmation':self.entry_password_confirm.get(),
                    'prefix':self.entry_indicatif.get(),'phone':self.entry_tel.get()}
            fields={'nom':self.entry_nom,'prenoms':self.entry_prenom,'email':self.entry_email,'birth':self.entry_birth,
                    'password':self.entry_password,'confirmation':self.entry_password_confirm,'prefix':self.entry_indicatif,'phone':self.entry_tel}
            for entry in fields.values():field_error(entry)
            errors=registration_errors(values)
            for key,text in errors.items():field_error(fields[key],text)
            if errors:
                form_notice(self,'Corrigez les champs indiqués avant de continuer.');return False
            if not self.conditions_var.get():
                form_notice(self,'Confirmez les informations saisies avant de continuer.');return False
            return self.ajouter_client()

        def ajouter_client(self):
            values=(self.entry_nom.get(),self.entry_prenom.get(),self.selected_sexe.get(),self.entry_birth.get().strip(),
                    self.entry_email.get(),self.entry_password.get(),self.entry_indicatif.get().strip()+' '+self.entry_tel.get().strip())
            form_notice(self,'Création du compte en cours…')
            def ready(result):
                open_page('connexion',self,return_to=RETURN_PAGE)
            def failed(error):
                text='Cette adresse est déjà associée à un compte.' if getattr(error,'errno',None)==1062 else 'La création du compte est indisponible. Réessayez.'
                if isinstance(error,ValueError):text=str(error)
                if getattr(error,'errno',None)==1062:field_error(self.entry_email,text)
                form_notice(self,text)
            return run_task(self,lambda:register_customer(*values),ready,failed,(self.submit_button,))

    app = Register()
    return app
