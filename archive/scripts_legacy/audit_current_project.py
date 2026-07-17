from pathlib import Path
import csv, hashlib
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
P=ROOT/'data'/'processed'
R=ROOT/'reports'
T=R/'tables'
T.mkdir(parents=True, exist_ok=True)
SEED=20260713
STR=['notice_id','buyer_key','buyer_key_type','buyer_name_normalized','buyer_siret_clean','buyer_siren_clean','cpv_clean','cpv_division','cpv_group','cpv_class','cpv_category','category_label']

def shape(path):
    if not path.exists(): return (None,None)
    with path.open('r',encoding='utf-8',errors='replace',newline='') as f:
        rd=csv.reader(f)
        try: h=next(rd)
        except StopIteration: return (0,0)
        return (sum(1 for _ in rd),len(h))

def sha(path):
    if not path.exists() or path.is_dir(): return None
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(1048576),b''): h.update(b)
    return h.hexdigest()

def load():
    dtype={c:str for c in STR}
    sources=pd.read_csv(P/'boamp_m0_sources.csv',dtype=dtype,parse_dates=['publication_date','start_date','estimated_end_date','study_end_date'],low_memory=False)
    pairs=pd.read_csv(P/'boamp_m0_candidate_pairs.csv',dtype={'source_notice_id':str,'candidate_notice_id':str,'buyer_key':str,'buyer_key_type':str},parse_dates=['source_date','candidate_date','expected_end_date'],low_memory=False)
    surv=pd.read_csv(P/'boamp_survival_m0_balanced.csv',dtype={'notice_id':str,'linked_candidate_notice_id':str,'buyer_key':str,'buyer_key_type':str,'cpv_division':str},parse_dates=['publication_date','start_date','estimated_end_date','study_end_date'],low_memory=False)
    links={v:pd.read_csv(P/f'boamp_m0_links_{v}.csv',dtype={'source_notice_id':str,'candidate_notice_id':str,'buyer_key':str,'buyer_key_type':str},parse_dates=['source_date','candidate_date','expected_end_date'],low_memory=False) for v in ['broad','balanced','strict']}
    return sources,pairs,surv,links

def inventory():
    defs=[('raw_pdl_json',ROOT/'data/raw/boamp/pdl','monthly raw JSON','download_boamp.py','monthly export','current'),('raw_national_archive',ROOT/'data/raw/boamp_national_2024_2026_archive','superseded national raw JSON','none active','monthly export','stale/superseded'),('interim_flattened',ROOT/'data/interim/boamp_raw_flattened.csv','flattened notices','parse_boamp.py','notice','current'),('cleaned_notices',P/'boamp_clean_m0_no_enrichment.csv','cleaned all notices','preprocess_boamp_m0.py','notice','current'),('m0_sources',P/'boamp_m0_sources.csv','M0 digital APPEL_OFFRE sources','preprocess_boamp_m0.py','source notice','current'),('candidate_pairs',P/'boamp_m0_candidate_pairs.csv','blocked/scored pairs','build_m0_candidate_pairs.py','source-candidate pair','current'),('links_broad',P/'boamp_m0_links_broad.csv','broad links','run_m0_linkage.py','accepted link','current'),('links_balanced',P/'boamp_m0_links_balanced.csv','reference balanced links','run_m0_linkage.py','accepted link','current'),('links_strict',P/'boamp_m0_links_strict.csv','strict links','run_m0_linkage.py','accepted link','current'),('survival_balanced',P/'boamp_survival_m0_balanced.csv','reference survival handoff','run_m0_linkage.py','source notice','current')]
    rows=[]
    for name,path,desc,script,unit,status in defs:
        if path.is_dir(): n,c=len(list(path.glob('*.json'))),np.nan
        else: n,c=shape(path)
        rows.append(dict(dataset=name,path=str(path.relative_to(ROOT)),description=desc,unit_of_observation=unit,creation_script=script,row_count=n,column_count=c,current_or_stale=status,sha256=sha(path)))
    pd.DataFrame(rows).to_csv(T/'audit_dataset_inventory.csv',index=False)
    lin=[('raw BOAMP data','data/raw/boamp/pdl/boamp_YYYYMM.json','download_boamp.py','DILA API by month, PdL departments'),('flattening','data/interim/boamp_raw_flattened.csv','parse_boamp.py','raw JSON'),('filter/preprocess','data/processed/boamp_clean_m0_no_enrichment.csv','preprocess_boamp_m0.py','flattened CSV'),('eligible sources','data/processed/boamp_m0_sources.csv','preprocess_boamp_m0.py','cleaned notices'),('candidate generation','data/processed/boamp_m0_candidate_pairs.csv','build_m0_candidate_pairs.py','M0 sources'),('accepted links','data/processed/boamp_m0_links_balanced.csv','run_m0_linkage.py','candidate pairs'),('survival handoff','data/processed/boamp_survival_m0_balanced.csv','run_m0_linkage.py','sources + links')]
    pd.DataFrame(lin,columns=['stage','official_path','script','upstream_dependencies']).to_csv(T/'audit_data_lineage.csv',index=False)

