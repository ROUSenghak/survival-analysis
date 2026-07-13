from pathlib import Path
import sys
import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from lifelines import KaplanMeierFitter
from lifelines.utils import restricted_mean_survival_time

ROOT=Path(__file__).resolve().parents[1]
P=ROOT/'data'/'processed'; T=ROOT/'reports'/'tables'; T.mkdir(parents=True,exist_ok=True)
sys.path.insert(0,str(ROOT/'scripts'))
import build_m0_candidate_pairs as bmcp
import run_m0_linkage as rml
WINDOWS=[6,9,12,18]
MAX_CAND=30

def load_sources():
    dtype={c:str for c in ['notice_id','buyer_key','buyer_key_type','buyer_name_normalized','buyer_siret_clean','buyer_siren_clean','objet_clean','cpv_clean','cpv_division','cpv_category','cpv_class','cpv_group','category_label']}
    s=pd.read_csv(P/'boamp_m0_sources.csv',dtype=dtype,parse_dates=['publication_date','start_date','estimated_end_date','study_end_date'],low_memory=False)
    return s[s.buyer_key_type!='MISSING'].sort_values(['buyer_key','publication_date']).reset_index(drop=True), s

def build_pairs(src,tfidf,W):
    ids=src.notice_id.to_numpy(); pub=src.publication_date.to_numpy(); end=src.estimated_end_date.to_numpy(); bk=src.buyer_key.to_numpy(object); bkt=src.buyer_key_type.to_numpy(object)
    main=src.cpv_clean.to_numpy(object); cat=src.cpv_category.to_numpy(object); cls=src.cpv_class.to_numpy(object); grp=src.cpv_group.to_numpy(object); div=src.cpv_division.to_numpy(object); gen=src.cpv_generic_flag.to_numpy()
    rec=[]; td=np.timedelta64(int(round(W*30.44)),'D')
    for _,idx in src.groupby('buyer_key',sort=False).indices.items():
        idx=np.asarray(idx); gp=pub[idx]; ge=end[idx]; n=len(idx)
        if n<2: continue
        for i in range(n):
            if pd.isna(ge[i]): continue
            lo=ge[i]-td; hi=ge[i]+td; left=np.searchsorted(gp,lo,'left'); right=np.searchsorted(gp,hi,'right')
            loc=np.arange(left,right); loc=loc[(gp[loc]>gp[i]) & (loc!=i)]
            if len(loc)==0: continue
            glob=idx[loc]; ig=idx[i]
            abs_gap=np.abs((gp[loc]-ge[i]))/np.timedelta64(1,'D')/30.44
            if len(loc)>MAX_CAND:
                keep=np.argsort(abs_gap)[:MAX_CAND]; loc=loc[keep]; glob=glob[keep]; abs_gap=abs_gap[keep]
            gaps=(gp[loc]-gp[i])/np.timedelta64(1,'D')/30.44; stime=np.clip(1-abs_gap/W,0,None); sims=tfidf[glob].dot(tfidf[ig].T).toarray().ravel(); sb= bmcp.BUYER_KEY_TYPE_SCORE.get(bkt[ig],0.0)
            for k,cg in enumerate(glob):
                scpv=bmcp.cpv_pair_score(main[ig],main[cg],cat[ig],cat[cg],cls[ig],cls[cg],grp[ig],grp[cg],div[ig],div[cg]); stext=float(sims[k])
                comp=bmcp.W_TEXT*stext+bmcp.W_CPV*scpv+bmcp.W_TIME*stime[k]+bmcp.W_BUYER*sb
                rec.append(dict(source_notice_id=ids[ig],candidate_notice_id=ids[cg],source_date=gp[i],candidate_date=gp[loc[k]],buyer_key=bk[ig],buyer_key_type=bkt[ig],gap_months=gaps[k],expected_end_date=ge[i],abs_gap_to_expected_end=abs_gap[k],s_time=stime[k],s_text=stext,s_cpv=scpv,s_buyer=sb,m0_composite_score=comp,cpv_missing=bool(pd.isna(main[ig]) or pd.isna(main[cg])),cpv_generic_flag=bool(gen[ig] or gen[cg])))
    pairs=pd.DataFrame(rec)
    if len(pairs):
        pairs=pairs.sort_values(['source_notice_id','m0_composite_score'],ascending=[True,False])
        pairs['candidate_rank']=pairs.groupby('source_notice_id').cumcount()+1; pairs['n_candidates_for_source']=pairs.groupby('source_notice_id').candidate_notice_id.transform('count')
        top2=pairs[pairs.candidate_rank<=2].pivot(index='source_notice_id',columns='candidate_rank',values='m0_composite_score'); margin=(top2.get(1)-top2.get(2)).fillna(top2.get(1)); pairs['top1_top2_margin']=pairs.source_notice_id.map(margin)
    return pairs

