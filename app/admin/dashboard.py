"""Tableau de bord Dash : filtres, classements, exports, prévisions et segmentation des ventes."""

import pandas as pd
import dash
from dash import dcc, html, dash_table
from dash.dependencies import Input, Output, State
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
from app.database import create_engine
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
import numpy as np
import hmac
import time
import json
from pathlib import Path
from flask import request, Response
from app.config import admin_credentials


def create_app(engine=None):
    from app.credits import project_credits
    from app.analytics import (DashboardSnapshots, french_number, french_date, product_performance,
                               required_history, validation_windows, weekly_reference,
                               segmentation_diagnostics, COLUMN_LABELS, french_export, FRENCH_PLOTLY_LOCALE)
    from dash.dash_table.Format import Format, Group, Scheme
    from dash.exceptions import PreventUpdate
    engine = engine if engine is not None else create_engine()

    main_query = """
    SELECT 
        c.id AS client_id, c.nom AS nom, c.prenoms AS prenoms, c.sexe AS sexe,
        dc.id AS detailcommande_id, dc.date_commande, dc.Ville_de_residence AS ville_residence,
        co.produit_id, p.nom AS produit_nom, p.categorie, p.stock,
        pa.mode_paiement_id,
        COALESCE(mp.type_paiement, CASE WHEN pa.nb_modes > 1
            THEN 'Paiements multiples' ELSE 'Non renseigné' END) AS type_paiement,
        co.nombre_article, co.prix_unitaire AS prix,
        v.lat, v.lng
    FROM 
        Client c
    JOIN 
        Commande co ON c.id = co.client_id
    JOIN 
        DetailCommande dc ON co.commande_id = dc.id
    JOIN 
        Produit p ON co.produit_id = p.id
    LEFT JOIN
        (SELECT commande_id, COUNT(DISTINCT mode_paiement_id) AS nb_modes,
            CASE WHEN COUNT(DISTINCT mode_paiement_id) = 1
                THEN MIN(mode_paiement_id) END AS mode_paiement_id
         FROM Paiement GROUP BY commande_id) pa ON dc.id = pa.commande_id
    LEFT JOIN
        ModePaiement mp ON pa.mode_paiement_id = mp.id
    LEFT JOIN
        (SELECT city, AVG(lat) AS lat, AVG(lng) AS lng FROM Ville GROUP BY city) v
        ON dc.Ville_de_residence = v.city
    """

    snapshots = DashboardSnapshots(engine, main_query)
    snapshots.refresh()

    def sales_for(version=None):
        return snapshots.get(version).sales

    def product_options(products):
        return [{'label': value, 'value': value} for value in sorted(products['categorie'].dropna().unique())]

    def options(data, column):
        return [{'label': value, 'value': value} for value in sorted(data[column].dropna().unique())]

    def chart(figure):
        figure.update_layout(template='plotly_white', separators=', ',
                             font={'family':'Segoe UI, Arial, sans-serif','color':'#14243B'},
                             colorway=['#245BEA','#18735A','#684BD8','#C16B21'],
                             margin={'l':35,'r':25,'t':60,'b':55},
                             title={'font':{'size':17}}, legend={'orientation':'h','y':-0.22})
        figure.update_xaxes(automargin=True)
        figure.update_yaxes(automargin=True)
        return figure

    def graph(figure=None, **kwargs):
        kwargs.setdefault('config',{'locale':'fr','locales':{'fr':FRENCH_PLOTLY_LOCALE},'displaylogo':False,'responsive':True})
        return dcc.Graph(figure=figure,**kwargs)

    def message_figure(message):
        fig = go.Figure().add_annotation(text=message, x=.5,y=.5,xref='paper',yref='paper',showarrow=False)
        fig.update_xaxes(visible=False);fig.update_yaxes(visible=False)
        return chart(fig)

    app = dash.Dash(__name__, suppress_callback_exceptions=True)

    @app.server.before_request
    def require_admin():
        """Protéger également un accès direct au serveur Dash."""
        auth = request.authorization
        username, password = admin_credentials()
        username, password = username.encode("utf-8"), password.encode("utf-8")
        if (auth and auth.type.lower() == "basic"
                and hmac.compare_digest((auth.username or "").encode("utf-8"), username)
                and hmac.compare_digest((auth.password or "").encode("utf-8"), password)):
            getattr(require_admin, 'attempts', {}).pop(getattr(request, 'remote_addr', 'local'), None)
            return None
        attempts = getattr(require_admin, 'attempts', {})
        require_admin.attempts = attempts
        address, now = getattr(request, 'remote_addr', 'local'), time.monotonic()
        failures = [stamp for stamp in attempts.get(address, []) if now - stamp < 60]
        failures.append(now)
        attempts[address] = failures[-5:]
        if len(failures) >= 5:
            return Response('Trop de tentatives. Réessayez dans une minute.', 429, {'Retry-After': '60'})
        return Response("Authentification administrateur requise.", 401,
                        {"WWW-Authenticate": 'Basic realm="Group 9"'})

    @app.server.after_request
    def protect_responses(response):
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Referrer-Policy'] = 'no-referrer'
        return response

    def filter_sales(data, start_date=None, end_date=None, categories=None, villes=None, paiements=None):
        filtered = data.copy()
        if start_date:
            filtered = filtered[filtered["date_commande"] >= pd.Timestamp(start_date).normalize()]
        if end_date:
            stop = pd.Timestamp(end_date).normalize() + pd.Timedelta(days=1)
            filtered = filtered[filtered["date_commande"] < stop]
        for column, values in [("categorie", categories), ("ville_residence", villes),
                               ("type_paiement", paiements)]:
            if values:
                filtered = filtered[filtered[column].isin(values)]
        return filtered

    def complete_priced_orders(data):
        """Écarter une commande entière si une de ses lignes sélectionnées est inconnue."""
        complete = data.groupby('detailcommande_id')['montant'].transform(lambda amounts: amounts.notna().all())
        return data.loc[complete.astype(bool)].copy()

    COLORS = {
        'primary': '#14243B',
        'secondary': '#14243B',
        'accent': '#2C65FF',
        'success': '#18735A',
        'warning': '#14243B',
        'danger': '#684BD8',
        'light': '#ecf0f1',
        'dark': '#2c3e50'
    }

    credits = project_credits()
    def serve_layout():
        initial=snapshots.get()
        df=initial.sales
        today=datetime.now().date()
        first_date=df['date_commande'].min().date() if not df.empty else today
        last_date=df['date_commande'].max().date() if not df.empty else today
        return html.Div([
            html.Header([
                html.Div([html.Span('g9', className='g9-mark'), html.Strong('GROUP9 / INSIGHTS')], className='g9-brand'),
                html.Div('Ventes · Stocks · Clients', className='g9-subtitle'),
                html.Span('Espace administrateur', className='g9-access')
            ], className='g9-header'),
            dcc.Store(id='snapshot-version', data=initial.version),
            html.Div([
                html.Div([html.Strong('Des données à jour pour décider'),
                          html.Div('Actualisez après une commande pour mettre les ventes et les stocks à jour.')]),
                html.Button('Actualiser les données',id='refresh-data',n_clicks=0),
                html.Div('Données actualisées le '+french_date(initial.loaded_at,True)+' UTC',
                         id='refresh-status',role='status',**{'aria-live':'polite'})
            ],className='g9-refresh'),
            dcc.Tabs(id='tabs', value='tab-1', children=[
                dcc.Tab(label='Vue d’ensemble', value='tab-1'),
                dcc.Tab(label='Données et exports', value='tab-2'),
                dcc.Tab(label='Prévisions', value='tab-3'),
                dcc.Tab(label='Segments clients', value='tab-4'),
            ], parent_className='g9-tabs'),
    
            # Contenu principal
            html.Div([
                # Sidebar pour les filtres
                html.Div([
                    html.H3("Filtres", style={'color': COLORS['light'], 'marginBottom': '20px'}),
            
                    # Filtre de date
                    html.Div([
                        html.Label('Période', style={'color': COLORS['light']}),
                        dcc.DatePickerRange(
                            id='date-range',
                            min_date_allowed=first_date,
                            max_date_allowed=last_date,
                            start_date=first_date,
                            end_date=last_date,
                            display_format='DD/MM/YYYY',
                            month_format='MM/YYYY',
                            first_day_of_week=1,
                            start_date_placeholder_text='Début',
                            end_date_placeholder_text='Fin',
                            style={'backgroundColor': COLORS['light']}
                        ),
                    ], style={'marginBottom': '20px'}),
            
                    # Filtre de catégorie
                    html.Div([
                        html.Label('Catégorie', style={'color': COLORS['light']}),
                        dcc.Dropdown(
                            id='categorie-filter',
                            options=product_options(initial.products),
                            multi=True,
                            placeholder="Sélectionner les catégories",
                            style={'backgroundColor': COLORS['light']}
                        ),
                    ], style={'marginBottom': '20px'}),
            
                    # Filtre de ville
                    html.Div([
                        html.Label('Ville', style={'color': COLORS['light']}),
                        dcc.Dropdown(
                            id='ville-filter',
                            options=options(df, 'ville_residence'),
                            multi=True,
                            placeholder="Sélectionner les villes",
                            style={'backgroundColor': COLORS['light']}
                        ),
                    ], style={'marginBottom': '20px'}),
            
                    # Filtre de paiement
                    html.Div([
                        html.Label('Mode de paiement', style={'color': COLORS['light']}),
                        dcc.Dropdown(
                            id='paiement-filter',
                            options=options(df, 'type_paiement'),
                            multi=True,
                            placeholder="Sélectionner les modes de paiement",
                            style={'backgroundColor': COLORS['light']}
                        ),
                    ], style={'marginBottom': '20px'}),
            
                ], className='g9-filters', style={
                    'width': '200px',
                    'position': 'fixed',
                    'top': '84px',
                    'left': '0',
                    'bottom': '0',
                    'backgroundColor': COLORS['secondary'],
                    'padding': '20px',
                    'boxShadow': '2px 0 5px rgba(0,0,0,0.05)',
                    'overflowY': 'auto'
                }),
        
                # Contenu principal
                html.Div(id='main-content', className='g9-main', style={'marginLeft': '250px', 'padding': '20px'})
            ]),
            html.Footer([
                html.Strong(credits['signature']+' - '+credits['title']),
                html.Div('Projet collaboratif - Groupe 9 / ENSEA'),
                html.Details([html.Summary('Équipe & crédits'),
                              html.P(credits['contribution']),
                              html.P(' / '.join(credits['team'])),
                              html.P('Supervision : '+credits['supervisor'])])
            ], className='g9-footer')
        ])

    app.layout=serve_layout

    @app.callback(Output('main-content','children'),
        Input('tabs','value'),Input('date-range','start_date'),Input('date-range','end_date'),
        Input('categorie-filter','value'),Input('ville-filter','value'),Input('paiement-filter','value'),
        Input('snapshot-version','data'))
    def update_content(tab,start_date,end_date,categories,villes,paiements,version=None):
        try:snapshot=snapshots.get(version)
        except ValueError as error:return html.P(str(error),role='status')
        filtered_df=filter_sales(snapshot.sales,start_date,end_date,categories,villes,paiements)
        products=snapshot.products
        catalog=products[products['categorie'].isin(categories)] if categories else products
        if tab=='tab-1':content=create_dashboard_layout(filtered_df,catalog)
        elif tab=='tab-2':content=create_data_view_layout(filtered_df)
        elif tab=='tab-3':content=create_predictions_layout(filtered_df)
        else:content=create_segmentation_layout(filtered_df)
        unknown=int(filtered_df['montant'].isna().sum())
        text='Montants des articles hors livraison, dans la sélection courante.'
        if unknown:text=f'{french_number(unknown)} ligne(s) sans prix historique : montants partiels ; commandes incomplètes exclues du panier moyen et des segments. Prévisions indisponibles.'
        return html.Div([html.P(text),content])

    @app.callback(Output('snapshot-version','data'),Output('refresh-status','children'),
        Output('date-range','min_date_allowed'),Output('date-range','max_date_allowed'),
        Output('date-range','start_date'),Output('date-range','end_date'),
        Output('categorie-filter','options'),Output('ville-filter','options'),Output('paiement-filter','options'),
        Input('refresh-data','n_clicks'),State('snapshot-version','data'),
        State('date-range','start_date'),State('date-range','end_date'),prevent_initial_call=True,
        running=[(Output('refresh-data','disabled'),True,False)])
    def refresh_data(n_clicks,version,start_date,end_date):
        if not n_clicks:raise PreventUpdate
        try:
            previous=snapshots.get(version)
            snapshot=snapshots.refresh()
        except Exception:
            return (dash.no_update,html.Span('Actualisation impossible. Les dernières données affichées sont conservées. Réessayez.',className='g9-error'),*[dash.no_update]*7)
        data=snapshot.sales
        first=data['date_commande'].min().date() if not data.empty else datetime.now().date()
        last=data['date_commande'].max().date() if not data.empty else first
        old_first=previous.sales['date_commande'].min().date() if not previous.sales.empty else None
        old_last=previous.sales['date_commande'].max().date() if not previous.sales.empty else None
        # Prolonger une période complète ; conserver une sélection personnalisée.
        begin=first if not start_date or (old_first is not None and pd.Timestamp(start_date).date()==old_first) else start_date
        end=last if not end_date or (old_last is not None and pd.Timestamp(end_date).date()==old_last) else end_date
        return (snapshot.version,'Données actualisées le '+french_date(snapshot.loaded_at,True)+' UTC',
                first,last,begin,end,product_options(snapshot.products),options(data,'ville_residence'),options(data,'type_paiement'))

    def create_dashboard_layout_original(filtered_df,catalog):
        # Calcul des KPIs
        total_ventes = filtered_df['montant'].sum()
        nb_commandes = filtered_df['detailcommande_id'].nunique()
        documented = complete_priced_orders(filtered_df)
        documented_orders = documented['detailcommande_id'].nunique()
        panier_moyen = documented['montant'].sum() / documented_orders if documented_orders else None
        nb_clients = filtered_df['client_id'].nunique()
    
        return html.Div([
            # KPIs
            html.Div([
                create_kpi_card("Ventes documentées hors livraison", f"{total_ventes:,.0f} FCFA" if filtered_df['montant'].notna().any() else "Indisponible", COLORS['accent']),
                create_kpi_card("Commandes", f"{nb_commandes:,}", COLORS['success']),
                create_kpi_card("Panier moyen documenté", f"{panier_moyen:,.0f} FCFA" if panier_moyen is not None else "Indisponible", COLORS['warning']),
                create_kpi_card("Clients uniques", f"{nb_clients:,}", COLORS['danger'])
            ], style={'display': 'flex', 'justifyContent': 'space-between', 'gap': '12px', 'flexWrap': 'wrap', 'marginBottom': '20px'}),
        
            # Première ligne de graphiques
            html.Div([
                html.Div([
                    graph(
                        figure=chart(create_map_figure(filtered_df)),
                        style={'height': '400px'}
                    )
                ], className='g9-chart-cell', style={'width': '50%', 'display': 'inline-block'}),
            
                html.Div([
                    graph(
                        figure=create_sales_evolution(filtered_df),
                        style={'height': '400px'}
                    )
                ], className='g9-chart-cell', style={'width': '50%', 'display': 'inline-block'})
            ]),
        
            # Deuxième ligne de graphiques
            html.Div([
                html.Div([
                    graph(
                        figure=chart(create_category_pie(filtered_df)),
                        style={'height': '400px'}
                    )
                ], className='g9-chart-cell', style={'width': '50%', 'display': 'inline-block'}),
            
                html.Div([
                    graph(
                        figure=create_payment_distribution(filtered_df),
                        style={'height': '400px'}
                    )
                ], className='g9-chart-cell', style={'width': '50%', 'display': 'inline-block'})
            ]),
        
            # Stock Dashboard
            html.Div([
                html.Div([
                    html.H3("Stocks actuels les plus élevés"),
                    create_stock_table(catalog.sort_values(['stock','id'],ascending=[False,True]).head(5)[['nom','stock','categorie']])
                ], className='g9-chart-cell', style={'width': '48%', 'display': 'inline-block', 'marginRight': '2%'}),
            
                html.Div([
                    html.H3("Stocks actuels les plus faibles"),
                    create_stock_table(catalog[catalog['stock']>=0].sort_values(['stock','id']).head(5)[['nom','stock','categorie']])
                ], className='g9-chart-cell', style={'width': '48%', 'display': 'inline-block'})
            ])
        ])


    def create_map_figure(df):
        df = df.dropna(subset=['montant', 'lat', 'lng'])
        cities = df.groupby('ville_residence', as_index=False).agg(
            montant=('montant', 'sum'), lat=('lat', 'mean'), lng=('lng', 'mean'))
        cities = cities.astype({'montant': float, 'lat': float, 'lng': float})
        path = Path(__file__).resolve().parents[2] / 'assets/data/cote_ivoire.json'
        outline = json.loads(path.read_text(encoding='utf-8'))['geometry']['coordinates'][0]
        longitude, latitude = zip(*outline)
        figure = go.Figure() if cities.empty else px.scatter(cities, x='lng', y='lat', size='montant', size_max=45, render_mode='svg',
                            hover_name='ville_residence', hover_data={'montant': ':,.0f', 'lat': False, 'lng': False},
                            text='ville_residence' if len(cities) <= 8 else None,
                            color_discrete_sequence=['#2C65FF'],
                            labels={'lng': 'Longitude', 'lat': 'Latitude', 'montant': 'Ventes (FCFA)'},
                            title='Localisation des ventes documentées')
        figure.update_traces(textposition='top center', marker_opacity=0.85)
        figure.add_trace(go.Scatter(x=longitude, y=latitude, mode='lines', fill='toself',
                                   fillcolor='#EDF2FA', line={'color': '#B6C7E1', 'width': 1.5},
                                   hoverinfo='skip', showlegend=False))
        figure.data = (figure.data[-1],) + figure.data[:-1]
        figure.update_xaxes(range=[min([*longitude, *cities['lng']])-0.4, max([*longitude, *cities['lng']])+0.4],
                            showgrid=False, zeroline=False)
        figure.update_yaxes(range=[min([*latitude, *cities['lat']])-0.3, max([*latitude, *cities['lat']])+0.3],
                            scaleanchor='x', scaleratio=1, showgrid=False, zeroline=False)
        return figure.update_layout(plot_bgcolor='white', paper_bgcolor='white', showlegend=False,
                                    margin={'r': 15, 't': 50, 'l': 40, 'b': 35},
                                    annotations=[{'text': 'Contour : Natural Earth', 'xref': 'paper', 'yref': 'paper',
                                                  'x': 0, 'y': 0, 'showarrow': False, 'font': {'size': 9, 'color': '#66758B'}}])

    def create_sales_evolution(df):
        daily=(df.assign(date_commande=df['date_commande'].dt.normalize()).groupby('date_commande')['montant'].sum(min_count=1).reset_index())
        daily['date_fr']=daily['date_commande'].map(french_date)
        figure=px.line(daily,x='date_commande',y='montant',custom_data=['date_fr'],
                       color_discrete_sequence=['#245BEA'],
                       labels={'date_commande':'Date','montant':'Ventes hors livraison (FCFA)'},title='Évolution des ventes documentées')
        figure.update_traces(hovertemplate='%{customdata[0]}<br>Ventes : %{y:,.0f} FCFA<extra></extra>')
        figure.update_xaxes(tickformat='%d/%m/%Y',nticks=7)
        figure.update_yaxes(tickformat=',.0f')
        return chart(figure)

    def create_category_pie(df):
        category_sales = df.groupby('categorie')['montant'].sum(min_count=1).dropna()
        return px.pie(
            values=category_sales.values,
            names=category_sales.index,
            color_discrete_sequence=['#245BEA','#18735A','#684BD8','#C16B21','#517894'],
            title='Ventes documentées par catégorie',
            labels={'values':'Ventes (FCFA)','names':'Catégorie'}
        )

    def create_payment_distribution(df):
        data=df.groupby('type_paiement')['montant'].sum(min_count=1).dropna().sort_values().reset_index()
        figure=px.bar(data,x='montant',y='type_paiement',orientation='h',
                      color_discrete_sequence=['#245BEA'],
                      labels={'type_paiement':'Mode de paiement','montant':'Ventes hors livraison (FCFA)'},title='Ventes par mode de paiement')
        figure.update_traces(hovertemplate='%{y}<br>Ventes : %{x:,.0f} FCFA<extra></extra>')
        figure.update_xaxes(tickformat=',.0f');figure.update_yaxes(categoryorder='array',categoryarray=data['type_paiement'].tolist())
        return chart(figure)

    def create_kpi_card(title, value, color):
        return html.Div([
            html.H4(title, style={'color': COLORS['dark'], 'marginBottom': '5px'}),
            html.H2(value.replace(',', ' '), style={'color': color, 'margin': '0', 'fontSize': '25px'})
        ], style={
            'backgroundColor': 'white',
            'padding': '20px',
            'borderRadius': '16px',
            'border': '1px solid #E4E9F1',
            'flex': '1 1 190px',
            'minWidth': '170px',
            'minHeight': '100px',
            'textAlign': 'left'
        })

    def create_stock_table(df):
        return dash_table.DataTable(
            data=df.to_dict('records'),
            columns=[
                {'name': 'Produit', 'id': 'nom'},
                {'name':'Stock','id':'stock','type':'numeric','format':Format(precision=0,scheme=Scheme.fixed,group=Group.yes,group_delimiter=' ',decimal_delimiter=',',nully='Non documenté')},
                {'name': 'Catégorie', 'id': 'categorie'}
            ],
            style_table={'overflowX': 'auto'},
            style_cell={
                'textAlign': 'left',
                'padding': '10px',
                'fontFamily':'Segoe UI, Arial, sans-serif',
                'whiteSpace':'normal','height':'auto','minWidth':'55px','maxWidth':'240px',
            },
            style_cell_conditional=[{'if':{'column_id':'nom'},'width':'60%'},
                                    {'if':{'column_id':'stock'},'width':'15%'},
                                    {'if':{'column_id':'categorie'},'width':'25%'}],
            style_header={
                'backgroundColor': COLORS['light'],
                'fontWeight': 'bold',
            }
        )

    def create_product_performance_charts(filtered_df,catalog):
        import textwrap
        performance=product_performance(filtered_df,catalog)
        def ranking(data,title,color):
            frame=data.copy()
            if frame.empty:return message_figure('Aucun produit commandé dans cette sélection.')
            frame['label']=frame['produit_nom'].map(lambda value:'<br>'.join(textwrap.wrap(str(value),35)))
            frame['display_count']=frame['nombre_commandes'].map(lambda value:french_number(value) if value else '')
            figure=px.bar(frame,x='nombre_commandes',y='produit_id',orientation='h',
                          custom_data=['produit_nom','label'],text='display_count',title=title,
                          labels={'nombre_commandes':'Nombre de commandes distinctes','produit_id':'Produit'})
            figure.update_traces(marker_color=color,textposition='outside',cliponaxis=False,
                hovertemplate='%{customdata[0]}<br>%{x:,.0f} commande(s)<extra></extra>')
            if not frame.empty:
                zeros=frame[frame['nombre_commandes']==0]
                if not zeros.empty:figure.add_trace(go.Scatter(x=zeros['nombre_commandes'],y=zeros['produit_id'],mode='markers+text',
                    text=['0 commande']*len(zeros),textposition='middle right',textfont={'size':11},cliponaxis=False,
                    marker={'size':7,'color':color},customdata=zeros[['produit_nom']],showlegend=False,
                    hovertemplate='%{customdata[0]}<br>0 commande<extra></extra>'))
            figure.update_yaxes(type='category',ticklabelstandoff=10,categoryorder='array',categoryarray=frame['produit_id'].tolist(),
                                 autorange='reversed',tickmode='array',tickvals=frame['produit_id'],ticktext=frame['label'],title=None)
            figure.update_xaxes(range=[0,max(1,frame['nombre_commandes'].max() if not frame.empty else 1)*1.22],dtick=max(1,int(np.ceil(frame['nombre_commandes'].max()/5))) if not frame.empty else 1,tickformat=',.0f')
            figure.update_layout(height=max(370,len(frame)*88+100),showlegend=False)
            return chart(figure)
        top=performance[performance['nombre_commandes']>0].sort_values(['nombre_commandes','produit_id'],ascending=[False,True]).head(10)
        bottom=performance.head(10)
        return html.Div([
            html.P('Nombre de commandes distinctes dans la sélection. Le classement inclut le catalogue actuel des catégories choisies, même sans vente.',className='g9-explainer'),
            html.Div(graph(ranking(top,'Les plus commandés','#245BEA')),className='g9-chart-cell',style={'width':'50%','display':'inline-block'}),
            html.Div(graph(ranking(bottom,'Les moins commandés, zéro inclus','#18735A')),className='g9-chart-cell',style={'width':'50%','display':'inline-block'})])

    def create_dashboard_layout(filtered_df,catalog):
        # Garder le layout existant et ajouter les nouveaux graphiques
        existing_layout = create_dashboard_layout_original(filtered_df,catalog)
        product_performance = create_product_performance_charts(filtered_df,catalog)
    
        return html.Div([
            existing_layout,
            html.H3("Produits : succès et références sans commande"),
            product_performance
        ])

    def create_download_buttons():
        return html.Div([
            html.Button("Exporter en CSV", id='btn-csv'),
            dcc.Download(id="download-dataframe-csv"),
        ], style={'margin': '10px 0'})

    @app.callback(Output('download-dataframe-csv','data'),Input('btn-csv','n_clicks'),
        State('date-range','start_date'),State('date-range','end_date'),State('categorie-filter','value'),
        State('ville-filter','value'),State('paiement-filter','value'),State('snapshot-version','data'),prevent_initial_call=True)
    def export_csv(n_clicks,start_date,end_date,categories,villes,paiements,version=None):
        if not n_clicks:raise PreventUpdate
        try:filtered=filter_sales(sales_for(version),start_date,end_date,categories,villes,paiements)
        except ValueError:raise PreventUpdate
        content='\ufeff'+french_export(filtered).to_csv(index=False,sep=';',decimal=',')
        return {'content':content,'filename':'ventes_selection.csv','type':'text/csv;charset=utf-8','base64':False}

    def create_data_view_layout(filtered_df):
        data=filtered_df.copy()
        data['prix_historique_connu']=data['prix_historique_connu'].map({True:'Oui',False:'Non'})
        data['date_commande']=filtered_df['date_commande'].map(lambda value:french_date(value,True))
        columns=[]
        for name in data.columns:
            definition={'name':COLUMN_LABELS.get(name,name),'id':name}
            if pd.api.types.is_numeric_dtype(data[name]):
                decimals=2 if name in ('prix','montant') else 5 if name in ('lat','lng') else 0
                definition.update(type='numeric',format=Format(precision=decimals,scheme=Scheme.fixed,group=Group.yes,
                    decimal_delimiter=',',group_delimiter=' ',nully='Non documenté'))
            columns.append(definition)
        return html.Div([html.H1('Données détaillées'),create_download_buttons(),
            html.P('Export français : séparateur point-virgule, virgule décimale, dates JJ/MM/AAAA. Les valeurs historiques inconnues restent vides.',className='g9-explainer'),
            dash_table.DataTable(id='data-table',columns=columns,data=data.where(pd.notna(data),None).to_dict('records'),
            page_size=10,filter_action='native',filter_options={'placeholder_text':'Filtrer…','case':'insensitive'},sort_action='custom',sort_mode='single',
                sort_by=[],style_table={'overflowX':'auto'},style_cell={'fontFamily':'Segoe UI, Arial','padding':'12px','textAlign':'left','maxWidth':'280px','whiteSpace':'normal'},
                style_header={'backgroundColor':'#EAF0FF','fontWeight':'bold'},
                style_data_conditional=[{'if':{'row_index':'odd'},'backgroundColor':'#F7F9FC'}])])

    @app.callback(Output('data-table','data'),Input('data-table','sort_by'),
        State('date-range','start_date'),State('date-range','end_date'),State('categorie-filter','value'),
        State('ville-filter','value'),State('paiement-filter','value'),State('snapshot-version','data'))
    def sort_detail(sort_by,start_date,end_date,categories,villes,paiements,version=None):
        try:data=filter_sales(sales_for(version),start_date,end_date,categories,villes,paiements)
        except ValueError:raise PreventUpdate
        if sort_by:
            name=sort_by[0]['column_id']
            if name in data.columns:data=data.sort_values(name,ascending=sort_by[0]['direction']=='asc',kind='stable',na_position='last')
        data=data.copy()
        data['date_commande']=data['date_commande'].map(lambda value:french_date(value,True))
        data['prix_historique_connu']=data['prix_historique_connu'].map({True:'Oui',False:'Non'})
        return data.where(pd.notna(data),None).to_dict('records')

    def create_predictions_layout(df):
        days=(df['date_commande'].max().normalize()-df['date_commande'].min().normalize()).days+1 if not df.empty else 0
        available=[h for h in (7,30,90) if days>=required_history(h)]
        return html.Div([html.H1('Prévisions : quel horizon peut-on évaluer ?'),
            html.P('Trois périodes chronologiques de même durée que la prévision. Comparaison au dernier jour connu et à une répétition de la dernière semaine.',className='g9-explainer'),
            html.Div([html.Label('Horizon de prévision'),dcc.Dropdown(id='prediction-horizon',
                options=[{'label':f'{h} jours / minimum {required_history(h)} jours observés','value':h,'disabled':days<required_history(h)} for h in (7,30,90)],
                value=30 if 30 in available else 7,clearable=False),
                html.P(f'{french_number(days)} jours dans la sélection. Les horizons non évaluables sont désactivés.'),
                html.Button('Évaluer et prévoir',id='generate-predictions',n_clicks=0,disabled=not available),
                dcc.Loading([graph(id='prediction-graph',figure=message_figure('Lancez l’évaluation pour afficher la prévision.')),
                             html.Div(id='prediction-evaluation')],type='circle')],className='g9-analysis-panel')])

    def create_segmentation_layout(df):
        return html.Div([html.H1('Segments clients : des profils à vérifier'),
            html.P('Les groupes sont construits sur six indicateurs standardisés. Le graphique en deux dimensions n’en montre qu’une partie.',className='g9-explainer'),
            html.Div([html.Label('Nombre de segments'),dcc.Dropdown(id='n-clusters',
                options=[{'label':f'{i} segments','value':i} for i in range(2,11)],value=4,clearable=False),
                html.Button('Évaluer les segments',id='generate-segments',n_clicks=0),
                dcc.Loading([html.Div(id='segment-descriptions'),graph(id='segmentation-graph',figure=message_figure('Lancez l’évaluation des segments.'))],type='circle')],className='g9-analysis-panel')])

    def prepare_features_for_prediction(df):
        """Prépare les features avancées pour la prédiction"""
        daily_sales = (df.assign(date_commande=df['date_commande'].dt.normalize())
                       .groupby('date_commande')['montant'].sum().reset_index())
        daily_sales = daily_sales.set_index('date_commande').asfreq('D').reset_index()
        daily_sales['montant'] = daily_sales['montant'].fillna(0)
    
        # Features temporelles avancées
        daily_sales['day_of_week'] = daily_sales['date_commande'].dt.dayofweek
        daily_sales['month'] = daily_sales['date_commande'].dt.month
        daily_sales['day_of_month'] = daily_sales['date_commande'].dt.day
        daily_sales['is_weekend'] = daily_sales['day_of_week'].isin([5, 6]).astype(int)
    
        # Moyennes mobiles
        daily_sales['rolling_mean_7d'] = daily_sales['montant'].shift(1).rolling(window=7, min_periods=1).mean().fillna(0)
        daily_sales['rolling_mean_30d'] = daily_sales['montant'].shift(1).rolling(window=30, min_periods=1).mean().fillna(0)
    
        # Lag features
        for lag in [1, 7, 14, 30]:
            daily_sales[f'lag_{lag}d'] = daily_sales['montant'].shift(lag).fillna(0)
    
        return daily_sales

    def forecast_values(model, feature_columns, daily_sales, horizon):
        """Prévision récursive : les valeurs futures ne sont jamais observées."""
        last_date = daily_sales['date_commande'].max()
        future = pd.DataFrame({'date_commande': pd.date_range(last_date + timedelta(days=1), periods=horizon)})
        future['day_of_week'] = future['date_commande'].dt.dayofweek
        future['month'] = future['date_commande'].dt.month
        future['day_of_month'] = future['date_commande'].dt.day
        future['is_weekend'] = future['day_of_week'].isin([5, 6]).astype(int)
        history = daily_sales['montant'].tail(30).to_numpy(dtype=float)
        predictions = []
        for index in range(horizon):
            row = future.iloc[index:index + 1].copy()
            row['rolling_mean_7d'] = np.mean(history[-7:])
            row['rolling_mean_30d'] = np.mean(history)
            for lag in (1, 7, 14, 30):
                row[f'lag_{lag}d'] = history[-lag]
            prediction = float(model.predict(row[feature_columns])[0])
            if not np.isfinite(prediction):
                raise ValueError("Le modèle a produit une prévision invalide.")
            prediction = max(0.0, prediction)
            predictions.append(prediction)
            history = np.append(history[1:], prediction)
        future['predicted_sales'] = predictions
        return future

    def train_prediction_model(daily_sales,horizon=7):
        from xgboost import XGBRegressor
        windows=validation_windows(len(daily_sales),horizon)
        columns=['day_of_week','month','day_of_month','is_weekend','rolling_mean_7d','rolling_mean_30d','lag_1d','lag_7d','lag_14d','lag_30d']
        parameters=dict(n_estimators=100,learning_rate=.1,max_depth=5,min_child_weight=1,
                        subsample=.8,colsample_bytree=.8,random_state=42,n_jobs=1)
        folds=[]
        for start,stop in windows:
            history=daily_sales.iloc[:start]
            model=XGBRegressor(**parameters)
            model.fit(history[columns].iloc[30:],history['montant'].iloc[30:])
            predictions=forecast_values(model,columns,history,stop-start)['predicted_sales'].to_numpy(dtype=float)
            actual=daily_sales['montant'].iloc[start:stop].to_numpy(dtype=float)
            last=np.repeat(history['montant'].iloc[-1],stop-start)
            weekly=weekly_reference(history['montant'],stop-start)
            folds.append(dict(start=daily_sales['date_commande'].iloc[start].date().isoformat(),
                end=daily_sales['date_commande'].iloc[stop-1].date().isoformat(),days=stop-start,train_days=len(history),
                mae=float(np.mean(np.abs(actual-predictions))),rmse=float(np.sqrt(np.mean((actual-predictions)**2))),
                naive_mae=float(np.mean(np.abs(actual-last))),weekly_mae=float(np.mean(np.abs(actual-weekly)))))
        metrics={key:float(np.mean([row[key] for row in folds])) for key in ('mae','rmse','naive_mae','weekly_mae')}
        metrics.update(folds=folds,test_days=3*horizon,test_start=folds[0]['start'],test_end=folds[-1]['end'],
                       wins=sum(row['mae']<row['weekly_mae'] for row in folds),horizon=horizon)
        model=XGBRegressor(**parameters)
        model.fit(daily_sales[columns].iloc[30:],daily_sales['montant'].iloc[30:])
        return model,columns,metrics

    @app.callback(Output('prediction-graph','figure'),Output('prediction-evaluation','children'),
        Input('generate-predictions','n_clicks'),Input('prediction-horizon','value'),
        State('date-range','start_date'),State('date-range','end_date'),State('categorie-filter','value'),
        State('ville-filter','value'),State('paiement-filter','value'),State('snapshot-version','data'))
    def update_predictions(n_clicks,horizon,start_date,end_date,categories,villes,paiements,version=None):
        if not n_clicks:return message_figure('Lancez l’évaluation pour afficher la prévision.'),''
        try:
            minimum=required_history(horizon)
            selected=filter_sales(sales_for(version),start_date,end_date,categories,villes,paiements)
            if selected['montant'].isna().any():raise ValueError('Prévisions indisponibles : des prix historiques sont inconnus dans cette sélection.')
            if selected.empty:raise ValueError('Aucune vente dans cette sélection.')
            daily=prepare_features_for_prediction(selected)
            if len(daily)<minimum:raise ValueError(f'Au moins {minimum} jours sont nécessaires pour cet horizon et trois périodes de validation.')
            model,columns,metrics=train_prediction_model(daily,horizon)
            future=forecast_values(model,columns,daily,horizon)
        except (ValueError,ImportError) as error:return message_figure(str(error)),''
        figure=go.Figure()
        for dates,values,title,color,dash_style in [
            (daily['date_commande'].tail(90),daily['montant'].tail(90),'Ventes observées','#14243B','solid'),
            (future['date_commande'],future['predicted_sales'],'Modèle de prévision','#245BEA','dash'),
            (future['date_commande'],weekly_reference(daily['montant'],horizon),'Référence : dernière semaine','#18735A','dot')]:
            figure.add_trace(go.Scatter(x=dates,y=values,name=title,line={'color':color,'dash':dash_style},
                customdata=[french_date(value) for value in dates],hovertemplate='%{customdata}<br>%{y:,.0f} FCFA<extra>%{fullData.name}</extra>'))
        figure.update_layout(title=f'Prévision à {horizon} jours / comparaison à la référence',xaxis_title='Date',yaxis_title='Ventes hors livraison (FCFA)',hovermode='x unified')
        figure.update_xaxes(tickformat='%d/%m/%Y',nticks=7);figure.update_yaxes(tickformat=',.0f')
        rows=[{'Période':f'{french_date(row["start"])} au {french_date(row["end"])}',
            'Jours d’apprentissage':row['train_days'],'Erreur modèle (FCFA)':french_number(row['mae']),
            'Erreur dernière semaine (FCFA)':french_number(row['weekly_mae']),
            'Erreur dernier jour (FCFA)':french_number(row['naive_mae'])} for row in metrics['folds']]
        conclusion=(f'Le modèle améliore la référence hebdomadaire sur {metrics["wins"]}/3 périodes. '
            +('Son erreur moyenne est inférieure à cette référence.' if metrics['mae']<metrics['weekly_mae'] else 'La référence hebdomadaire reste au moins aussi bonne en moyenne.'))
        report=html.Div([html.H3('Évaluation avant interprétation'),html.P(conclusion),
            html.P(f'Erreur absolue moyenne du modèle : {french_number(metrics["mae"])} FCFA par jour. '
                   f'Référence hebdomadaire : {french_number(metrics["weekly_mae"])} FCFA par jour.'),
            dash_table.DataTable(data=rows,columns=[{'name':name,'id':name} for name in rows[0]],style_table={'overflowX':'auto'},style_cell={'padding':'10px','textAlign':'left','whiteSpace':'normal'},style_header={'backgroundColor':'#EAF0FF','fontWeight':'bold'}),
            html.P('Trois fenêtres sans chevauchement, apprentissage croissant et prévision récursive sans observation des ventes futures. Modèle final réentraîné sur toute la sélection.',className='g9-explainer'),
            html.P('Les jours sans commande entre les premières et dernières ventes sont comptés à zéro. La prévision dépend de cette hypothèse et ne fournit pas d’intervalle de confiance. Les horizons longs restent exploratoires.',className='g9-explainer')],className='g9-diagnostics')
        return chart(figure),report

    def prepare_customer_features(df, reference_date=None):
        """Une transaction correspond à une commande, quel que soit son nombre de lignes."""
        data = complete_priced_orders(df)
        orders = data.groupby(['client_id', 'detailcommande_id'], as_index=False).agg(
            order_amount=('montant', 'sum'), order_items=('nombre_article', 'sum'),
            order_date=('date_commande', 'max'))
        customers = orders.groupby('client_id').agg(
            total_amount=('order_amount', 'sum'), avg_amount=('order_amount', 'mean'),
            std_amount=('order_amount', 'std'), nb_transactions=('detailcommande_id', 'count'),
            total_items=('order_items', 'sum'), avg_items_per_order=('order_items', 'mean'),
            first_purchase=('order_date', 'min'), last_purchase=('order_date', 'max'))
        customers['std_amount'] = customers['std_amount'].fillna(0)
        reference = pd.Timestamp(reference_date if reference_date else df['date_commande'].max()).normalize()
        customers['recency'] = (reference - customers['last_purchase'].dt.normalize()).dt.days.clip(lower=0)
        observed_days = (reference - customers['first_purchase'].dt.normalize()).dt.days.clip(lower=0) + 1
        customers['purchase_frequency'] = customers['nb_transactions'] / observed_days
        customers['avg_amount_per_item'] = (customers['total_amount'] / customers['total_items'].replace(0, np.nan)).fillna(0)
        return customers.drop(columns=['first_purchase', 'last_purchase'])

    def perform_customer_segmentation(customer_metrics, n_clusters):
        """Réalise une segmentation plus sophistiquée des clients"""
        # Sélection des features pour la segmentation
        features_for_clustering = [
            'total_amount', 'avg_amount', 'nb_transactions',
            'recency', 'purchase_frequency', 'avg_items_per_order'
        ]
    
        if isinstance(n_clusters, bool) or not isinstance(n_clusters, int) or not 2 <= n_clusters <= 10:
            raise ValueError("Choisissez entre 2 et 10 segments.")
        if len(customer_metrics) < n_clusters:
            raise ValueError("Le nombre de clients aux commandes documentées doit être au moins égal au nombre de segments.")
        values = customer_metrics[features_for_clustering].to_numpy(dtype=float)
        if not np.isfinite(values).all():
            raise ValueError("Les indicateurs clients contiennent des valeurs invalides.")
        # Standardisation
        scaler = StandardScaler()
        X = scaler.fit_transform(values)
        if len(np.unique(X, axis=0)) < n_clusters:
            raise ValueError("Le nombre de profils clients distincts est insuffisant. Réduisez le nombre de segments.")
    
        # Application de K-means
        kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
        labels = kmeans.fit_predict(X)
        if len(np.unique(labels)) != n_clusters:
            raise ValueError("Certains segments sont vides. Réduisez le nombre de segments.")
        customer_metrics = customer_metrics.copy()
        customer_metrics['Segment'] = labels
    
        # Calcul des centres des clusters normalisés
        cluster_centers = pd.DataFrame(
            scaler.inverse_transform(kmeans.cluster_centers_),
            columns=features_for_clustering
        )
    
        return customer_metrics, cluster_centers

    @app.callback(Output('segmentation-graph','figure'),Output('segment-descriptions','children'),
        Input('generate-segments','n_clicks'),Input('n-clusters','value'),
        State('date-range','start_date'),State('date-range','end_date'),State('categorie-filter','value'),
        State('ville-filter','value'),State('paiement-filter','value'),State('snapshot-version','data'))
    def update_segmentation(n_clicks,n_clusters,start_date,end_date,categories,villes,paiements,version=None):
        if not n_clicks:return message_figure('Lancez l’évaluation des segments.'),''
        try:
            selected=filter_sales(sales_for(version),start_date,end_date,categories,villes,paiements)
            if selected.empty:raise ValueError('Aucun client dans cette sélection.')
            customers=prepare_customer_features(selected,end_date)
            segmented,centers=perform_customer_segmentation(customers,n_clusters)
            diagnostics=segmentation_diagnostics(customers,segmented['Segment'],n_clusters)
        except ValueError as error:return message_figure(str(error)),''
        display=segmented.reset_index().assign(Segment=lambda data:(data['Segment']+1).astype(str))
        figure=px.scatter(display,x='total_amount',y='nb_transactions',color='Segment',custom_data=['client_id'],
            category_orders={'Segment':[str(value) for value in range(1,n_clusters+1)]},
            color_discrete_sequence=['#245BEA','#18735A','#684BD8','#C16B21','#517894','#963954','#5A7138','#2C8A88','#895F26','#794E87'],
            title='Vue partielle des profils : montant et nombre de commandes',
            labels={'total_amount':'Achats documentés (FCFA)','nb_transactions':'Nombre de commandes'})
        figure.update_traces(hovertemplate='Client %{customdata[0]}<br>Achats : %{x:,.0f} FCFA<br>%{y:,.0f} commande(s)<extra>%{fullData.name}</extra>')
        figure.update_xaxes(tickformat=',.0f');figure.update_yaxes(tickformat=',.0f',dtick=1)
        cards=[html.Div([html.Strong(title),html.Div(french_number(value,3) if value is not None else 'Non évaluable')],className='g9-metric')
               for title,value in [('Séparation / silhouette',diagnostics['silhouette']),('Stabilité / graines, ARI médian',diagnostics['seed_median']),
                                   ('Stabilité / sous-échantillons, ARI médian',diagnostics['sample_median']),('Sous-échantillons, ARI minimum',diagnostics['sample_min'])]]
        summary=html.Div([html.H3('Évaluation avant description'),html.Strong(diagnostics['status']),html.Div(cards,className='g9-metrics'),
            html.P(f'Silhouette sur {french_number(diagnostics["silhouette_clients"])} clients dans les six dimensions. '
                f'{diagnostics["successful_resamples"]}/5 sous-échantillons exploitables à 80 %, avec standardisation réestimée. '
                'Cinq initialisations supplémentaires ; comparaison des partitions par indice de Rand ajusté (ARI).'),
            html.P('Silhouette : de -1 à 1, plus élevée pour des groupes mieux séparés. ARI : 1 signifie des partitions identiques, sans dépendre du numéro des segments. '
                'Les seuils de prudence sont des règles du projet, pas une validation universelle. La stabilité temporelle n’est pas mesurée.',className='g9-explainer')],className='g9-diagnostics')
        profiles=[]
        for segment in sorted(segmented['Segment'].unique()):
            part=segmented[segmented['Segment']==segment]
            profiles.append(html.Div([html.H4(f'Segment {segment+1} / {french_number(len(part))} client{"s" if len(part)>1 else ""}'),
                html.P(f'Achats moyens : {french_number(part["total_amount"].mean())} FCFA'),
                html.P(f'Panier moyen : {french_number(part["avg_amount"].mean())} FCFA'),
                html.P(f'Fréquence : {french_number(part["purchase_frequency"].mean(),3)} commande(s)/jour'),
                html.P(f'Récence moyenne : {french_number(part["recency"].mean(),1)} jours')],className='g9-profile'))
        return chart(figure),html.Div([summary,html.H3('Profils descriptifs / à confirmer'),html.Div(profiles,className='g9-profiles')])

    app.index_string = '''
    <!DOCTYPE html>
    <html lang="fr">
        <head>
            {%metas%}
            <title>Group9 Insights · Tableau de bord</title>
            {%favicon%}
            {%css%}
            <style>
                body {
                    font-family: "Segoe UI", Arial, sans-serif;
                    background-color: #F4F6FA;
                    color: #14243B;
                    margin: 0;
                }
                .g9-header {height:84px;display:flex;align-items:center;gap:32px;padding:0 30px;background:#14243B;color:white;box-sizing:border-box;}
                .g9-brand {display:flex;align-items:center;gap:13px;letter-spacing:1px;font-size:16px;}
                .g9-mark {display:grid;place-items:center;background:#2C65FF;width:43px;height:41px;border-radius:10px;font-size:24px;font-weight:750;letter-spacing:-1px;}
                .g9-subtitle {color:#C9D8EB;font-size:13px;}
                .g9-access {margin-left:auto;background:#243C5A;padding:10px 15px;border-radius:24px;font-size:12px;}
                .g9-refresh {margin:20px 28px 10px 270px;padding:18px 22px;background:white;border:1px solid #E4E9F1;border-radius:16px;display:flex;align-items:center;gap:18px;flex-wrap:wrap;font-size:13px;line-height:1.6}
                .g9-refresh > div:first-child {flex:1;min-width:210px}
                #refresh-status {width:100%;color:#52647B;font-size:12px}
                .g9-error {color:#A53242}
                .g9-explainer {color:#52647B;font-size:13px;line-height:1.7}
                .g9-analysis-panel,.g9-diagnostics {background:white;padding:22px;border:1px solid #E4E9F1;border-radius:16px;margin:18px 0;line-height:1.6}
                .g9-analysis-panel button {margin:16px 0}
                .g9-metrics,.g9-profiles {display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:14px;margin:18px 0}
                .g9-metric,.g9-profile {padding:18px;background:#F3F6FC;border-radius:12px}
                .g9-metric {font-size:12px}.g9-metric > div{font-size:25px;font-weight:700;color:#245BEA;margin-top:10px}
                .g9-chart-cell {vertical-align:top}
                .g9-tabs {margin:22px 24px 0 270px;}
                .g9-tabs .tab {font-size:13px!important;font-weight:600!important;border:0!important;background:white!important;color:#66758B!important;padding:16px 12px!important;}
                .g9-tabs .tab--selected {background:#2C65FF!important;color:white!important;border-radius:10px!important;}
                h1 {font-size:28px;letter-spacing:-.6px;} h3 {font-size:18px;}
                #main-content > div > p {background:#EAF0FF;padding:14px 18px;border-radius:12px;color:#365276;font-size:13px;line-height:1.55;}
                .js-plotly-plot {border-radius:16px;overflow:hidden;border:1px solid #E4E9F1;margin:8px;}
                button {cursor:pointer;border:0;border-radius:9px;padding:12px 18px;background:#2C65FF;color:white;font-family:inherit;font-weight:600;}
                .DateInput {width:85px!important;} .DateInput_input {font-size:12px!important;padding:10px 6px!important;}
                .DateRangePickerInput {border-radius:9px!important;overflow:hidden;}
                .dash-datepicker-input {width:74px!important;font-family:inherit!important;font-size:12px!important;}
                .g9-footer {margin:16px 28px 28px 270px;color:#596B72;font-size:12px;line-height:1.8;}
                .g9-footer summary {cursor:pointer;color:#245BEA;font-weight:600;}
                @media(max-width:950px){
                  .g9-filters{position:static!important;width:auto!important;margin:16px;padding:16px!important;display:grid;grid-template-columns:1fr 1fr;gap:14px}
                  .g9-filters h3{grid-column:1/-1;margin:0!important}
                  .g9-main{margin-left:0!important;padding:8px 12px!important}
                  .g9-tabs{margin:14px 16px 0!important}.g9-refresh{margin:16px}
                  .g9-footer{margin:16px 24px}
                  .g9-chart-cell{width:100%!important;margin-right:0!important}
                }
                @media(max-width:570px){.g9-filters{grid-template-columns:1fr}.g9-header{gap:10px}.g9-access{display:none}}
                @media(max-width:950px){.g9-subtitle{display:none}.g9-header{padding:0 18px}.g9-tabs{margin-left:250px}.g9-access{font-size:10px}}
            </style>
        </head>
        <body>
            {%app_entry%}
            <footer>
                {%config%}
                {%scripts%}
                {%renderer%}
            </footer>
        </body>
    </html>
    '''

    app.snapshots = snapshots
    return app


def main(product_id=None, return_to="accueil"):
    create_app().run(debug=False, host="127.0.0.1")