def source_diag(sources,pairs):
    elig=sources[sources.buyer_key_type!='MISSING'].copy()
    window=int((P/'_m0_window_months.txt').read_text().strip()) if (P/'_m0_window_months.txt').exists() else 6
    wd=window*30.44
    counts=pairs.groupby('source_notice_id').size()
    best=pairs.sort_values(['source_notice_id','m0_composite_score'],ascending=[True,False]).groupby('source_notice_id').head(1).set_index('source_notice_id')
    second=pairs[pairs.candidate_rank==2].set_index('source_notice_id')['m0_composite_score']
    reuse=best['candidate_notice_id'].value_counts()
    rows=[]; has=set(counts.index)
    for bk,g0 in elig.sort_values(['buyer_key','publication_date']).groupby('buyer_key',dropna=False):
        g=g0.reset_index(drop=True); dates=g.publication_date.to_numpy()
        for _,r in g.iterrows():
            nid=r.notice_id; later=dates>np.datetime64(r.publication_date); nlate=int(later.sum())
            if pd.notna(r.estimated_end_date):
                lo=r.estimated_end_date-pd.Timedelta(days=wd); hi=r.estimated_end_date+pd.Timedelta(days=wd)
                nwin=int((later & (dates>=np.datetime64(lo)) & (dates<=np.datetime64(hi))).sum())
            else: nwin=0
            if nid in has: cause='has_candidates'
            elif nlate==0: cause='no_later_same_buyer_notice'
            elif nwin==0: cause='temporal_window_excluded_all_later_same_buyer'
            else: cause='hard_filter_or_candidate_cap_edge_case'
            b=best.loc[nid] if nid in best.index else None
            cand=b.candidate_notice_id if b is not None else None
            rows.append(dict(source_notice_id=nid,publication_year=r.publication_date.year,cpv_division=r.cpv_division,buyer_key=r.buyer_key,buyer_key_type=r.buyer_key_type,duration_status='imputed' if bool(r.dur_was_imputed) else 'observed',buyer_publication_frequency=len(g),n_later_same_buyer_sources=nlate,n_later_same_buyer_in_temporal_window=nwin,n_scored_candidates=int(counts.get(nid,0)),best_score=float(b.m0_composite_score) if b is not None else np.nan,second_best_score=float(second.get(nid,np.nan)),score_margin=float(b.top1_top2_margin) if b is not None else np.nan,source_has_only_one_candidate=bool(counts.get(nid,0)==1),selected_candidate_notice_id=cand,selected_candidate_multiplicity=int(reuse.get(cand,0)) if cand is not None else 0,zero_candidate_cause=cause))
    out=pd.DataFrame(rows); out.to_csv(T/'audit_candidate_source_diagnostics.csv',index=False); return out

