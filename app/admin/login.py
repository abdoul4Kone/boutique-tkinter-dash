"""Accès administrateur ; le serveur Dash vérifie aussi chaque requête."""
from tkinter import messagebox
import customtkinter as ctk
import hmac
import threading
import time
import webbrowser
from urllib.request import urlopen
from urllib.error import HTTPError, URLError
from app.config import admin_credentials
from app.runtime import PageFrame
from app.navigation import open_page
from app.views.components import Style, setup_window, footer, label, button, panel, field, split_panels


def main(parent=None, **options):
    if parent is None:
        from app.runtime import launch
        return launch('administration')
    username, password = admin_credentials()

    def open_webpage():
        url = 'http://127.0.0.1:8050/'
        for attempt in range(60):
            try:
                with urlopen(url, timeout=1):
                    pass
            except HTTPError as error:
                if error.code != 401:
                    time.sleep(0.5)
                    continue
            except (URLError, TimeoutError):
                time.sleep(0.5)
                continue
            webbrowser.open(url)
            return
        print('Le tableau de bord ne répond pas. Vérifiez le serveur MySQL et les dépendances.')

    class Login(PageFrame):
        def __init__(self):
            super().__init__(parent)
            setup_window(self, 'Administration')
            top = ctk.CTkFrame(self, fg_color=Style.ink, corner_radius=0, height=78)
            top.grid(row=0, column=0, sticky='ew')
            top.grid_columnconfigure(0, weight=1)
            label(top, 'GROUP9  /  INSIGHTS', 18, 'bold', color='white').grid(row=0, column=0, sticky='w', padx=35, pady=24)
            button(top, '← Retour à la boutique', lambda: open_page('accueil', self), 'nav', width=200).grid(row=0, column=1, padx=30)
            footer(self)
            body = ctk.CTkScrollableFrame(self, fg_color=Style.bg, corner_radius=0)
            body.grid(row=1, column=0, sticky='nsew', padx=20, pady=20)
            body.grid_columnconfigure((0, 1), weight=1, uniform='admin')
            copy = ctk.CTkFrame(body, fg_color='transparent')
            copy.grid(row=0, column=0, sticky='nw', padx=(0, 30), pady=35)
            label(copy, 'ESPACE ADMINISTRATEUR', 11, 'bold', color=Style.blue).pack(anchor='w', pady=(0, 20))
            label(copy, 'Une vue claire.\nDe meilleurs repères.', 32, 'bold', justify='left').pack(anchor='w')
            label(copy, 'Ventes, stocks, prévisions et clients.\nLes indicateurs réunis dans un même espace.', 14, color=Style.muted, justify='left').pack(anchor='w', pady=24)
            form = panel(body)
            form.grid(row=0, column=1, sticky='new')
            form.grid_columnconfigure(0, weight=1)
            label(form, 'Accéder aux analyses', 25, 'bold').grid(row=0, column=0, sticky='w', padx=25, pady=(30, 20))
            self.entry_email = field(form, 'Identifiant administrateur', 'Votre identifiant', row=1)
            self.entry_password = field(form, 'Mot de passe', 'Votre mot de passe', row=2, show='•')
            button(form, 'Ouvrir le tableau de bord  →', self.verification).grid(row=3, column=0, sticky='ew', padx=22, pady=(24, 15))
            label(form, 'Le navigateur demandera les mêmes identifiants.', 11, color=Style.muted, wraplength=340).grid(row=4, column=0, sticky='w', padx=22, pady=(0, 26))
            self._responsive = split_panels(body, copy, form, breakpoint=850)
            self.bind('<Return>', lambda event: self.verification())

        def verification(self):
            valid_user = hmac.compare_digest(self.entry_email.get().strip().encode('utf-8'), username.encode('utf-8'))
            valid_password = hmac.compare_digest(self.entry_password.get().encode('utf-8'), password.encode('utf-8'))
            if not (valid_user and valid_password):
                messagebox.showerror('Accès refusé', 'Identifiant ou mot de passe incorrect.', parent=self)
                return False
            open_page('tableau-de-bord', self)
            threading.Thread(target=open_webpage).start()
            return True

    app = Login()
    return app
