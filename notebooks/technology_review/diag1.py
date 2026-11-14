import pandas as pd, numpy as np
pd.set_option('display.width',200); pd.set_option('display.max_columns',30)
o=pd.read_csv('data/processed/technology_trade_orientation.csv')
c=pd.read_csv('data/processed/technology_trade_components.csv',dtype={'hs_code':str})
cw=pd.read_csv('data/reference/comtrade_country_crosswalk.csv')
print(cw.mapping_method.value_counts()); print(cw[cw.comtrade_code.isin([490,842,156,251,699,757,579,344,458,704,410])])
s=o.dropna(subset=['tech_orientation_score'])
print('\n== overall score dist'); print(s.tech_orientation_score.describe().round(3))
print('share <0', (s.tech_orientation_score<0).mean().round(3), 'share <-0.5',(s.tech_orientation_score<-0.5).mean().round(3),'share >0',(s.tech_orientation_score>0).mean().round(3))
print('\n== by year');
print(s.groupby('year').tech_orientation_score.agg(['count','median','mean',lambda x:(x<0).mean(),lambda x:(x>0).sum(),lambda x:(x<=-0.95).sum(),lambda x:(x>=0.95).sum()]).round(3))
# complete only balanced panel
comp=o[o.data_complete]
print('\n== complete only by year'); print(comp.groupby('year').tech_orientation_score.agg(['count','median','mean']).round(3))
# value-weighted aggregate (all scored countries): world-level orientation
agg=s.groupby('year')[['us_tech_imports','china_tech_imports']].sum()
agg['agg_score']=(agg.us_tech_imports-agg.china_tech_imports)/(agg.us_tech_imports+agg.china_tech_imports)
agg['us_bn']=agg.us_tech_imports/1e9; agg['cn_bn']=agg.china_tech_imports/1e9
print('\n== pooled value-weighted'); print(agg[['us_bn','cn_bn','agg_score']].round(3))
# category
cs=c.dropna(subset=['category_orientation_score'])
print('\n== category score dist'); print(cs.groupby('hs_code').category_orientation_score.describe().round(3))
print(cs.groupby('hs_code').category_orientation_score.agg(neg=lambda x:(x<0).mean(),lt_m09=lambda x:(x<=-0.9).mean(),pos=lambda x:(x>0).mean()).round(3))
print('\n== category by year median'); print(cs.pivot_table(index='year',columns='hs_code',values='category_orientation_score',aggfunc='median').round(3))
# value composition among matched cells
m=c.dropna(subset=['china_imports','us_imports'])
v=m.groupby('hs_code')[['china_imports','us_imports']].sum()/1e9
v['cn_share_of_cn_total']=v.china_imports/v.china_imports.sum(); v['us_share_of_us_total']=v.us_imports/v.us_imports.sum()
v['pooled_score']=(v.us_imports-v.china_imports)/(v.us_imports+v.china_imports)
print('\n== value by HS (matched cells, all years, US$bn)'); print(v.round(3))
vy=m.groupby(['year','hs_code'])[['china_imports','us_imports']].sum().unstack()/1e9
print(vy.round(1))
