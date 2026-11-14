import pandas as pd, numpy as np
pd.set_option('display.width',250); pd.set_option('display.max_columns',30); pd.set_option('display.max_rows',300)
o=pd.read_csv('data/processed/technology_trade_orientation.csv')
c=pd.read_csv('data/processed/technology_trade_components.csv',dtype={'hs_code':str})
d=pd.read_parquet('data/interim/comtrade_technology_filtered.parquet')
sel=['JPN','KOR','S19','AUS','GBR','DEU','FRA','CAN','MEX','ISR','SGP','PHL','IND','VNM','MYS','HKG','SAU','ARE','BRA','RUS','IRN','PAK','THA','NZL','POL','ZAF','NGA','IDN','TUR','ITA']
w=o[o.country_iso3.isin(sel)].pivot_table(index='country_iso3',columns='year',values='tech_orientation_score').round(2)
print(w.to_string())
st=o[o.country_iso3.isin(sel)].groupby('country_iso3').data_status.agg(lambda x: ','.join(sorted(set(x)-{'complete'})))
print(st[st!=''])
# trends: complete obs, 2014-2024 (2025 partial year coverage), need >=9 obs
s=o[o.data_complete&(o.year<=2024)]
def slope(g):
    if len(g)<9: return np.nan
    return np.polyfit(g.year,g.tech_orientation_score,1)[0]
tr=s.groupby(['country_iso3','country']).apply(slope).dropna().rename('slope').reset_index()
first=s.groupby('country_iso3').apply(lambda g:g.sort_values('year').tech_orientation_score.head(3).mean()).rename('first3')
last=s.groupby('country_iso3').apply(lambda g:g.sort_values('year').tech_orientation_score.tail(3).mean()).rename('last3')
tot=s.assign(t=s.china_tech_imports+s.us_tech_imports).groupby('country_iso3').t.median().rename('med_tot_musd')/1e6
tr=tr.join(first,on='country_iso3').join(last,on='country_iso3').join(tot,on='country_iso3')
tr['change']=tr.last3-tr.first3
print('\ncountries with trend:',len(tr),' slope>0:',(tr.slope>0).sum(),' slope<0:',(tr.slope<0).sum(), ' median slope/yr %.4f'%tr.slope.median())
print('|change|<0.1:',(tr.change.abs()<0.1).sum())
big=tr[tr.med_tot_musd>=100]
print('among countries with median total>=US$100m:',len(big),' up:',(big.change>0.1).sum(),' down:',(big.change<-0.1).sum())
print('\nTOP UP (toward US)'); print(tr.sort_values('change',ascending=False).head(12).round(3).to_string(index=False))
print('\nTOP DOWN (toward China)'); print(tr.sort_values('change').head(12).round(3).to_string(index=False))
# large jumps diagnostics
f=pd.read_csv('outputs/tables/technology_qa_flags.csv'); j=f[f.flag=='large_yoy_change'].copy()
j['year']=j.year.astype(int)
o2=o.set_index(['country_iso3','year'])
j['status']=[o2.loc[(a,b),'data_status'] for a,b in zip(j.country_iso3,j.year)]
j['prev_status']=[o2.loc[(a,b-1),'data_status'] if (a,b-1) in o2.index else 'n/a' for a,b in zip(j.country_iso3,j.year)]
j['tot_musd']=[(o2.loc[(a,b),'china_tech_imports']+o2.loc[(a,b),'us_tech_imports'])/1e6 for a,b in zip(j.country_iso3,j.year)]
cls=d.groupby(['country_iso3','year']).classification.agg(lambda x:','.join(sorted(set(x))))
j['cls']=[cls.get((a,b),'') for a,b in zip(j.country_iso3,j.year)]; j['cls_prev']=[cls.get((a,b-1),'') for a,b in zip(j.country_iso3,j.year)]
j['partial_involved']=(j.status!='complete')|(j.prev_status!='complete')
j['cls_change']=j.cls!=j.cls_prev
j['small']=j.tot_musd<50
print('\nlarge jumps:',len(j),' partial involved:',j.partial_involved.sum(),' classification change:',j.cls_change.sum(),' total<US$50m:',j.small.sum(),
      ' none of these:',(~j.partial_involved&~j.cls_change&~j.small).sum())
print(j[~j.partial_involved&~j.small].sort_values('tot_musd',ascending=False)[['country_iso3','country','year','detail','tot_musd','cls_prev','cls']].round(1).to_string(index=False))
# HS vintage: median category score change at years where reporter switches classification vs not
cc=c.dropna(subset=['category_orientation_score']).merge(cls.rename('cls').reset_index(),on=['country_iso3','year'])
cc=cc.sort_values(['country_iso3','hs_code','year']); cc['prev']=cc.groupby(['country_iso3','hs_code']).category_orientation_score.shift(); cc['prev_cls']=cc.groupby(['country_iso3','hs_code']).cls.shift()
cc=cc.dropna(subset=['prev']); cc['dlt']=cc.category_orientation_score-cc.prev; cc['switch']=cc.cls!=cc.prev_cls
print('\n== |category change| by HS, switch vs no switch (median, share>0.5)')
print(cc.groupby(['hs_code','switch']).dlt.agg(n='size',med_abs=lambda x:x.abs().median(),big=lambda x:(x.abs()>0.5).mean()).round(3))
print('\nclassification mix by year:'); print(pd.crosstab(d.year,d.classification))
