"""Historique personnel et détail des commandes de démonstration."""
from datetime import datetime
from decimal import Decimal
import customtkinter as ctk
from app.runtime import PageFrame,run_task
from app.accounts import current_user_id
from app.commerce import get_customer_orders
from app.navigation import open_page
from app.views.components import Style,label,button,panel,header,footer,setup_window,ResizeObserver


def money(value):
    if value is None:return 'Non documenté'
    return f'{Decimal(str(value)):,.0f} FCFA'.replace(',',' ')


def date_label(value):
    if isinstance(value,str):
        try:value=datetime.fromisoformat(value)
        except ValueError:return value
    return value.strftime('%d/%m/%Y à %H:%M') if value else 'Date non documentée'


class OrdersPage(PageFrame):
    def __init__(self,parent,initial_data):
        super().__init__(parent)
        setup_window(self,'Mes commandes');header(self,'mes-commandes');footer(self)
        self.user_id=current_user_id()
        self.scroll=ctk.CTkScrollableFrame(self,fg_color=Style.bg,corner_radius=0)
        self.scroll.grid(row=1,column=0,sticky='nsew',padx=20,pady=16)
        self.scroll.grid_columnconfigure(0,weight=1)
        label(self.scroll,'VOTRE ESPACE / COMMANDES',11,'bold',color=Style.blue).grid(row=0,column=0,sticky='w',padx=12,pady=(10,8))
        label(self.scroll,'Mes commandes',31,'bold').grid(row=1,column=0,sticky='w',padx=12)
        label(self.scroll,'Retrouvez vos sélections et leurs montants enregistrés.',14,color=Style.muted,wraplength=480,justify='left').grid(row=2,column=0,sticky='w',padx=12,pady=(8,20))
        self.list=ctk.CTkFrame(self.scroll,fg_color='transparent')
        self.list.grid(row=3,column=0,sticky='ew');self.list.grid_columnconfigure(0,weight=1)
        self.paging=ctk.CTkFrame(self.scroll,fg_color='transparent')
        self.paging.grid(row=4,column=0,sticky='ew',padx=12,pady=18);self.paging.grid_columnconfigure(1,weight=1)
        self.previous=button(self.paging,'Précédentes',lambda:self.load(-1),'light',width=140)
        self.previous.grid(row=0,column=0)
        self.count=label(self.paging,'',12,color=Style.muted);self.count.grid(row=0,column=1)
        self.next=button(self.paging,'Suivantes',lambda:self.load(1),'light',width=140);self.next.grid(row=0,column=2)
        self.message=label(self.scroll,'',13,color='#AD3544',wraplength=500);self.message.grid(row=5,column=0,sticky='w',padx=12)
        self.draw(initial_data)

    def draw(self,data):
        self.data=data
        for child in self.list.winfo_children():child.destroy()
        if not data['orders']:
            empty=panel(self.list);empty.grid(row=0,column=0,sticky='ew',padx=10,pady=10)
            label(empty,'Votre histoire commence ici.',23,'bold').pack(padx=25,pady=(30,12))
            label(empty,'Vos commandes apparaîtront après leur confirmation.',14,color=Style.muted,wraplength=390).pack(padx=25,pady=10)
            button(empty,'Découvrir la collection',lambda:open_page('catalogue',self)).pack(padx=25,pady=(10,30))
        for index,order in enumerate(data['orders']):
            card=panel(self.list);card.grid(row=index,column=0,sticky='ew',padx=10,pady=7)
            card.grid_columnconfigure(0,weight=1)
            label(card,f"Commande G9-{order['id']:06d}",18,'bold',anchor='w').grid(row=0,column=0,sticky='w',padx=20,pady=(18,5))
            info=label(card,f"{date_label(order['date'])} / {order['city'] or 'Ville non documentée'} / {order['quantity']} article(s)",12,color=Style.muted,anchor='w',justify='left',wraplength=450)
            info.grid(row=1,column=0,sticky='ew',padx=20,pady=(0,15))
            label(card,money(order['total']),22,'bold').grid(row=0,column=1,padx=20,pady=(18,5))
            action=button(card,'Voir le détail',lambda number=order['id']:open_page(f'confirmation:{number}',self),'light',width=155)
            action.grid(row=1,column=1,padx=20,pady=(0,15))
            def arrange(width,frame=card,control=action,detail=info):
                compact=width<700
                control.grid(row=2 if compact else 1,column=0 if compact else 1,sticky='w' if compact else 'e',padx=20,pady=(0,15))
                detail.configure(wraplength=max(220,width-260))
            card._responsive=ResizeObserver(card,arrange)
        total,offset,limit=data['total'],data['offset'],data['limit']
        self.count.configure(text=f'{min(offset+1,total)}-{min(offset+len(data["orders"]),total)} / {total}')
        self.previous.configure(state='normal' if offset else 'disabled')
        self.next.configure(state='normal' if offset+limit<total else 'disabled')

    def load(self,step):
        if current_user_id()!=self.user_id:
            open_page('connexion',self,return_to='mes-commandes');return
        offset=max(0,self.data['offset']+step*self.data['limit'])
        self.message.configure(text='Chargement…')
        def ready(data):
            self.draw(data);self.message.configure(text='');self.scroll._parent_canvas.yview_moveto(0)
        run_task(self,lambda:get_customer_orders(self.user_id,offset=offset,limit=self.data['limit']),ready,
                 lambda error:self.message.configure(text='Les commandes sont indisponibles. Réessayez.'),(self.previous,self.next))


