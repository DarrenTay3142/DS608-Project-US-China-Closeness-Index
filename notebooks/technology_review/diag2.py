import pandas as pd, numpy as np
pd.set_option('display.width',220); pd.set_option('display.max_columns',30); pd.set_option('display.max_rows',200)
o=pd.read_csv('data/processed/technology_trade_orientation.csv')
c=pd.read_csv('data/processed/technology_trade_components.csv',dtype={'hs_code':str})
m=c.dropna(subset=['china_imports','us_imports']).copy()
def score(df, codes):
    d=df[df.hs_code.isin(codes)].groupby(['country_iso3','year'])[['us_imports','china_imports']].sum()
    return ((d.us_imports-d.china_imports)/(d.us_imports+d.china_imports)).rename('s')
# counterfactual diagnostics on COMPLETE country-years only (same basket for all)
comp=o[o.data_complete][['country_iso3','year','tech_orientation_score']].set_index(['country_iso3','year'])
alts={'all4':['8471','8517','8541','8542'],'excl8541':['8471','8517','8542'],'only8542':['8542'],'excl8471_8517':['8541','8542'],'only8471_8517':['8471','8517']}
res=pd.DataFrame({k:score(m,v) for k,v in alts.items()}).loc[comp.index]
print('== counterfactual scores, complete obs (n=%d)'%len(res))
print(res.describe().round(3).loc[['mean','25%','50%','75%']])
print('share negative:', (res<0).mean().round(3).to_dict())
d=(res.excl8541-res.all4); print('excl8541 - all4: mean %.3f median %.3f p90 %.3f max %.3f; n with |diff|>0.1: %d (%.1f%%)'%(d.mean(),d.median(),d.quantile(.9),d.max(),(d.abs()>0.1).sum(),100*(d.abs()>0.1).mean()))
r=res.reset_index().groupby('year')[['all4','excl8541','only8542']].median().round(3); print(r)
# category share of each country's China tech imports (complete obs)
mc=m.set_index(['country_iso3','year']).loc[comp.index].reset_index()
sh=mc.pivot_table(index=['country_iso3','year'],columns='hs_code',values='china_imports',aggfunc='sum')
sh=sh.div(sh.sum(1),axis=0)
print('\n== median share of China tech imports by HS (complete obs)'); print(sh.median().round(3))
shu=mc.pivot_table(index=['country_iso3','year'],columns='hs_code',values='us_imports',aggfunc='sum'); shu=shu.div(shu.sum(1),axis=0)
print('== median share of US tech imports by HS'); print(shu.median().round(3))
# 8541 rising China: value growth of 8541 China vs US
# partial baskets
p=o[o.data_status=='partial_basket']; cpl=o[o.data_status=='complete']
print('\n== partial vs complete')
for n,df in [('complete',cpl),('partial',p)]:
    x=df.tech_orientation_score; tot=df.china_tech_imports+df.us_tech_imports
    print(n,len(df),'median %.3f mean %.3f |s|>=0.95 %.1f%%  s>0 %.1f%%  median total US$m %.1f'%(x.median(),x.mean(),100*(x.abs()>=0.95).mean(),100*(x>0).mean(),tot.median()/1e6))
print('n_categories_matched:',p.n_categories_matched.value_counts().sort_index().to_dict())
# which categories missing and which side
pc=c.merge(p[['country_iso3','year']],on=['country_iso3','year'])
miss=pc[pc.china_imports.isna()|pc.us_imports.isna()]
print('missing cells by HS & side:'); print(pd.crosstab(miss.hs_code, np.where(miss.us_imports.isna()&miss.china_imports.isna(),'both',np.where(miss.us_imports.isna(),'US missing','China missing'))))
print('partial by year:',p.year.value_counts().sort_index().to_dict())
pt=p.groupby(['country_iso3','country']).size().sort_values(ascending=False); print('countries with partial:',len(pt)); print(pt.head(15).to_string())
# median total value of partial countries; overlap with small totals
print('\n== small denominators')
s=o.dropna(subset=['tech_orientation_score']).copy(); s['tot']=s.china_tech_imports+s.us_tech_imports
s['ext']=s.tech_orientation_score.abs()>=0.95
s['size']=pd.qcut(s.tot,5,labels=['Q1 smallest','Q2','Q3','Q4','Q5 largest'])
print(s.groupby('size',observed=True).agg(n=('ext','size'),median_tot_musd=('tot',lambda x:x.median()/1e6),share_extreme=('ext','mean'),median_score=('tech_orientation_score','median')).round(3))
print('scored with total < US$1m:',(s.tot<1e6).sum(),' of which extreme:',((s.tot<1e6)&s.ext).sum())
print('near -1 (<=-0.95):',(s.tech_orientation_score<=-0.95).sum(),' near +1:',(s.tech_orientation_score>=0.95).sum())
print(s[s.tech_orientation_score>=0.95][['country_iso3','country','year','us_tech_imports','china_tech_imports','tot','data_status']].assign(tot=lambda x:(x.tot/1e6).round(2)).to_string(index=False))
