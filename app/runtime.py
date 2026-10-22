"""Une fenêtre Tk, des pages internes et des lectures MySQL hors du fil graphique."""
from concurrent.futures import ThreadPoolExecutor
from importlib import import_module
import itertools
import queue
import tkinter as tk

from app.accounts import current_user_id
from app.navigation import ROUTES, split_target, normalize_return


class PageFrame(tk.Frame):
    def __init__(self, parent):
        super().__init__(parent, borderwidth=0, highlightthickness=0)
        self._app_controller = parent._app_controller
        self.grid(row=0, column=0, sticky='nsew')
        self._return_handler = None

    def title(self, value=None):
        return self._app_controller.root.title(value)

    def geometry(self, value=None):
        # Les anciennes vues ne changent plus les dimensions choisies par l'utilisateur.
        return self._app_controller.root.geometry()

    def minsize(self, *args):
        root = self._app_controller.root
        if args and hasattr(root, '_get_window_scaling'):
            scale = root._get_window_scaling()
            return root.minsize(*(round(value / scale) for value in args))
        return root.minsize(*args)

    def resizable(self, *args):
        return self._app_controller.root.resizable()

    def protocol(self, *args):
        return None

    def bind(self, sequence=None, func=None, add=None):
        if sequence == '<Return>':
            self._return_handler = func
            return None
        return super().bind(sequence, func, add)


def run_task(owner, operation, success, failure, controls=(), auth=False):
    """Seules les fonctions operation sont exécutées dans un thread de travail."""
    controller = getattr(owner, '_app_controller', None)
    if isinstance(controller, Application):
        return controller.submit(owner, operation, success, failure, controls, auth=auth)
    try:
        result = operation()
    except Exception as error:
        failure(error)
        return False
    success(result)
    return True


