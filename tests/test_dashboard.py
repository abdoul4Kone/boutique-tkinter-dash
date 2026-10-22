"""Actualisation atomique, produits sans vente, formats et diagnostics réels."""
from contextlib import AbstractContextManager
import io
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from dash import no_update
import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler

from app.analytics import (DashboardSnapshots, Snapshot, french_number, french_date,
                           product_performance, required_history, validation_windows,
                           weekly_reference, segmentation_diagnostics, CLUSTER_FEATURES, french_export)
from app.admin.dashboard import create_app


def records(days=84):
    return pd.DataFrame([dict(client_id=i%12+1,nom='Client',prenoms='Démo',sexe='Masculin',
        detailcommande_id=i+1,date_commande=pd.Timestamp('2024-01-01')+pd.Timedelta(days=i),
        ville_residence='Abidjan',produit_id=1,produit_nom='Article vendu',categorie='Tech',
        stock=8,mode_paiement_id=2,type_paiement='Wave',nombre_article=2,prix=19.49,lat=5.3,lng=-4.) for i in range(days)])


def catalogue():
    return pd.DataFrame([dict(id=1,nom='Article vendu',stock=8,categorie='Tech'),
        dict(id=2,nom='Article sans vente',stock=12,categorie='Tech'),
        dict(id=3,nom='Autre catégorie sans vente',stock=0,categorie='Mode')])


class Connection(AbstractContextManager):
    def __init__(self):self.isolation=[];self.transactions=0
    def execution_options(self,**kwargs):self.isolation.append(kwargs);return self
    def begin(self):self.transactions+=1;return self
    def __exit__(self,*args):pass


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.connection=Connection();self.engine=Mock()
        self.engine.connect.return_value=self.connection
        self.raw,self.products=records(),catalogue()
        self.fail=False;self.connections=[]
        def read(query,connection):
            self.connections.append(connection)
            if query=='ventes':return self.raw.copy()
            if self.fail:raise OSError('Base de test indisponible')
            return self.products.copy()
        self.patch=patch('app.analytics.pd.read_sql',side_effect=read)
        self.patch.start();self.addCleanup(self.patch.stop)
        self.store=DashboardSnapshots(self.engine,'ventes',keep=2)

    def test_refresh_reads_sales_and_catalogue_in_one_transaction(self):
        snapshot=self.store.refresh()
        self.assertEqual(self.connections,[self.connection,self.connection])
        self.assertEqual(self.connection.isolation,[{'isolation_level':'REPEATABLE READ'}])
        self.assertEqual(self.connection.transactions,1)
        self.assertAlmostEqual(snapshot.sales['montant'].iloc[0],38.98)
        self.assertIsNotNone(snapshot.loaded_at.tzinfo)

    def test_second_refresh_publishes_new_order_and_new_stock_together(self):
        first=self.store.refresh()
        self.raw=pd.concat([self.raw,self.raw.tail(1).assign(detailcommande_id=999)],ignore_index=True)
        self.products.loc[0,'stock']=6
        second=self.store.refresh()
        self.assertNotEqual(first.version,second.version)
        self.assertEqual(second.sales['detailcommande_id'].nunique(),85)
        self.assertEqual(second.products.iloc[0]['stock'],6)
        self.assertEqual(self.store.get(first.version).products.iloc[0]['stock'],8)

    def test_failed_catalogue_read_never_publishes_partial_sales(self):
        first=self.store.refresh()
        self.raw=self.raw.tail(1)
        self.fail=True
        with self.assertRaises(OSError):self.store.refresh()
        self.assertIs(self.store.get(),first)
        self.assertEqual(len(self.store.versions),1)

    def test_old_versions_are_explicitly_expired(self):
        old=self.store.refresh()
        self.store.refresh();latest=self.store.refresh()
        self.assertIs(self.store.get(),latest)
        with self.assertRaisesRegex(ValueError,'expiré'):self.store.get(old.version)

    def test_empty_database_and_unknown_prices_remain_distinct(self):
        self.raw=self.raw.iloc[:0]
        self.assertTrue(self.store.refresh().sales.empty)
        self.raw=records(1).assign(prix=None)
        snapshot=self.store.refresh()
        self.assertTrue(pd.isna(snapshot.sales['montant'].iloc[0]))
        self.assertFalse(snapshot.sales['prix_historique_connu'].iloc[0])