def coverage(diag,sources):
    rows=[]
    def add(k,v,f):
        n=len(f); w=int((f.n_scored_candidates>0).sum()) if n else 0
        rows.append(dict(breakdown=k,level=str(v),n_eligible_sources=n,n_sources_with_candidate=w,n_sources_zero_candidate=n-w,blocking_coverage=w/n if n else np.nan))
    add('overall','eligible_nonmissing_buyer_key',diag)
    for c in ['publication_year','cpv_division','buyer_key_type','duration_status','zero_candidate_cause']:
        for v,f in diag.groupby(c,dropna=False): add(c,v,f)
    bins=pd.cut(diag.buyer_publication_frequency,[0,1,2,5,10,25,np.inf],labels=['1','2','3-5','6-10','11-25','26+'])
    for v,f in diag.assign(freq_bin=bins).groupby('freq_bin',observed=False): add('buyer_publication_frequency',v,f)
    miss=sources[sources.buyer_key_type=='MISSING']
    rows.append(dict(breakdown='buyer_blocking_eligibility',level='missing_buyer_key_excluded_before_candidate_generation',n_eligible_sources=len(miss),n_sources_with_candidate=0,n_sources_zero_candidate=len(miss),blocking_coverage=0.0 if len(miss) else np.nan))
    pd.DataFrame(rows).to_csv(T/'audit_blocking_coverage.csv',index=False)

def duplicates_scores(pairs,links,sources):
    bal=links['balanced']; cnt=bal.candidate_notice_id.value_counts().rename_axis('candidate_notice_id').reset_index(name='n_sources_selecting_candidate')
    summ=pd.DataFrame([dict(variant='balanced',n_selected_links=len(bal),n_unique_selected_candidates=bal.candidate_notice_id.nunique(),n_candidates_reused=int((cnt.n_sources_selecting_candidate>1).sum()),share_candidates_reused=float((cnt.n_sources_selecting_candidate>1).mean()) if len(cnt) else 0,max_multiplicity=int(cnt.n_sources_selecting_candidate.max()) if len(cnt) else 0)])
    summ.to_csv(T/'audit_duplicate_candidate_summary.csv',index=False)
    cnt.n_sources_selecting_candidate.value_counts().sort_index().rename_axis('multiplicity').reset_index(name='n_candidates').to_csv(T/'audit_duplicate_candidate_distribution.csv',index=False)
    ex=cnt.merge(bal[['candidate_notice_id','source_notice_id','buyer_key','m0_composite_score','top1_top2_margin']],on='candidate_notice_id',how='left')
    ex=ex.merge(sources[['notice_id','objet_clean','cpv_clean','cpv_division']].add_prefix('source_'),left_on='source_notice_id',right_on='source_notice_id',how='left')
    ex.sort_values(['n_sources_selecting_candidate','candidate_notice_id','m0_composite_score'],ascending=[False,True,False]).head(100).to_csv(T/'audit_duplicate_candidate_examples.csv',index=False)
    keys=set(zip(bal.source_notice_id,bal.candidate_notice_id))
    pops={'all_candidate_pairs':pairs,'rank1_candidates':pairs[pairs.candidate_rank==1],'accepted_balanced_links':pairs[[x in keys for x in zip(pairs.source_notice_id,pairs.candidate_notice_id)]],'rejected_candidates':pairs[[x not in keys for x in zip(pairs.source_notice_id,pairs.candidate_notice_id)]],'runner_up_candidates':pairs[pairs.candidate_rank==2]}
    rows=[]
    for pop,df in pops.items():
        for c in ['m0_composite_score','s_text','s_cpv','s_time','s_buyer','top1_top2_margin']:
            if c in df and len(df):
                d=df[c].describe(percentiles=[.1,.25,.5,.75,.9])
                rows.append({'population':pop,'score':c,**{k:d.get(k,np.nan) for k in ['count','mean','std','min','10%','25%','50%','75%','90%','max']}})
    pd.DataFrame(rows).to_csv(T/'audit_score_component_distributions.csv',index=False)

