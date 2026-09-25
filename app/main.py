import os
from datetime import datetime, timezone
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from app.db.repository import Repository
from app.collector.hankyung import collect
from app.ai.schema import validate
from app.services.top10 import calculate

BASE='/stock50-7'; repo=Repository(os.getenv('DATABASE_PATH','data/stock50.db')); repo.init()
app=FastAPI(title='stock50-7', root_path=BASE)
app.mount('/static',StaticFiles(directory='frontend'),name='static')
class RawAnalysis(BaseModel): raw: str
@app.get('/health')
def health(): return {'status':'ok','provider':'manual'}
@app.get('/')
def index(): return FileResponse('frontend/index.html')
@app.get('/api/state')
def state():
 arts=repo.articles(); snaps=repo.snapshots()
 return {'articles':arts,'candidates':[a for a in arts if a['is_candidate']],'snapshots':snaps,'latest': snapshot(snaps[0]['id']) if snaps else None}
@app.post('/api/collect')
async def run_collect(): return {'fetched':await collect(repo),'articles':len(repo.articles())}
@app.get('/api/prompt')
def prompt(ids:str=''):
 selected={int(x) for x in ids.split(',') if x.isdigit()} if ids else {a['id'] for a in repo.candidates()[:50]}
 articles=[a for a in repo.articles() if a['id'] in selected]
 body='\n\n'.join(f"[기사 {i+1}]\narticle_id: {a['id']}\n제목: {a['title']}\n시간: {a['published_at']}\n섹션: {a['section']}\nURL: {a['url']}\n내용: {a['snippet']}" for i,a in enumerate(articles))
 instruction='''stock50-7 한국경제 뉴스 AI 분석\n반드시 JSON만 반환하세요. 시장 영향도 높은 기사 최대 20개를 선택하고 동일 사건은 하나로 인식하세요. 각 기사 summary는 정확히 3개, importance와 종목 impact는 1~5 정수, confidence는 HIGH/MEDIUM/LOW, beneficiaries/losers는 각 최대 3개입니다. 한국 상장주만 선택하세요.\n형식: {"analysis_time":"ISO8601","articles":[{"article_id":1,"title":"...","importance":5,"confidence":"HIGH","summary":["...","...","..."],"beneficiaries":[{"name":"SK하이닉스","code":"000660","market":"KOSPI","impact":5,"reason":"..."}],"losers":[]}]}\n\n기사 후보\n'''
 return {'text':instruction+body}
@app.post('/api/analysis/validate')
def check(body:RawAnalysis):
 try: return {'valid':True,'data':validate(body.raw,{a['id'] for a in repo.articles()},repo.universe())}
 except ValueError as e: raise HTTPException(422,str(e))
@app.post('/api/analysis/save')
def save(body:RawAnalysis):
 try: payload=validate(body.raw,{a['id'] for a in repo.articles()},repo.universe()); return {'id':repo.save_analysis(payload)}
 except ValueError as e: raise HTTPException(422,str(e))
@app.get('/api/snapshot/{aid}')
def snapshot(aid:int):
 rows=repo.snapshot(aid)
 if not rows: raise HTTPException(404,'Snapshot을 찾을 수 없습니다.')
 # duplicate group comes from source article for aggregation
 all_articles={a['id']:a for a in repo.articles()}
 for x in rows: x['duplicate_group']=all_articles[x['article_id']]['duplicate_group']
 return {'articles':rows,'top10':calculate(rows)}
