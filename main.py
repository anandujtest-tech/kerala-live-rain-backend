"""Kerala Live Rain: fail-closed IMD adapters. Never invent measurements."""
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from datetime import datetime, timezone, timedelta
from typing import Any
import asyncio, httpx, time
app=FastAPI(title="Kerala Live Rain",version="0.3-diagnostics")
BASE="https://api.imd.gov.in/api/v1/"
DISTRICTS=["Thiruvananthapuram","Kollam","Pathanamthitta","Alappuzha","Kottayam","Idukki","Ernakulam","Thrissur","Palakkad","Malappuram","Kozhikode","Wayanad","Kannur","Kasaragod"]
ENDPOINTS={"aws":"aws_data?sid=4","mapping":"aws_data_mapping","current":"current_wx","rainfall":"districtrainfall","nowcast":"districtnowcast","warning":"districtwarning"}
cache={}
def now():return datetime.now(timezone.utc).isoformat()
async def fetch(key):
    t=time.monotonic()
    if key in cache and t-cache[key][0]<600:return cache[key][1]
    try:
        async with httpx.AsyncClient(timeout=12,follow_redirects=True) as client:
            response=await client.get(BASE+ENDPOINTS[key],headers={"Accept":"application/json","User-Agent":"KeralaLiveRain/0.1"})
            response.raise_for_status()
            data=response.json()
        value={"available":True,"retrieved_at":now(),"data":data,"error":None}
    except Exception as ex:value={"available":False,"retrieved_at":now(),"data":None,"error":type(ex).__name__+": "+str(ex)[:160]}
    cache[key]=(t,value);return value

def records(obj:Any):
    if isinstance(obj,list):return obj
    if isinstance(obj,dict):
        for key in ("data","Data","records","result","results","stations"):
            if isinstance(obj.get(key),list):return obj[key]
    return []
def find(row,*names):
    if not isinstance(row,dict):return None
    norm={str(k).lower().replace(" ","").replace("_",""):v for k,v in row.items()}
    for name in names:
        v=norm.get(name.lower().replace(" ","").replace("_",""))
        if v is not None and str(v).strip() not in ("","--","NA","null"):return v
    return None
def safe_rain(value):
    """Keep only finite, non-negative numeric totals; never infer current rain."""
    import math
    try:
        n=float(str(value).strip())
        return round(n,2) if math.isfinite(n) and n>=0 else None
    except (TypeError, ValueError):
        return None

@app.get('/api/health')
async def health():return {"ok":True,"time_utc":now(),"prototype":True,"source_validation_required":True}
@app.get('/api/kerala/sources/status')
async def sources():
    vals=await asyncio.gather(*(fetch(k) for k in ENDPOINTS))
    return {"sources":{k:{"available":v["available"],"retrieved_at":v["retrieved_at"],"error":v["error"],"record_count":len(records(v["data"])) if v["available"] else 0,"schema_keys":list(v["data"][0].keys())[:35] if isinstance(v["data"],list) and v["data"] and isinstance(v["data"][0],dict) else list(v["data"].keys())[:35] if isinstance(v["data"],dict) else []} for k,v in zip(ENDPOINTS,vals)}}
@app.get('/api/kerala/stations')
async def stations():
    a=await fetch("aws");return {"source":"IMD AWS/ARG","retrieved_at":a["retrieved_at"],"available":a["available"],"records_unverified":records(a["data"]),"note":"Raw records; fields and Kerala mapping require verification; not proof of current rainfall."} if a["available"] else {"available":False,"stations":[],"error":a["error"]}
@app.get('/api/kerala/rain/live')
async def live():
    # Current rain markers intentionally absent until IMD weather code + observation UTC mapping are validated.
    a=await fetch('current')
    return {"observed_rain":[],"status":"unverified_source_schema" if a["available"] else "unavailable","source":"IMD current weather","retrieved_at":a["retrieved_at"],"message":"No current-rain symbols emitted without validated code, location and timestamp. Empty does not mean dry."}
@app.get('/api/kerala/districts')
async def districts():
    a=await fetch('rainfall')
    out=[]
    for name in DISTRICTS:
        matched=next((r for r in records(a['data']) if str(find(r,'District','District Name','DistrictName') or '').strip().lower()==name.lower()),None)
        out.append({"name":name,"status":"Accumulated rainfall (not current rain)" if matched and safe_rain(find(matched,'Daily Actual','DailyActual','Actual')) is not None else "No verified observation available","source":"IMD district rainfall" if matched else "Unavailable","observation_time":str(find(matched,'Date','Daily Date') or 'Unavailable'),"rainfall_24h_mm":safe_rain(find(matched,'Daily Actual','DailyActual','Actual')) if matched else None,"measurement_period":"Daily total (source period must be checked)" if matched else None})
    return {"districts":out,"retrieved_at":a['retrieved_at'],"source_available":a['available'],"note":"District accumulated totals are not live rain observations."}
@app.get('/api/kerala/districts/{district_id}')
async def district(district_id:str):
    data=await districts()
    return next((d for d in data['districts'] if d['name'].lower()==district_id.lower()),JSONResponse(status_code=404,content={'error':'Unknown district'}))
@app.get('/api/kerala/alerts')
async def alerts():
    a,b=await asyncio.gather(fetch('nowcast'),fetch('warning'))
    # Don't display expired or mismapped alerts without validated source timestamps/severity.
    return {"alerts":[],"status":"pending_alert_schema_validation" if a['available'] or b['available'] else "unavailable","sources":{"nowcast":a['available'],"districtwarning":b['available']},"message":"Alerts are withheld until validity and district mappings can be verified. Check official IMD/NDMA warnings."}
@app.get('/api/kerala/rain/history')
async def history():return {"observations":[],"status":"not_configured","note":"Persistent database and historical ingestion not yet configured."}

@app.get('/api/kerala/diagnostics')
async def diagnostics():
    """Source reachability and structure, without leaking raw station records."""
    result=await sources()
    return {"backend_version":"0.3-diagnostics","sources":result["sources"],"note":"Source availability does not establish schema validation or current rainfall. Empty warnings and markers are not evidence of no rain or no alerts."}
