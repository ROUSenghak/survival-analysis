from pathlib import Path
import sys
import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from lifelines import CoxPHFitter

ROOT=Path(__file__).resolve().parents[1]
P=ROOT/'data'/'processed'; T=ROOT/'reports'/'tables'; T.mkdir(parents=True,exist_ok=True)
sys.path.insert(0,str(ROOT/'scripts'))
import build_m0_candidate_pairs as bmcp
import run_m0_linkage as rml
NO_TIME_W={'s_text':bmcp.W_TEXT/(bmcp.W_TEXT+bmcp.W_CPV+bmcp.W_BUYER),'s_cpv':bmcp.W_CPV/(bmcp.W_TEXT+bmcp.W_CPV+bmcp.W_BUYER),'s_buyer':bmcp.W_BUYER/(bmcp.W_TEXT+bmcp.W_CPV+bmcp.W_BUYER)}

def load():
    dtype={c:str for c in ['notice_id','buyer_key','buyer_key_type','buyer_name_normalized','buyer_siret_clean','buyer_siren_clean','objet_clean','cpv_clean','cpv_division','cpv_category','cpv_class','cpv_group','category_label']}
    allsrc=pd.read_csv(P/'boamp_m0_sources.csv',dtype=dtype,parse_dates=['publication_date','start_date','estimated_end_date','study_end_date'],low_memory=False)
    elig=allsrc[allsrc.buyer_key_type!='MISSING'].sort_values(['buyer_key','publication_date']).reset_index(drop=True)
    pairs=pd.read_csv(P/'boamp_m0_candidate_pairs.csv',dtype={'source_notice_id':str,'candidate_notice_id':str},parse_dates=['source_date','candidate_date','expected_end_date'],low_memory=False)
    ref=pd.read_csv(P/'boamp_m0_links_balanced.csv',dtype={'source_notice_id':str,'candidate_notice_id':str},parse_dates=['source_date','candidate_date','expected_end_date'],low_memory=False)
    return allsrc,elig,pairs,ref

def make_links_from_pairs(pairs,name,score_col):
    x=pairs.sort_values(['source_notice_id',score_col],ascending=[True,False]).copy(); x['candidate_rank']=x.groupby('source_notice_id').cumcount()+1; r1=x[x.candidate_rank==1].copy(); thr=r1[score_col].quantile(.5); links=r1[r1[score_col]>=thr].copy(); links['m0_composite_score']=links[score_col]; links['variant']=name; links['threshold_used']=thr; return links,thr

def forward_pairs(src,tfidf,months=24):
    ids=src.notice_id.to_numpy(); pub=src.publication_date.to_numpy(); bk=src.buyer_key.to_numpy(object); bkt=src.buyer_key_type.to_numpy(object); main=src.cpv_clean.to_numpy(object); cat=src.cpv_category.to_numpy(object); cls=src.cpv_class.to_numpy(object); grp=src.cpv_group.to_numpy(object); div=src.cpv_division.to_numpy(object); gen=src.cpv_generic_flag.to_numpy(); rec=[]; maxcand=30
    for _,idx in src.groupby('buyer_key',sort=False).indices.items():
        idx=np.asarray(idx); gp=pub[idx]; n=len(idx)
        if n<2: continue
        for i in range(n):
            hi=gp[i]+np.timedelta64(int(round(months*30.44)),'D'); loc=np.where((gp>gp[i]) & (gp<=hi))[0]
            if len(loc)==0: continue
            glob=idx[loc]; gaps=(gp[loc]-gp[i])/np.timedelta64(1,'D')/30.44
            if len(loc)>maxcand:
                keep=np.argsort(gaps)[:maxcand]; loc=loc[keep]; glob=glob[keep]; gaps=gaps[keep]
            sims=tfidf[glob].dot(tfidf[idx[i]].T).toarray().ravel(); sb=bmcp.BUYER_KEY_TYPE_SCORE.get(bkt[idx[i]],0.0)
            for k,cg in enumerate(glob):
                scpv=bmcp.cpv_pair_score(main[idx[i]],main[cg],cat[idx[i]],cat[cg],cls[idx[i]],cls[cg],grp[idx[i]],grp[cg],div[idx[i]],div[cg]); stext=float(sims[k]); score=NO_TIME_W['s_text']*stext+NO_TIME_W['s_cpv']*scpv+NO_TIME_W['s_buyer']*sb
                rec.append(dict(source_notice_id=ids[idx[i]],candidate_notice_id=ids[cg],source_date=gp[i],candidate_date=gp[loc[k]],buyer_key=bk[idx[i]],buyer_key_type=bkt[idx[i]],gap_months=gaps[k],expected_end_date=pd.NaT,abs_gap_to_expected_end=np.nan,s_time=np.nan,s_text=stext,s_cpv=scpv,s_buyer=sb,m0_composite_score=score,cpv_missing=bool(pd.isna(main[idx[i]]) or pd.isna(main[cg])),cpv_generic_flag=bool(gen[idx[i]] or gen[cg]),score_forward_no_duration=score))
    out=pd.DataFrame(rec)
    if len(out):
        out=out.sort_values(['source_notice_id','score_forward_no_duration'],ascending=[True,False]); out['candidate_rank']=out.groupby('source_notice_id').cumcount()+1; out['n_candidates_for_source']=out.groupby('source_notice_id').candidate_notice_id.transform('count'); top2=out[out.candidate_rank<=2].pivot(index='source_notice_id',columns='candidate_rank',values='score_forward_no_duration'); out['top1_top2_margin']=out.source_notice_id.map((top2.get(1)-top2.get(2)).fillna(top2.get(1)))
    return out

