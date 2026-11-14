import pandas as pd, numpy as np
pd.set_option('display.width',250); pd.set_option('display.max_columns',40); pd.set_option('display.max_rows',300)
c=pd.read_csv('data/processed/technology_trade_components.csv',dtype={'hs_code':str})
o=pd.read_csv('data/processed/technology_trade_orientation.csv')
for iso in ['ISR','PHL','GTM','HUN','NLD','KOR','JPN','DEU','S19','MEX','CAN','AUS','MYS','VNM','HKG','SGP','GBR','IND']:
    x=c[c.country_iso3==iso].pivot_table(index='year',columns='hs_code',values='category_orientation_score').round(2)
    v=c[c.country_iso3==iso].assign(t=lambda d:(d.china_imports.fillna(0)+d.us_imports.fillna(0))).pivot_table(index='year',columns='hs_code',values='t',aggfunc='sum')
    sh=(v.div(v.sum(axis=1),axis=0)*100).round(0)
    print(f'\n### {iso} category scores | value share % of US+China total')
    print(pd.concat([x,sh.add_prefix('sh')],axis=1).loc[[y for y in [2014,2017,2019,2021,2022,2023,2024,2025] if y in x.index]].to_string())
# US 8471 rise 2024-25: which importers
u=c[(c.hs_code=='8471')&c.year.isin([2022,2023,2024,2025])].pivot_table(index='country_iso3',columns='year',values='us_imports',aggfunc='sum')/1e9
u['d']=u[2025]-u[2022]; print('\nUS 8471 imports change 2022->2025 (US$bn)'); print(u.sort_values('d',ascending=False).head(8).round(2))
u=c[(c.hs_code=='8542')&c.year.isin([2022,2025])].pivot_table(index='country_iso3',columns='year',values='us_imports',aggfunc='sum')/1e9
u['d']=u[2025]-u[2022]; print('\nUS 8542 change 2022->2025'); print(u.sort_values('d').head(8).round(2))
# HKG weight in pooled totals
s=o.dropna(subset=['tech_orientation_score'])
print('\nHKG share of pooled China tech imports by year:', (s[s.country_iso3=='HKG'].set_index('year').china_tech_imports/s.groupby('year').china_tech_imports.sum()).round(2).to_dict())
# positive-score countries (latest complete year avg 2022-2024)
r=o[o.data_complete&o.year.between(2022,2024)].groupby(['country_iso3','country']).agg(score=('tech_orientation_score','mean'),tot=('china_tech_imports',lambda x: np.nan)).score
print('\nmean 2022-24 complete >0:'); print(r[r>0].sort_values(ascending=False).round(2).to_string())
print('n countries with 2022-24 complete obs:',len(r),' share <0:',(r<0).mean().round(3), ' share <-0.5:',(r<-0.5).mean().round(3))
# 8541 China value growth
v=c.groupby(['year','hs_code']).china_imports.sum().unstack()/1e9; print('\nChina exports to reporters by HS (US$bn, reported, all reporters incl. partial)'); print(v.round(1))
