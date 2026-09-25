COEF={'HIGH':1.0,'MEDIUM':.75,'LOW':.5}
def calculate(rows):
 totals={'beneficiaries':{},'losers':{}}
 # one highest-impact record per duplicate_group/stock/side prevents repeat-event inflation
 chosen={}
 for article in rows:
  for s in article['impacts']:
   group=article.get('duplicate_group') or str(article['article_id']); key=(s['side'],group,s['code'])
   value=article['importance']*s['impact']*COEF[article['confidence']]
   if key not in chosen or value>chosen[key][0]: chosen[key]=(value,article,s)
 for value,article,s in chosen.values():
  bucket=totals[s['side']].setdefault(s['code'],{'name':s['name'],'code':s['code'],'score':0,'articles':set(),'high':0,'reasons':[]})
  bucket['score'] += value if s['side']=='beneficiaries' else -value
  bucket['articles'].add(article['article_id']); bucket['high'] += article['confidence']=='HIGH'; bucket['reasons'].append(s['reason'])
 def rank(side):
  data=totals[side].values()
  return [dict(x, articles=len(x['articles']), reason=x['reasons'][0]) for x in sorted(data,key=lambda x:abs(x['score']),reverse=True)[:10]]
 return {'beneficiaries':rank('beneficiaries'),'losers':rank('losers')}
