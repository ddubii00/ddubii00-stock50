import json, re

CONF={'HIGH','MEDIUM','LOW'}
def strip_fence(text):
 return re.sub(r'^\s*```(?:json)?\s*|\s*```\s*$','',text.strip(),flags=re.I)
def validate(raw, article_ids, universe):
 try: data=json.loads(strip_fence(raw))
 except json.JSONDecodeError as e: raise ValueError(f'JSON 문법 오류: {e.msg}')
 if not isinstance(data,dict) or not isinstance(data.get('articles'),list): raise ValueError('articles 배열이 필요합니다.')
 if len(data['articles'])>20: raise ValueError('articles는 최대 20개입니다.')
 names={}
 for stock in universe: names.setdefault(stock['name'],[]).append(stock)
 codes={x['code']:x for x in universe}; seen_ids=set(); seen_stocks=set()
 for a in data['articles']:
  aid=a.get('article_id')
  if aid not in article_ids: raise ValueError(f'기사 ID {aid}: 실제 존재하지 않는 article_id입니다.')
  if aid in seen_ids: raise ValueError(f'기사 ID {aid}: 중복 article_id입니다.')
  seen_ids.add(aid)
  if not isinstance(a.get('summary'),list) or len(a['summary'])!=3: raise ValueError(f'기사 ID {aid}: summary는 정확히 3개여야 합니다.')
  if not isinstance(a.get('importance'),int) or not 1<=a['importance']<=5: raise ValueError(f'기사 ID {aid}: importance는 1~5 정수여야 합니다.')
  if a.get('confidence') not in CONF: raise ValueError(f'기사 ID {aid}: confidence는 HIGH/MEDIUM/LOW여야 합니다.')
  for side in ('beneficiaries','losers'):
   stocks=a.get(side,[])
   if not isinstance(stocks,list) or len(stocks)>3: raise ValueError(f'기사 ID {aid}: {side}는 0~3개여야 합니다.')
   for s in stocks:
    code=s.get('code'); name=s.get('name')
    if not code and name in names and len(names[name])==1: s['code']=code=names[name][0]['code']; s.setdefault('market',names[name][0]['market'])
    ref=codes.get(code)
    if not ref: raise ValueError(f'기사 ID {aid}: 잘못된 종목코드 {code}')
    if name != ref['name']: raise ValueError(f'기사 ID {aid}: name/code가 서로 다른 회사입니다.')
    if not isinstance(s.get('impact'),int) or not 1<=s['impact']<=5: raise ValueError(f'기사 ID {aid}: {name} impact는 1~5 정수여야 합니다.')
    key=(aid,code)
    if key in seen_stocks: raise ValueError(f'기사 ID {aid}: 중복 종목 {name}')
    seen_stocks.add(key)
 return data