class ProductRankingTests(unittest.TestCase):
    def test_zero_sales_are_included_without_merging_duplicate_product_names(self):
        products=catalogue();products.loc[1,'nom']='Article vendu'
        data=records(2)
        # Deux lignes d'une même commande comptent pour une seule commande.
        data=pd.concat([data,data.iloc[:1]],ignore_index=True)
        result=product_performance(data,products).set_index('produit_id')
        self.assertEqual(result['nombre_commandes'].to_dict(),{2:0,3:0,1:2})

    def test_category_filter_constrains_unsold_catalogue(self):
        result=product_performance(records(2).iloc[:0],catalogue(),['Tech'])
        self.assertEqual(result['produit_id'].tolist(),[1,2])
        self.assertEqual(result['nombre_commandes'].tolist(),[0,0])

    def test_no_sales_in_a_city_still_lists_the_catalogue(self):
        data=records(2);selected=data[data['ville_residence']=='Bouaké']
        result=product_performance(selected,catalogue())
        self.assertEqual(len(result),3)
        self.assertFalse(result['nombre_commandes'].any())


class HorizonTests(unittest.TestCase):
    def test_long_horizons_require_three_complete_windows_and_training_history(self):
        self.assertEqual([required_history(h) for h in (7,30,90)],[66,150,450])
        for h in (7,30,90):
            n=required_history(h)
            windows=validation_windows(n,h)
            self.assertEqual(len(windows),3)
            self.assertEqual([b-a for a,b in windows],[h]*3)
            self.assertEqual(windows[-1][1],n)
            self.assertEqual(windows[0][1],windows[1][0])
            self.assertGreaterEqual(windows[0][0],max(45,2*h))
            with self.assertRaises(ValueError):validation_windows(n-1,h)

    def test_invalid_horizons_are_refused(self):
        for h in (True,7.,None,14,'30',[]):
            with self.assertRaises(ValueError):required_history(h)

    def test_weekly_reference_never_uses_unobserved_future_sales(self):
        observed=np.arange(20)
        self.assertEqual(weekly_reference(observed,10).tolist(),list(range(13,20))+[13,14,15])