def implementation_matrix():
    rows=[
('Eligibility definition','Which source contracts can enter linkage?','IMPLEMENTED AND VERIFIED','preprocess_boamp_m0.py','boamp_m0_sources.csv','APPEL_OFFRE digital scope; nonmissing buyer key for candidate generation','duration imputation affects estimated end dates','P1'),
('Blocking coverage','How many eligible sources can be compared?','PARTIALLY IMPLEMENTED','build_m0_candidate_pairs.py','audit_blocking_coverage.csv','same buyer_key and duration-centered temporal window','zero-candidate causes were absent before audit','P1'),
('Candidate-pool diagnostics','Are candidate pools ambiguous?','PARTIALLY IMPLEMENTED','candidate rank/margin columns','audit_candidate_source_diagnostics.csv','top two scores summarize ambiguity','no source-level table before audit','P1'),
('Duplicate-candidate analysis','Is one candidate reused by many sources?','PARTIALLY IMPLEMENTED','run_m0_linkage.py duplicate count','audit_duplicate_candidate_*.csv','many-to-one may be valid for lots/frameworks','examples/distribution absent before audit','P1'),
('Score and margin diagnostics','Which components drive decisions?','PARTIALLY IMPLEMENTED','m0_score_distribution_summary.csv','audit_score_component_distributions.csv','internal scores are not validation','accepted/rejected/runner-up populations absent before audit','P1'),
('Threshold sensitivity','Do cutoffs alter events?','IMPLEMENTED BUT INCONSISTENT','eval_m6a_threshold_sensitivity.py','m6a_threshold_*.csv','percentile thresholds','hardcoded eligible denominator and limited breakdown','P1'),
('Temporal-window sensitivity','Does the window drive links?','NOT IMPLEMENTED','none found','pending eval_m6d_temporal_window_sensitivity.py','rerun candidate generation for each W','single 6-month window only','P1'),
('Feature ablation','Which components change rankings?','PARTIALLY IMPLEMENTED','eval_m6b_feature_ablation.py','m6b_feature_ablation.csv','drop component, renormalize, rerank','missing selected-candidate/event-status/survival summaries','P2'),
('Weight sensitivity','Do manual weights matter?','NOT IMPLEMENTED','none found','none','weights are manual','no perturbation grid','P2'),
('Fellegi-Sunter mixture','Model-based precision conditional on Omega?','IMPLEMENTED AND VERIFIED','eval_m3_fellegi_sunter_mixture.py','m3_*.csv','unsupervised beta mixture','not verified accuracy; beta imperfect for discrete variables','P2'),
('Semi-synthetic corruption/recovery','Robustness to field degradation?','IMPLEMENTED BUT INCONSISTENT','eval_m4_corruption_recovery.py','m4_*.csv','strict links are reference subset, not truth','fixed candidate pool when corrupted fields may affect blocking','P2'),
('Duration-leakage audit','Does duration mechanically construct events?','NOT IMPLEMENTED','duration used in preprocessing/linkage/survival','pending eval_duration_leakage.py','duration defines expected end, temporal score, survival timing','risk not quantified','P1'),
('Placebo/negative controls','Do links separate from plausible nonmatches?','NOT IMPLEMENTED','none found','none','internal score separation is not truth','no runner-up/random/date-shift placebo','P2'),
('Manual-validation readiness','Can humans label a balanced sample?','NOT IMPLEMENTED','none found','manual_validation_sample_unlabeled.csv','do not fabricate labels','no annotation sample/guide before audit','P1'),
('Survival-time/censoring construction','Are event/censoring times coherent?','PARTIALLY IMPLEMENTED','run_m0_linkage.py','audit_survival_construction_checks.csv','event time uses candidate-source gap_months','request says source start date; code uses publication-date gap','P1'),
('Censoring diagnostics','Are censored rows different?','NOT IMPLEMENTED','none found','audit_censoring_diagnostics.csv','administrative censoring differs from linkage failure','no SMD/balance table before audit','P1'),
('Event counts/model complexity','Enough events per model?','PARTIALLY IMPLEMENTED','m0_event_counts.csv','pending survival_event_complexity.csv','events per parameter should be checked','no model complexity table','P1'),
('Proportional hazards','Does Cox PH hold?','NOT IMPLEMENTED','none found','pending survival_ph_diagnostics.csv','Schoenfeld residuals where supported','no Cox model yet','P2'),
('Functional form','Are continuous effects linear?','NOT IMPLEMENTED','none found','pending survival_functional_form.csv','duration may be nonlinear/circular','no transform/spline check','P2'),
('Dependence within buyer','Are SEs buyer-robust?','NOT IMPLEMENTED','none found','pending survival_cox_models.csv','cluster by buyer_key','no robust buyer inference','P2'),
('Temporal validation','Do predictions generalize over time?','NOT IMPLEMENTED','none found','pending survival_temporal_validation.csv','avoid censoring-dominated split','no validation','P3'),
('Alternative event definitions','Are conclusions robust to definitions?','PARTIALLY IMPLEMENTED','broad/balanced/strict; eval_m6c','m6c_km_summary.csv','alternative definitions should rebuild links','only broad/strict KM by CPV exists','P1'),
('Downstream robustness','Do survival conclusions survive uncertainty?','PARTIALLY IMPLEMENTED','eval_m6c_variant_km_robustness.py','m6c_*.csv','KM/RMST only','no Cox/AFT/prediction robustness','P2'),
('Ranking stability','Are segment/buyer rankings stable?','PARTIALLY IMPLEMENTED','eval_m6c rank correlation','m6c_km_rank_correlation.csv','few CPV divisions','no buyer/top-risk stability','P3'),
('Bootstrap uncertainty','How large is pipeline uncertainty?','NOT IMPLEMENTED','none found','none','full-pipeline bootstrap costly','not implemented','P3'),
('Operational prediction calibration','Are 12/24m risks calibrated?','NOT IMPLEMENTED','none found','pending survival_predictions_12_24m.csv','against constructed proxy event only','not implemented','P3')]
    pd.DataFrame(rows,columns=['check_name','scientific_question','status','evidence_in_code','evidence_in_outputs','main_assumptions','problems_found','priority']).to_csv(T/'audit_credibility_implementation_matrix.csv',index=False)