def summarize(name,links,allsrc,ref_keys,ref_src):
    links.to_csv(P/f'boamp_m0_links_{name}.csv',index=False); surv=rml.build_survival_dataset(allsrc,links,name); surv.to_csv(P/f'boamp_survival_m0_{name}.csv',index=False)
    keys=set(zip(links.source_notice_id,links.candidate_notice_id)); src=set(links.source_notice_id); cnt=links.candidate_notice_id.value_counts(); return surv,dict(variant=name,n_links=len(links),event_rate=len(links)/len(allsrc[allsrc.buyer_key_type!='MISSING']),jaccard_vs_reference=len(keys&ref_keys)/len(keys|ref_keys) if keys|ref_keys else np.nan,event_status_changes_vs_reference=len(src^ref_src),n_reused_candidates=int((cnt>1).sum()),max_candidate_multiplicity=int(cnt.max()) if len(cnt) else 0,observed_duration_event_rate=surv.loc[~surv.dur_was_imputed,'event'].mean(),imputed_duration_event_rate=surv.loc[surv.dur_was_imputed,'event'].mean(),median_event_time=surv.loc[surv.event==1,'time_to_event_or_censor_months'].median())

def cox_duration(surv,name):
    df=surv[['time_to_event_or_censor_months','event','declared_duration_months','dur_was_imputed','buyer_key']].dropna().copy(); df['log_duration']=np.log1p(df.declared_duration_months); df['dur_was_imputed']=df.dur_was_imputed.astype(int)
    rows=[]
    for robust in [False,True]:
        try:
            c=CoxPHFitter(); cols=['time_to_event_or_censor_months','event','log_duration','dur_was_imputed']+(['buyer_key'] if robust else []); c.fit(df[cols],duration_col='time_to_event_or_censor_months',event_col='event',cluster_col='buyer_key' if robust else None,robust=robust)
            for term,r in c.summary.iterrows(): rows.append(dict(variant=name,model='cox_duration_clustered' if robust else 'cox_duration',term=term,coef=r.coef,exp_coef=r['exp(coef)'],p=r.p,ci_lower=r['exp(coef) lower 95%'],ci_upper=r['exp(coef) upper 95%']))
        except Exception as e: rows.append(dict(variant=name,model='cox_duration_clustered' if robust else 'cox_duration',term='ERROR',coef=np.nan,exp_coef=np.nan,p=np.nan,ci_lower=np.nan,ci_upper=np.nan,error=str(e)))
    return rows

def main():
    allsrc,elig,pairs,ref=load(); ref_keys=set(zip(ref.source_notice_id,ref.candidate_notice_id)); ref_src=set(ref.source_notice_id)
    rows=[]; cox=[]
    ref_surv=pd.read_csv(P/'boamp_survival_m0_balanced.csv',parse_dates=['publication_date','start_date','estimated_end_date','study_end_date'],low_memory=False); rows.append(dict(variant='balanced_reference',n_links=len(ref),event_rate=len(ref)/len(elig),jaccard_vs_reference=1,event_status_changes_vs_reference=0,n_reused_candidates=int((ref.candidate_notice_id.value_counts()>1).sum()),max_candidate_multiplicity=int(ref.candidate_notice_id.value_counts().max()),observed_duration_event_rate=ref_surv.loc[~ref_surv.dur_was_imputed,'event'].mean(),imputed_duration_event_rate=ref_surv.loc[ref_surv.dur_was_imputed,'event'].mean(),median_event_time=ref_surv.loc[ref_surv.event==1,'time_to_event_or_censor_months'].median())); cox+=cox_duration(ref_surv,'balanced_reference')
    nt=pairs.copy(); nt['score_no_temporal']=NO_TIME_W['s_text']*nt.s_text+NO_TIME_W['s_cpv']*nt.s_cpv+NO_TIME_W['s_buyer']*nt.s_buyer; nt_links,thr=make_links_from_pairs(nt,'no_temporal_score_reference_pool','score_no_temporal'); surv,s=summarize('no_temporal_score_reference_pool',nt_links,allsrc,ref_keys,ref_src); rows.append(s); cox+=cox_duration(surv,'no_temporal_score_reference_pool')
    tfidf=TfidfVectorizer(max_features=50000,ngram_range=(1,2),min_df=2).fit_transform(elig.objet_clean.fillna('').tolist()); fp=forward_pairs(elig,tfidf,24); fp.to_csv(P/'boamp_m0_candidate_pairs_forward_24m_no_duration.csv',index=False); flinks,thr=make_links_from_pairs(fp,'forward_24m_no_duration','score_forward_no_duration'); surv,s=summarize('forward_24m_no_duration',flinks,allsrc,ref_keys,ref_src); rows.append(s); cox+=cox_duration(surv,'forward_24m_no_duration')
    pd.DataFrame(rows).to_csv(T/'duration_leakage_linkage_sensitivity.csv',index=False); pd.DataFrame(cox).to_csv(T/'duration_leakage_cox_duration_effect.csv',index=False)
if __name__=='__main__': main()
