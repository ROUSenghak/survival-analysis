from pathlib import Path
import numpy as np
import pandas as pd
from lifelines import KaplanMeierFitter, CoxPHFitter, WeibullAFTFitter, LogNormalAFTFitter
from lifelines.statistics import logrank_test, proportional_hazard_test
from lifelines.utils import concordance_index, restricted_mean_survival_time

ROOT=Path(__file__).resolve().parents[1]; P=ROOT/'data'/'processed'; T=ROOT/'reports'/'tables'; T.mkdir(parents=True,exist_ok=True)
VARIANTS=['balanced','broad','strict','no_temporal_score_reference_pool','forward_24m_no_duration','window_9m','window_12m','window_18m']

def load(v):
    path=P/f'boamp_survival_m0_{v}.csv'
    if not path.exists(): return None
    return pd.read_csv(path,parse_dates=['publication_date','start_date','estimated_end_date','study_end_date'],low_memory=False)

def prep(df):
    x=df[['time_to_event_or_censor_months','event','declared_duration_months','dur_was_imputed','buyer_key','buyer_key_type','cpv_division','publication_date']].copy()
    x=x[x.time_to_event_or_censor_months>0].dropna(subset=['declared_duration_months'])
    x['log_duration']=np.log1p(x.declared_duration_months); x['duration_sq']=x.log_duration**2; x['dur_was_imputed']=x.dur_was_imputed.astype(int); x['start_year']=x.publication_date.dt.year
    x['cpv_division']=x.cpv_division.fillna('MISSING').astype(str); x['buyer_key_type']=x.buyer_key_type.fillna('MISSING').astype(str)
    return pd.get_dummies(x,columns=['cpv_division','buyer_key_type'],drop_first=True)

def fit_cox(df,v,quadratic=False):
    x=prep(df); base=['time_to_event_or_censor_months','event','buyer_key','log_duration','dur_was_imputed']; cols=base+(['duration_sq'] if quadratic else [])+[c for c in x.columns if c.startswith('cpv_division_') or c.startswith('buyer_key_type_')]
    x=x[cols].copy(); rows=[]
    try:
        c=CoxPHFitter(penalizer=0.01); c.fit(x,duration_col='time_to_event_or_censor_months',event_col='event',cluster_col='buyer_key',robust=True)
        for term,r in c.summary.iterrows(): rows.append(dict(variant=v,model='cox_clustered_quadratic' if quadratic else 'cox_clustered',term=term,coef=r.coef,exp_coef=r['exp(coef)'],p=r.p,ci_lower=r['exp(coef) lower 95%'],ci_upper=r['exp(coef) upper 95%']))
        ph=proportional_hazard_test(c,x,duration_col='time_to_event_or_censor_months',event_col='event')
        phdf=ph.summary.reset_index().rename(columns={'index':'term'}); phdf.insert(0,'variant',v); phdf.to_csv(T/f'survival_ph_diagnostics_{v}.csv',index=False)
        return rows,c,x
    except Exception as e:
        rows.append(dict(variant=v,model='cox_clustered_quadratic' if quadratic else 'cox_clustered',term='ERROR',coef=np.nan,exp_coef=np.nan,p=np.nan,ci_lower=np.nan,ci_upper=np.nan,error=str(e))); return rows,None,x

def aft(df,v):
    x=prep(df).drop(columns=['buyer_key','publication_date'],errors='ignore'); rows=[]
    for cls,name in [(WeibullAFTFitter,'weibull_aft'),(LogNormalAFTFitter,'lognormal_aft')]:
        try:
            m=cls(penalizer=0.01); m.fit(x,duration_col='time_to_event_or_censor_months',event_col='event')
            rows.append(dict(variant=v,model=name,AIC=m.AIC_,log_likelihood=m.log_likelihood_,concordance_index=getattr(m,'concordance_index_',np.nan)))
        except Exception as e: rows.append(dict(variant=v,model=name,AIC=np.nan,log_likelihood=np.nan,concordance_index=np.nan,error=str(e)))
    return rows

def prediction_calibration(df,v,c,x):
    if c is None: return []
    rows=[]; px=x.drop(columns=['time_to_event_or_censor_months','event','buyer_key'],errors='ignore')
    for h in [12,24]:
        try:
            risk=1-c.predict_survival_function(x,times=[h]).T.iloc[:,0].to_numpy()
            tmp=df.loc[x.index].copy(); tmp['pred_risk']=risk; tmp['observed_by_horizon']=((tmp.event==1)&(tmp.time_to_event_or_censor_months<=h)).astype(int)
            tmp['risk_group']=pd.qcut(pd.Series(risk).rank(method='first'),5,labels=False)+1
            for g,z in tmp.groupby('risk_group'):
                rows.append(dict(variant=v,horizon_months=h,risk_group=int(g),n=len(z),mean_predicted_risk=z.pred_risk.mean(),observed_event_rate=z.observed_by_horizon.mean(),brier_score=np.mean((z.observed_by_horizon-z.pred_risk)**2)))
        except Exception as e: rows.append(dict(variant=v,horizon_months=h,risk_group=-1,n=0,mean_predicted_risk=np.nan,observed_event_rate=np.nan,brier_score=np.nan,error=str(e)))
    return rows