def survival_checks(surv,links,diag):
    bal=links['balanced'].set_index('source_notice_id'); rows=[]; linked=set(bal.index); sids=set(surv.notice_id)
    rows += [('survival_rows',len(surv),'rows in balanced survival handoff'),('duplicated_survival_notice_ids',int(surv.notice_id.duplicated().sum()),'must be zero'),('events',int(surv.event.sum()),'event rows'),('balanced_links',len(bal),'accepted links'),('events_equal_links',int(surv.event.sum()==len(bal)),'1 pass'),('event_rows_missing_candidate',int(((surv.event==1)&surv.linked_candidate_notice_id.isna()).sum()),'must be zero'),('censored_rows_with_candidate',int(((surv.event==0)&surv.linked_candidate_notice_id.notna()).sum()),'must be zero'),('nonpositive_time',int((surv.time_to_event_or_censor_months<=0).sum()),'must be zero'),('event_ids_not_in_links',len(set(surv.loc[surv.event==1,'notice_id'])-linked),'must be zero'),('links_not_in_survival',len(linked-sids),'must be zero')]
    ev=surv[surv.event==1].merge(bal[['candidate_date','gap_months']],left_on='notice_id',right_index=True,how='left')
    rows.append(('max_abs_event_time_gap_diff',float((ev.time_to_event_or_censor_months-ev.gap_months).abs().max()) if len(ev) else 0,'event time equals link gap_months'))
    rows.append(('events_after_study_end',int((ev.candidate_date>ev.study_end_date).sum()),'must be zero'))
    pd.DataFrame(rows,columns=['check','value','note']).to_csv(T/'audit_survival_construction_checks.csv',index=False)
    sx=surv.merge(diag[['source_notice_id','n_scored_candidates','zero_candidate_cause','buyer_publication_frequency']],left_on='notice_id',right_on='source_notice_id',how='left')
    event=sx[sx.event==1]; cens=sx[sx.event==0]; out=[]
    for c in ['declared_duration_months','n_scored_candidates','buyer_publication_frequency']:
        x=pd.to_numeric(event[c],errors='coerce').dropna(); y=pd.to_numeric(cens[c],errors='coerce').dropna(); pooled=np.sqrt((x.var(ddof=1)+y.var(ddof=1))/2) if len(x)>1 and len(y)>1 else np.nan
        out.append(dict(variable=c,type='numeric',level='',event_mean=x.mean(),censored_mean=y.mean(),standardized_mean_difference=(x.mean()-y.mean())/pooled if pooled and not np.isnan(pooled) else np.nan,event_share=np.nan,censored_share=np.nan))
    for c in ['publication_date','buyer_key_type','cpv_division','dur_was_imputed','zero_candidate_cause']:
        vals=sx[c].dt.year if c=='publication_date' else sx[c].astype(str)
        evvals=event[c].dt.year if c=='publication_date' else event[c].astype(str); cevals=cens[c].dt.year if c=='publication_date' else cens[c].astype(str)
        for v in sorted(pd.Series(vals).dropna().unique()): out.append(dict(variable='publication_year' if c=='publication_date' else c,type='categorical_share',level=v,event_share=float((evvals==v).mean()) if len(event) else np.nan,censored_share=float((cevals==v).mean()) if len(cens) else np.nan,event_mean=np.nan,censored_mean=np.nan,standardized_mean_difference=np.nan))
    pd.DataFrame(out).to_csv(T/'audit_censoring_diagnostics.csv',index=False)

