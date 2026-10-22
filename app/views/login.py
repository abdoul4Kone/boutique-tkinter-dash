"""Connexion client et retour à la fiche ou au panier demandé."""
import re
import customtkinter as ctk
from app.accounts import SessionManager
from app.runtime import PageFrame, run_task
from app.navigation import open_page, normalize_return
from app.views.components import Style, setup_window, header, footer, label, button, panel, field, split_panels, field_error, form_notice


def main(product_id=None, return_to='accueil', parent=None, initial_data=None):
    if parent is None:
        from app.runtime import launch
        return launch('connexion', return_to=return_to)
    RETURN_PAGE = normalize_return(return_to)

    class Login(PageFrame):
        def __init__(self):
            super().__init__(parent)
            setup_window(self, 'Connexion')
            header(self)
            footer(self)
            body = ctk.CTkScrollableFrame(self, fg_color=Style.bg, corner_radius=0)
            body.grid(row=1, column=0, sticky='nsew', padx=20, pady=20)
            body.grid_columnconfigure((0, 1), weight=1, uniform='account')
            body.grid_rowconfigure(0, weight=1)
            welcome = ctk.CTkFrame(body, fg_color=Style.ink, corner_radius=20)
            welcome.grid(row=0, column=0, sticky='nsew', padx=(0, 25))
            label(welcome, 'VOTRE ESPACE GROUP9', 11, 'bold', color='#B9D4FF').pack(anchor='w', padx=32, pady=(65, 20))
            label(welcome, 'Heureux de\nvous retrouver.', 34, 'bold', color='white', justify='left').pack(anchor='w', padx=32)
            label(welcome, 'Votre sélection, votre panier,\nla suite de votre découverte.', 15, color='#CCD9EA', justify='left').pack(anchor='w', padx=32, pady=24)
            form = panel(body)
            form.grid(row=0, column=1, sticky='nsew')
            form.grid_columnconfigure(0, weight=1)
            label(form, 'Se connecter', 27, 'bold').grid(row=0, column=0, sticky='w', padx=28, pady=(45, 7))
            label(form, 'Saisissez les identifiants de votre compte.', 13, color=Style.muted, wraplength=320, justify='left').grid(row=1, column=0, sticky='w', padx=28, pady=(0, 22))
            self.entry_email = field(form, 'Adresse électronique', 'vous@exemple.com', row=2)
            self.entry_password = field(form, 'Mot de passe', 'Votre mot de passe', row=3, show='•')
            self.submit_button = button(form, 'Continuer  →', self.verification)
            self.submit_button.grid(row=4, column=0, sticky='ew', padx=24, pady=(24, 14))
            label(form, 'Pas encore de compte ?', 12, color=Style.muted).grid(row=5, column=0, pady=(14, 4))
            button(form, 'Créer un compte', self.register, 'light').grid(row=6, column=0, sticky='ew', padx=24, pady=(0, 30))
            self.form_message = label(form, '', 12, color='#AD3544', wraplength=340, justify='left')
            self.form_message.grid(row=7,column=0,sticky='ew',padx=24,pady=(0,15))
            self._responsive = split_panels(body, welcome, form, breakpoint=850)
            self.bind('<Return>', lambda event: self.verification())

        def register(self):
            open_page('inscription', self, return_to=RETURN_PAGE)

        def verification(self):
            email,mdp=self.entry_email.get().strip(),self.entry_password.get()
            field_error(self.entry_email);field_error(self.entry_password);form_notice(self,'')
            invalid=False
            if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',email) or len(email)>100:
                field_error(self.entry_email,'Saisissez une adresse électronique valide.');invalid=True
            if not mdp:
                field_error(self.entry_password,'Renseignez votre mot de passe.');invalid=True
            if invalid:return False
            form_notice(self,'Connexion en cours…')
            def ready(authenticated):
                if authenticated:open_page(RETURN_PAGE,self)
                else:form_notice(self,'Adresse électronique ou mot de passe incorrect.')
            def failed(error):
                text='Session indisponible : vérifiez les droits du dossier local.' if isinstance(error,OSError) else 'Connexion indisponible : vérifiez la base et réessayez.'
                form_notice(self,text)
            return run_task(self,lambda:SessionManager().login(email=email,password=mdp),ready,failed,
                            (self.submit_button,),auth=True)

    app = Login()
    return app