def main():
    km_rows=[]; logrank_rows=[]; cox_rows=[]; aft_rows=[]; pred_rows=[]; complexity=[]; functional=[]; validation=[]
    for v in VARIANTS:
        df=load(v)
        if df is None: continue
        km=KaplanMeierFitter(); km.fit(df.time_to_event_or_censor_months,df.event,label=v)
        km_rows.append(dict(variant=v,n=len(df),events=int(df.event.sum()),censoring_rate=1-df.event.mean(),median_survival_months=km.median_survival_time_,survival_at_12m=float(km.survival_function_at_times(12).iloc[0]),survival_at_24m=float(km.survival_function_at_times(24).iloc[0]),rmst_60m=float(restricted_mean_survival_time(km,t=60))))
        complexity.append(dict(variant=v,events=int(df.event.sum()),n_sources=len(df),n_buyers=df.buyer_key.nunique(),candidate_parameters_estimated='log_duration + imputation + CPV dummies + buyer_key_type dummies',approx_events_per_parameter=df.event.sum()/max(1,(2+df.cpv_division.nunique()+df.buyer_key_type.nunique()-2))))
        for div,g in df.groupby('cpv_division',dropna=False):
            if len(g)>10:
                k=KaplanMeierFitter(); k.fit(g.time_to_event_or_censor_months,g.event); km_rows.append(dict(variant=v+'__cpv',cpv_division=div,n=len(g),events=int(g.event.sum()),censoring_rate=1-g.event.mean(),median_survival_months=k.median_survival_time_,survival_at_12m=float(k.survival_function_at_times(12).iloc[0]),survival_at_24m=float(k.survival_function_at_times(24).iloc[0]),rmst_60m=float(restricted_mean_survival_time(k,t=60))))
        divs=[g for _,g in df[df.cpv_division.isin(['32','35','48','72'])].groupby('cpv_division') if g.event.sum()>0]
        for i in range(len(divs)):
            for j in range(i+1,len(divs)):
                a,b=divs[i],divs[j]; res=logrank_test(a.time_to_event_or_censor_months,b.time_to_event_or_censor_months,event_observed_A=a.event,event_observed_B=b.event); logrank_rows.append(dict(variant=v,group_a=str(a.cpv_division.iloc[0]),group_b=str(b.cpv_division.iloc[0]),test_statistic=res.test_statistic,p=res.p_value))
        rows,c,x=fit_cox(df,v,False); cox_rows+=rows; qrows,_,_=fit_cox(df,v,True); functional += [r for r in qrows if r.get('term') in ['log_duration','duration_sq','ERROR']]
        aft_rows+=aft(df,v); pred_rows+=prediction_calibration(df,v,c,x)
        try:
            train=df[df.publication_date.dt.year<=2021]; test=df[df.publication_date.dt.year>2021]
            tr_rows,c2,xtr=fit_cox(train,v+'_train_to_2021',False)
            if c2 is not None and len(test)>0:
                xt=prep(test); common=[col for col in xtr.columns if col in xt.columns]; xt=xt.reindex(columns=xtr.columns,fill_value=0); score=-c2.predict_partial_hazard(xt).to_numpy().ravel(); validation.append(dict(variant=v,train_n=len(train),train_events=int(train.event.sum()),test_n=len(test),test_events=int(test.event.sum()),test_c_index=concordance_index(test.loc[xt.index,'time_to_event_or_censor_months'],score,test.loc[xt.index,'event'])))
        except Exception as e: validation.append(dict(variant=v,error=str(e)))
    pd.DataFrame(km_rows).to_csv(T/'survival_km_summary.csv',index=False); pd.DataFrame(logrank_rows).to_csv(T/'survival_logrank_tests.csv',index=False); pd.DataFrame(cox_rows).to_csv(T/'survival_cox_models.csv',index=False); pd.DataFrame(aft_rows).to_csv(T/'survival_aft_models.csv',index=False); pd.DataFrame(pred_rows).to_csv(T/'survival_predictions_12_24m.csv',index=False); pd.DataFrame(complexity).to_csv(T/'survival_event_complexity.csv',index=False); pd.DataFrame(functional).to_csv(T/'survival_functional_form.csv',index=False); pd.DataFrame(validation, columns=['variant','train_n','train_events','test_n','test_events','test_c_index','error']).to_csv(T/'survival_temporal_validation.csv',index=False)
if __name__=='__main__': main()