def km_summary(surv):
    km=KaplanMeierFitter(); km.fit(surv.time_to_event_or_censor_months,surv.event)
    return float(km.survival_function_at_times(24).iloc[0]), float(restricted_mean_survival_time(km,t=60))

def main():
    elig,all_sources=load_sources(); tfidf=TfidfVectorizer(max_features=50000,ngram_range=(1,2),min_df=2).fit_transform(elig.objet_clean.fillna('').tolist())
    ref=pd.read_csv(P/'boamp_m0_links_balanced.csv',dtype={'source_notice_id':str,'candidate_notice_id':str}); ref_keys=set(zip(ref.source_notice_id,ref.candidate_notice_id)); ref_src=set(ref.source_notice_id)
    rows=[]; by_year=[]; by_seg=[]
    for W in WINDOWS:
        print(f'window {W}m')
        pairs=build_pairs(elig,tfidf,W); rank1=pairs[pairs.candidate_rank==1].copy() if len(pairs) else pairs
        thr=rank1.m0_composite_score.quantile(.5) if len(rank1) else np.nan; links=rank1[rank1.m0_composite_score>=thr].copy() if len(rank1) else rank1.copy(); links['variant']=f'window_{W}m'; links['threshold_used']=thr
        out=P/f'boamp_m0_links_window_{W}m.csv'; links.to_csv(out,index=False)
        surv=rml.build_survival_dataset(all_sources,links,f'window_{W}m'); surv.to_csv(P/f'boamp_survival_m0_window_{W}m.csv',index=False)
        s24,rmst60=km_summary(surv); keys=set(zip(links.source_notice_id,links.candidate_notice_id)); src=set(links.source_notice_id); cnt=links.candidate_notice_id.value_counts()
        rows.append(dict(window_months=W,n_eligible_sources=len(elig),n_sources_with_candidate=rank1.source_notice_id.nunique() if len(rank1) else 0,blocking_coverage=(rank1.source_notice_id.nunique()/len(elig)) if len(elig) else np.nan,n_candidate_pairs=len(pairs),n_links=len(links),linking_rate=len(links)/len(elig),threshold_p50=thr,median_margin=rank1.top1_top2_margin.median() if len(rank1) else np.nan,n_reused_candidates=int((cnt>1).sum()),max_candidate_multiplicity=int(cnt.max()) if len(cnt) else 0,jaccard_vs_reference=len(keys&ref_keys)/len(keys|ref_keys) if keys|ref_keys else np.nan,source_event_status_changes=len(src^ref_src),survival_at_24m=s24,rmst_60m=rmst60,mean_s_text=links.s_text.mean() if len(links) else np.nan,mean_s_cpv=links.s_cpv.mean() if len(links) else np.nan,mean_s_time=links.s_time.mean() if len(links) else np.nan,mean_s_buyer=links.s_buyer.mean() if len(links) else np.nan))
        tmp=all_sources[['notice_id','publication_date','cpv_division','buyer_key_type']].merge(links[['source_notice_id']],left_on='notice_id',right_on='source_notice_id',how='left'); tmp['event']=tmp.source_notice_id.notna(); tmp['year']=tmp.publication_date.dt.year
        for y,g in tmp[tmp.buyer_key_type!='MISSING'].groupby('year'): by_year.append(dict(window_months=W,publication_year=int(y),n_sources=len(g),n_events=int(g.event.sum()),event_rate=g.event.mean()))
        for d,g in tmp[tmp.buyer_key_type!='MISSING'].groupby('cpv_division',dropna=False): by_seg.append(dict(window_months=W,cpv_division=d,n_sources=len(g),n_events=int(g.event.sum()),event_rate=g.event.mean()))
    pd.DataFrame(rows).to_csv(T/'m6d_temporal_window_sensitivity.csv',index=False); pd.DataFrame(by_year).to_csv(T/'m6d_temporal_window_by_year.csv',index=False); pd.DataFrame(by_seg).to_csv(T/'m6d_temporal_window_by_cpv_division.csv',index=False)
if __name__=='__main__': main()