class SeparationTests(unittest.TestCase):
    def groups(self,n=80):
        rng=np.random.default_rng(3)
        values=np.r_[rng.normal(10,.3,(n//2,6)),rng.normal(100,.3,(n//2,6))]
        return pd.DataFrame(values,columns=CLUSTER_FEATURES)

    def test_separated_groups_have_high_silhouette_and_resampling_stability(self):
        customers=self.groups();labels=np.repeat([0,1],40)
        result=segmentation_diagnostics(customers,labels,2)
        self.assertGreater(result['silhouette'],.9)
        self.assertEqual(result['successful_resamples'],5)
        self.assertEqual(result['sample_min'],1.)
        self.assertEqual(result['sizes'],[40,40])
        self.assertIn('favorables',result['status'])

    def test_segment_numbers_do_not_change_the_assessment(self):
        customers=self.groups();labels=np.repeat([0,1],40)
        first=segmentation_diagnostics(customers,labels,2)
        second=segmentation_diagnostics(customers,1-labels,2)
        self.assertAlmostEqual(first['silhouette'],second['silhouette'])
        self.assertEqual(first['sample_median'],second['sample_median'])

    def test_small_samples_are_not_declared_stable(self):
        customers=self.groups(4)
        result=segmentation_diagnostics(customers,[0,0,1,1],2)
        self.assertIsNone(result['sample_median'])
        self.assertEqual(result['status'],'Évaluation insuffisante')

    def test_one_client_per_cluster_has_no_silhouette(self):
        customers=self.groups(4)
        result=segmentation_diagnostics(customers,[0,1,2,3],4)
        self.assertIsNone(result['silhouette'])
        self.assertEqual(result['status'],'Évaluation insuffisante')

    def test_poorly_separated_groups_are_flagged_before_interpretation(self):
        rng=np.random.default_rng(12)
        values=rng.normal(size=(100,6))
        customers=pd.DataFrame(values,columns=CLUSTER_FEATURES)
        labels=KMeans(n_clusters=3,n_init=10,random_state=42).fit_predict(StandardScaler().fit_transform(values))
        result=segmentation_diagnostics(customers,labels,3)
        self.assertLess(result['silhouette'],.25)
        self.assertIn('fragiles',result['status'])


class DashboardCallbacksTests(unittest.TestCase):
    def setUp(self):
        data=records();data['montant']=data['prix']*data['nombre_article'];data['prix_historique_connu']=True
        self.initial=Snapshot('v1',data,catalogue(),pd.Timestamp('2026-10-17',tz='UTC'))
        self.snapshots={'v1':self.initial};self.current=self.initial
        self.store=SimpleNamespace(get=lambda version=None:self.snapshots[version] if version else self.current,refresh=lambda:self.current)
        with patch('app.analytics.DashboardSnapshots',return_value=self.store):self.app=create_app(engine=Mock())
        self.callbacks={v['callback'].__wrapped__.__name__:v['callback'].__wrapped__ for v in self.app.callback_map.values()}

    def new_snapshot(self):
        data=self.initial.sales.copy()
        data.loc[len(data)]=data.iloc[-1]
        data.loc[len(data)-1,'date_commande']=pd.Timestamp('2024-04-05')
        data.loc[len(data)-1,'detailcommande_id']=999
        products=self.initial.products.copy();products.loc[0,'stock']=6
        self.current=Snapshot('v2',data,products,pd.Timestamp('2026-10-17 12:05',tz='UTC'))
        self.snapshots['v2']=self.current

    def test_refresh_extends_full_period_and_dates_the_new_snapshot(self):
        self.new_snapshot()
        result=self.callbacks['refresh_data'](1,'v1','2024-01-01','2024-03-24')
        self.assertEqual(result[0],'v2')
        self.assertIn('17/10/2026 à 12:05:00',result[1])
        self.assertEqual(pd.Timestamp(result[5]),pd.Timestamp('2024-04-05'))

    def test_refresh_preserves_custom_period(self):
        self.new_snapshot()
        result=self.callbacks['refresh_data'](1,'v1','2024-01-05','2024-02-01')
        self.assertEqual(result[4:6],('2024-01-05','2024-02-01'))

    def test_failed_refresh_keeps_all_data_controls_and_snapshot(self):
        def fail():raise OSError('Indisponible')
        self.store.refresh=fail
        result=self.callbacks['refresh_data'](1,'v1','2024-01-01','2024-03-24')
        self.assertIs(result[0],no_update)
        self.assertTrue(all(value is no_update for value in result[2:]))
        self.assertIn('conservées',str(result[1]))

    def test_new_browser_layout_uses_current_snapshot(self):
        self.new_snapshot()
        def find(component,identity):
            if getattr(component,'id',None)==identity:return component
            children=getattr(component,'children',None)
            if children is None:return None
            for child in children if isinstance(children,list) else [children]:
                if not isinstance(child,(str,int,float)):
                    result=find(child,identity)
                    if result is not None:return result
        self.assertEqual(find(self.app.layout(),'snapshot-version').data,'v2')

    def test_export_is_pinned_to_version_and_french_with_bom(self):
        self.new_snapshot()
        result=self.callbacks['export_csv'](1,None,None,None,None,None,'v1')
        self.assertTrue(result['content'].startswith('\ufeff'))
        self.assertIn('19,49',result['content'])
        self.assertNotIn('date_commande',result['content'])
        data=pd.read_csv(io.StringIO(result['content']),sep=';',decimal=',')
        self.assertEqual(len(data),84)
        self.assertAlmostEqual(data['Prix unitaire (FCFA)'].iloc[0],19.49)

    def test_detail_dates_sort_chronologically_not_lexicographically(self):
        result=self.callbacks['sort_detail']([{'column_id':'date_commande','direction':'desc'}],None,None,None,None,None,'v1')
        self.assertEqual(result[0]['date_commande'],'24/03/2024 à 00:00:00')
        self.assertEqual(result[-1]['date_commande'],'01/01/2024 à 00:00:00')

    def test_all_rankings_are_horizontal_and_zero_products_remain_visible(self):
        content=self.callbacks['update_content']('tab-1',None,None,None,None,None,'v1')
        figures=[]
        def visit(component):
            if getattr(component,'figure',None) is not None:figures.append(component.figure)
            children=getattr(component,'children',None)
            for child in children if isinstance(children,list) else [children]:
                if child is not None and not isinstance(child,(str,int,float)):visit(child)
        visit(content)
        bars=[trace for figure in figures for trace in figure.data if trace.type=='bar']
        self.assertTrue(bars)
        self.assertTrue(all(trace.orientation=='h' for trace in bars))
        self.assertTrue(any(0 in trace.x for trace in bars))


class FrenchFormatsTests(unittest.TestCase):
    def test_decimals_dates_and_unknown_values_are_readable(self):
        self.assertEqual(french_number(1949.49,2),'1\u202f949,49')
        self.assertEqual(french_number(None),'Non documenté')
        self.assertEqual(french_date('2024-12-31'),'31/12/2024')
        data=records(1).assign(montant=.1*3,prix=.1,prix_historique_connu=True)
        exported=french_export(data).to_csv(index=False,sep=';',decimal=',')
        self.assertIn('0,3',exported)
        self.assertNotIn('0,3000000000',exported)


if __name__=='__main__':unittest.main()
