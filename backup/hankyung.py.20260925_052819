"""Public-feed collector. Never bypasses authentication or paywalls."""
from datetime import datetime, timezone
import httpx
from bs4 import BeautifulSoup
from app.scoring.rules import score, normalize, similar

RSS_URLS = ['https://www.hankyung.com/feed/economy','https://www.hankyung.com/feed/finance','https://www.hankyung.com/feed/industry']
async def collect(repo):
 seen={a['url'] for a in repo.articles()}; prior=[]; fetched=0
 async with httpx.AsyncClient(timeout=10, headers={'User-Agent':'stock50-7 public news collector'}) as client:
  for url in RSS_URLS:
   try:
    res=await client.get(url); res.raise_for_status(); soup=BeautifulSoup(res.text,'xml')
    for item in soup.select('item'):
     link=(item.findtext('link') or '').strip(); title=(item.findtext('title') or '').strip()
     if not link or not title or link in seen: continue
     snippet=(item.findtext('description') or '').strip(); group=next((str(i) for i,p in enumerate(prior) if similar(title,p)), normalize(title))
     points=score(title,snippet)
     repo.upsert_article({'source':'한국경제 RSS','title':title,'url':link,'published_at':item.findtext('pubDate'),'section':'경제/증권','snippet':snippet[:500],'content_excerpt':snippet[:1000],'importance_score':points,'duplicate_group':group,'is_candidate':int(points>0)})
     prior.append(title); seen.add(link); fetched+=1
   except (httpx.HTTPError, ValueError): continue
 repo.refresh_candidates(50)
 return fetched