class ReceiptPage(PageFrame):
    def __init__(self,parent,data):
        super().__init__(parent)
        setup_window(self,'Détail de la commande');header(self,'mes-commandes');footer(self)
        scroll=ctk.CTkScrollableFrame(self,fg_color=Style.bg,corner_radius=0)
        scroll.grid(row=1,column=0,sticky='nsew',padx=20,pady=16);scroll.grid_columnconfigure(0,weight=1)
        if data is None:
            label(scroll,'Commande introuvable pour ce compte.',23,'bold',wraplength=480).pack(padx=20,pady=45)
            button(scroll,'Mes commandes',lambda:open_page('mes-commandes',self)).pack(pady=15)
            return
        order=data['order']
        label(scroll,'COMMANDE ENREGISTRÉE / DÉMONSTRATION',11,'bold',color=Style.green).grid(row=0,column=0,sticky='w',padx=12,pady=(12,8))
        label(scroll,f"Commande G9-{order['id']:06d}",31,'bold').grid(row=1,column=0,sticky='w',padx=12)
        label(scroll,date_label(order['date']),13,color=Style.muted).grid(row=2,column=0,sticky='w',padx=12,pady=(6,16))
        notice=label(scroll,'Votre commande de démonstration est enregistrée. Aucun débit ni aucune expédition réelle.',14,color=Style.green,wraplength=880,justify='left',anchor='w')
        notice.grid(row=3,column=0,sticky='ew',padx=12,pady=(0,18))
        items=panel(scroll);items.grid(row=4,column=0,sticky='ew',padx=10,pady=(0,14));items.grid_columnconfigure(0,weight=1)
        label(items,'Votre sélection',22,'bold').grid(row=0,column=0,sticky='w',padx=22,pady=(20,12))
        for index,item in enumerate(data['items']):
            row=ctk.CTkFrame(items,fg_color='#F6F7F5' if index%2==0 else '#FFFFFF',corner_radius=7)
            row.grid(row=index+1,column=0,sticky='ew',padx=18,pady=4);row.grid_columnconfigure(0,weight=1)
            name=label(row,item['name'],15,'bold',anchor='w',justify='left',wraplength=600)
            name.grid(row=0,column=0,sticky='ew',padx=12,pady=(12,4))
            label(row,f"Quantité : {item['quantity']} / Prix unitaire : {money(item['unit_price'])}",12,color=Style.muted,wraplength=400,anchor='w',justify='left').grid(row=1,column=0,sticky='w',padx=12,pady=(0,12))
            label(row,money(item['line_total']),17,'bold').grid(row=0,column=1,rowspan=2,padx=16,pady=12)
            row._responsive=ResizeObserver(row,lambda width,control=name:control.configure(wraplength=max(180,width-230)))
        details=panel(scroll);details.grid(row=5,column=0,sticky='ew',padx=10,pady=(0,14));details.grid_columnconfigure(0,weight=1)
        delivery=data['delivery'];mode={'relais':'Point relais','domicile':'À domicile'}.get(delivery['mode'],'Mode non documenté')
        address=' / '.join(str(value) for value in [order['city'],order['district'],order['residence']] if value)
        mode+=' / '+str(delivery['relay']) if delivery['relay'] else ''
        payment=' / '.join(dict.fromkeys(item['mode'] for item in data['payments'])) or 'Non documenté'
        for index,(title,value) in enumerate([('Livraison',mode),('Adresse enregistrée',address or 'Non documentée'),('Paiement enregistré',payment),
                                              ('Articles',money(data['subtotal'])),('Livraison',money(delivery['fee'])),('Total enregistré',money(order['total']))]):
            row=ctk.CTkFrame(details,fg_color='transparent');row.grid(row=index,column=0,sticky='ew',padx=20,pady=8);row.grid_columnconfigure(1,weight=1)
            label(row,title,13,'bold',width=165,anchor='w').grid(row=0,column=0,sticky='w')
            value_label=label(row,value,17 if index==5 else 13,'bold' if index==5 else 'normal',anchor='w',justify='left',wraplength=700)
            value_label.grid(row=0,column=1,sticky='ew',padx=(12,0))
            row._responsive=ResizeObserver(row,lambda width,control=value_label:control.configure(wraplength=max(180,width-190)))
        button(scroll,'Mes commandes',lambda:open_page('mes-commandes',self),'secondary',width=220).grid(row=6,column=0,sticky='w',padx=10,pady=8)
        button(scroll,'Continuer mes achats',lambda:open_page('catalogue',self),'light',width=220).grid(row=7,column=0,sticky='w',padx=10,pady=(4,20))
        scroll._responsive=ResizeObserver(scroll,lambda width:notice.configure(wraplength=max(260,width-30)))


def main(parent=None,product_id=None,initial_data=None,**options):
    if parent is None:
        from app.runtime import launch
        return launch(f'confirmation:{product_id}' if product_id else 'mes-commandes')
    return ReceiptPage(parent,initial_data) if product_id is not None else OrdersPage(parent,initial_data)