class Application:
    def __init__(self, root=None):
        from app.views.components import setup_window
        import customtkinter as ctk
        self.root = root if root is not None else ctk.CTk()
        self.root._app_controller = self
        setup_window(self.root, 'Boutique')
        scale = self.root._get_window_scaling() if hasattr(self.root, '_get_window_scaling') else 1
        width = round(min(1320,self.root.winfo_screenwidth()-60) / scale)
        height = round(min(880,self.root.winfo_screenheight()-90) / scale)
        self.root.geometry(f'{width}x{height}+25+25')
        self.root.grid_rowconfigure(0, weight=1)
        self.root.grid_rowconfigure(1, weight=0)
        self.root.protocol('WM_DELETE_WINDOW', self.close)
        self.root.bind('<Return>', self.enter)
        self.executor = ThreadPoolExecutor(max_workers=3, thread_name_prefix='group9-data')
        self.queue, self.jobs, self.sequence = queue.Queue(), {}, itertools.count()
        self.page, self.target = None, None
        self.browse_state, self.history, self.receipts = {}, [], {}
        self.external = {}
        self.identity = current_user_id()
        self.closing = False
        self.auth_pending = None
        self.root.after(40, self.poll)

    def enter(self, event):
        handler = getattr(self.page, '_return_handler', None)
        if handler and self.page.winfo_exists():
            handler(event)

    def remember(self):
        if self.page is None or not self.page.winfo_exists():
            return
        view = getattr(self.page, '_view', None)
        if self.target in ('accueil', 'catalogue') and view:
            self.browse_state[self.target] = {
                'query': view.search.get(), 'sort': view.sort.get(), 'category': view.selected,
                'position': view.scroll._parent_canvas.yview()[0],
            }

    def navigate(self, target, return_to=None, receipt=None, record=True):
        from app.views.components import header, footer, label, button, Style
        import customtkinter as ctk
        if self.auth_pending is not None:
            return False
        route, number = split_target(target)
        if route in ('tableau-de-bord', 'generer-clients', 'generer-commandes'):
            return self.open_external(target)
        identity = current_user_id()
        if identity != self.identity:
            self.receipts.clear()
            self.history.clear()
            self.identity = identity
        if route in ('panier', 'commande', 'mes-commandes', 'confirmation') and identity is None:
            return self.navigate('connexion', return_to=target, record=False)
        if receipt and route == 'confirmation':
            self.receipts[(identity, number)] = receipt
        self.remember()
        if record and self.target and self.target != target and self.target not in ('connexion', 'inscription'):
            self.history.append(self.target)
        if self.page is not None:
            self.page.destroy()
        # Chaque lecture est rattachée à sa page ; un résultat d'une page quittée est ignoré.
        self.target = target
        loading = self.page = PageFrame(self.root)
        loading.grid_columnconfigure(0, weight=1)
        loading.grid_rowconfigure(1, weight=1)
        header(loading)
        footer(loading)
        body = ctk.CTkFrame(loading, fg_color=Style.bg, corner_radius=0)
        body.grid(row=1, column=0, sticky='nsew')
        label(body, 'Chargement de votre espace…', 23, 'bold').pack(pady=(75, 20))
        progress = ctk.CTkProgressBar(body, width=240, mode='indeterminate', progress_color=Style.blue)
        progress.pack(); progress.start()
        def ready(data):
            progress.stop()
            loading.destroy()
            self.page = None
            try:
                page = import_module(ROUTES[route]).main(parent=self.root, product_id=number,
                    return_to=normalize_return(return_to or 'accueil'), initial_data=data)
                self.page = page
                if route in self.browse_state:
                    state = self.browse_state[route]
                    view = page._view
                    view.search.insert(0, state['query'])
                    view.sort.set(state['sort'])
                    view.select_category(state['category'])
                    self.restore_scroll(page, view, state['position'])
            except Exception as error:
                for child in self.root.winfo_children():
                    if isinstance(child, PageFrame):child.destroy()
                self.page = PageFrame(self.root)
                header(self.page);footer(self.page)
                label(self.page, 'Cet écran est indisponible. Réessayez.', 18).grid(row=1, column=0, pady=40)
                button(self.page, 'Réessayer', lambda:self.navigate(target,return_to=return_to,record=False)).grid(row=3,column=0,pady=20)
                self.root.report_callback_exception(type(error),error,error.__traceback__)
        def failed(error):
            progress.stop()
            for child in body.winfo_children():child.destroy()
            saved = self.receipts.get((identity, number)) if route == 'confirmation' else None
            title = f'Commande G9-{number:06d} enregistrée' if saved else 'Chargement indisponible'
            message = ('La commande est enregistrée. Son détail est momentanément indisponible.' if saved
                       else 'Vérifiez la connexion à la base puis réessayez.')
            label(body, title, 23, 'bold', wraplength=480).pack(pady=(60, 15))
            label(body, message, 14, color=Style.muted, wraplength=480).pack(pady=10)
            button(body, 'Réessayer', lambda:self.navigate(target,return_to=return_to,record=False)).pack(pady=15)
            button(body, 'Mes commandes' if saved else 'Retour',
                   lambda:self.navigate('mes-commandes') if saved else self.back(), 'light').pack(pady=5)
        return self.submit(loading, lambda:self.prepare(route,number,identity), ready, failed)

    def restore_scroll(self, page, view, position):
        """Attendre la fin de la mise en page avant de rétablir le défilement."""
        def settle(previous=None, attempts=0):
            if page is not self.page or not page.winfo_exists():
                return
            canvas = view.scroll._parent_canvas
            layout = (canvas.bbox('all'), canvas.winfo_width(), canvas.winfo_height(), view.columns)
            pending = any(getattr(widget._responsive, 'pending', None)
                          for widget in (view.controls, view.filters, view.cards))
            if (layout == previous and not pending) or attempts >= 15:
                canvas.yview_moveto(position)
            else:
                self.root.after(60, lambda: settle(layout, attempts + 1))
        self.root.after_idle(settle)

    def prepare(self, route, number, identity):
        from app import commerce
        if route in ('accueil','catalogue'):
            return {'products':commerce.get_products()}
        if route == 'produit':
            return {'products':commerce.get_products(number), 'cart':commerce.get_cart(identity) if identity else []}
        if route == 'panier':
            return {'cart':commerce.get_cart(identity)}
        if route == 'commande':
            return {'cart':commerce.get_cart(identity),'customer':commerce.get_customer(identity),'localities':commerce.localities()}
        if route == 'mes-commandes':
            return commerce.get_customer_orders(identity)
        if route == 'confirmation':
            return commerce.get_order_details(identity, number)
        return {}

    def submit(self, owner, operation, success, failure, controls=(), auth=False):
        if getattr(owner,'_task_busy',False):
            return False
        owner._task_busy = True
        if auth:self.auth_pending = owner
        controls = tuple(control for control in controls if control is not None)
        states = tuple((control,control.cget('state')) for control in controls)
        for control in controls:control.configure(state='disabled')
        token = next(self.sequence)
        self.jobs[token] = (owner,success,failure,states,current_user_id(),auth)
        future = self.executor.submit(operation)
        future.add_done_callback(lambda done:self.queue.put((token,done)))
        return True

    def poll(self):
        if self.closing:return
        while True:
            try:token,future = self.queue.get_nowait()
            except queue.Empty:break
            job = self.jobs.pop(token,None)
            if job is None:continue
            owner,success,failure,controls,identity,auth = job
            if auth:self.auth_pending = None
            if not owner.winfo_exists():continue
            owner._task_busy = False
            for control,state in controls:
                if control.winfo_exists():control.configure(state=state)
            if not auth and identity != current_user_id():
                self.navigate('connexion',return_to='mes-commandes',record=False)
                continue
            try:result=future.result()
            except Exception as error:failure(error)
            else:success(result)
        self.root.after(40,self.poll)

    def back(self):
        target = self.history.pop() if self.history else 'catalogue'
        self.navigate(target,record=False)

    def open_external(self, target):
        import subprocess,sys
        from app.navigation import command_for
        from app.config import ROOT_DIR
        previous=self.external.get(target)
        if previous is not None and previous.poll() is None:return previous
        options={'cwd':ROOT_DIR}
        if sys.platform=='win32':options['creationflags']=subprocess.CREATE_NO_WINDOW
        process=subprocess.Popen(command_for(target),**options)
        self.external[target]=process
        return process

    def close(self):
        self.closing=True
        self.executor.shutdown(wait=False,cancel_futures=True)
        self.root.destroy()


def launch(target='accueil', return_to=None):
    app=Application()
    app.navigate(target,return_to=return_to)
    app.root.mainloop()
    return app