def manual_sample(pairs,links,diag):
    bal=links['balanced']; keys=set(zip(bal.source_notice_id,bal.candidate_notice_id)); df=pairs.copy(); df['is_selected_balanced_link']=[k in keys for k in zip(df.source_notice_id,df.candidate_notice_id)]
    df=df.merge(diag[['source_notice_id','duration_status','selected_candidate_multiplicity','n_scored_candidates']],on='source_notice_id',how='left')
    df['score_tier']=pd.qcut(df.m0_composite_score.rank(method='first'),3,labels=['low','medium','high']); df['margin_tier']=pd.qcut(df.top1_top2_margin.rank(method='first'),3,labels=['small','medium','large'])
    df['candidate_pool_type']=np.where(df.n_scored_candidates<=1,'single','multiple'); df['duplicate_case']=np.where(df.selected_candidate_multiplicity>1,'duplicate_selected_candidate','not_duplicate')
    rng=np.random.default_rng(SEED); parts=[]; strata=['is_selected_balanced_link','score_tier','margin_tier','buyer_key_type','duration_status','candidate_pool_type','duplicate_case']
    for _,g in df.groupby(strata,dropna=False,observed=False): parts.append(g.sample(n=min(2,len(g)),random_state=int(rng.integers(0,1000000))))
    sample=pd.concat(parts).drop_duplicates(['source_notice_id','candidate_notice_id']).head(160); sample['human_label']=''; sample['reviewer_notes']=''
    cols=['source_notice_id','candidate_notice_id','is_selected_balanced_link','candidate_rank','m0_composite_score','top1_top2_margin','score_tier','margin_tier','buyer_key_type','duration_status','candidate_pool_type','duplicate_case','source_date','candidate_date','gap_months','s_text','s_cpv','s_time','s_buyer','human_label','reviewer_notes']
    sample[cols].to_csv(T/'manual_validation_sample_unlabeled.csv',index=False)
    (R/'manual_validation_guide.md').write_text('# Manual validation guide\n\nThis defines an annotation task; it does not contain labels.\n\nAllowed labels: credible_renewal, likely_not_renewal, uncertain, insufficient_evidence. Do not infer labels from the M0 score. Record reviewer notes and adjudicate disagreements before using labels as validation evidence.\n',encoding='utf-8')

def main():
    print('loading data'); sources,pairs,surv,links=load()
    print('inventory'); inventory(); implementation_matrix()
    print('source diagnostics'); diag=source_diag(sources,pairs); coverage(diag,sources)
    print('duplicates/scores'); duplicates_scores(pairs,links,sources)
    print('survival/censoring'); survival_checks(surv,links,diag)
    print('manual sample'); manual_sample(pairs,links,diag)
    print('done')
if __name__=='__main__': main()
