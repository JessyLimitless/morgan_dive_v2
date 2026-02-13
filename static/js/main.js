/* ═══════════════ Data Guide Toggle ═══════════════ */
function toggleGuide(id){
  var panel=document.getElementById(id);
  if(!panel)return;
  document.querySelectorAll('.guide-panel.open').forEach(function(p){
    if(p.id!==id)p.classList.remove('open');
  });
  panel.classList.toggle('open');
}

/* ═══════════════════════════════════════════════════════
   AX RADAR v5.3 — Data Engine
   ═══════════════════════════════════════════════════════ */
(function(){
'use strict';

const REFRESH = parseInt(document.body.dataset.refreshInterval, 10) || 30000;
let timer = null;

/* ── Sector Tab State ── */
let sectorTabMode = 'foreign'; // 'foreign' | 'inst'
let sectorFlowData = null;

/* ── API Layer ── */
const API = {
  _cache: {},
  async _f(url, retries=1){
    for(let i=0;i<=retries;i++){
      try{
        if(i>0) await new Promise(r=>setTimeout(r,1000));
        const r=await fetch(url);
        if(!r.ok){if(i<retries)continue;throw new Error('HTTP '+r.status)}
        const j=await r.json();
        if(j.status!=='ok'){if(i<retries)continue;throw new Error(j.message||'API error')}
        this._cache[url]=j.data;
        return j.data;
      }catch(e){
        if(i>=retries){if(this._cache[url])return this._cache[url];throw e}
      }
    }
  },
  indices()    {return this._f('/api/v3/indices')},
  inst()       {return this._f('/api/v3/institutions')},
  stock(c)     {return this._f('/api/v3/stock/'+c)},
  foreignTop() {return this._f('/api/v3/foreign-top')},
  foreignSector(){return this._f('/api/v3/foreign-sector')},
  accumulation(){return this._f('/api/v3/accumulation')},
  consecutiveBuy(){return this._f('/api/v3/consecutive-buy')},
  programTop(){return this._f('/api/v3/program-top')},
};

/* ── Splash ── */
function splashMsg(txt){var el=document.getElementById('splashStatus');if(el)el.textContent=txt}
function dismissSplash(){
  var el=document.getElementById('splash');
  if(!el||el.classList.contains('fade-out'))return;
  el.classList.add('fade-out');
  setTimeout(function(){el.style.display='none'},700);
}

/* ── Init ── */
document.addEventListener('DOMContentLoaded',()=>{
  loadAllInitial();
  timer=setInterval(loadAll,REFRESH);
  document.getElementById('mo').addEventListener('click',e=>{if(e.target.id==='mo')closeMo()});
  document.getElementById('mo-x').addEventListener('click',closeMo);
  document.getElementById('sellOverlay').addEventListener('click',e=>{if(e.target.id==='sellOverlay')closeSellPopup()});
  document.getElementById('sellPopClose').addEventListener('click',closeSellPopup);
  document.addEventListener('keydown',e=>{if(e.key==='Escape'){closeMo();closeSellPopup()}});
});

async function loadAllInitial(){
  clock();
  splashMsg('Loading market indices...');
  var p1=loadIdx().then(function(){splashMsg('Loading accumulation data...')});
  var p2=loadForeignTop();
  var p3=loadSectorFlow();
  var p4=loadInst();
  var p5=loadAccumulation();
  var p6=loadProgramTop();
  var p7=loadConsecutiveBuy();
  try{await Promise.all([p1,p2,p3,p4,p5,p6,p7])}catch(e){}
  dismissSplash();
}

function loadAll(){
  clock();
  loadIdx();
  loadForeignTop();
  loadSectorFlow();
  loadInst();
  loadAccumulation();
  loadProgramTop();
  loadConsecutiveBuy();
}

function clock(){
  const d=new Date(),p=n=>String(n).padStart(2,'0');
  const el=document.getElementById('clock');
  if(el) el.textContent=p(d.getHours())+':'+p(d.getMinutes())+':'+p(d.getSeconds());
}

/* ── Formatting ── */
function fNum(n){if(n==null)return'-';return Number(n).toLocaleString('ko-KR')}
function fAmt(n){
  if(!n)return'0';
  const a=Math.abs(n),s=n<0?'-':'+';
  if(a>=10000)return s+(a/10000).toFixed(1)+'\uC870';
  if(a>=1)return s+Math.round(a).toLocaleString('ko-KR')+'\uC5B5';
  return s+(a*1000).toFixed(0)+'\uBC31\uB9CC';
}
function fCap(n){
  if(!n)return'-';
  const a=Math.abs(n);
  if(a>=10000)return(a/10000).toFixed(1)+'\uC870';
  return a.toLocaleString('ko-KR')+'\uC5B5';
}
function sigCls(sig){const s=String(sig);return['1','2'].includes(s)?'up':['4','5'].includes(s)?'dn':'fl'}
function sigArrow(sig){const s=String(sig);return['1','2'].includes(s)?'\u25B2':['4','5'].includes(s)?'\u25BC':''}


/* ═══════════════ Market Pulse — Indices ═══════════════ */
async function loadIdx(){
  try{
    const d=await API.indices();
    ['KOSPI','KOSDAQ','NASDAQ'].forEach(k=>{
      const idx=d[k];
      if(!idx)return;
      const card=document.getElementById('idx-'+k);
      const valEl=document.getElementById('idx-'+k+'-val');
      const chgEl=document.getElementById('idx-'+k+'-chg');
      const pctEl=document.getElementById('idx-'+k+'-pct');
      if(!valEl)return;

      const val=typeof idx.value==='number'?idx.value:0;
      const chg=typeof idx.change==='number'?idx.change:0;
      const pct=typeof idx.changePct==='number'?idx.changePct:0;
      const cls=chg>0?'up':chg<0?'dn':'fl';
      const arrow=chg>0?'\u25B2':chg<0?'\u25BC':'';

      valEl.textContent=val.toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2});

      if(card){
        card.classList.remove('state-up','state-dn','state-fl');
        card.classList.add('state-'+cls);
      }
      if(chgEl){
        chgEl.className='idx-hero__chg '+cls;
        chgEl.textContent=arrow+(chg>0?' +':' ')+chg.toFixed(2);
      }
      if(pctEl){
        pctEl.className='idx-hero__pct '+cls;
        pctEl.textContent=(pct>0?'+':'')+pct.toFixed(2)+'%';
      }
    });
  }catch(e){
    console.error('loadIdx',e);
  }
}



/* ═══════════════ Foreign Flow TOP 5 ═══════════════ */
async function loadForeignTop(){
  try{
    const d=await API.foreignTop();
    const buyList=(d.buy||[]).slice(0,5);
    const sellList=(d.sell||[]).slice(0,5);
    rForeignList('foreignBuy',buyList,'buy');
    rForeignList('foreignSell',sellList,'sell');
    const bc=document.getElementById('fbCnt');
    const sc=document.getElementById('fsCnt');
    if(bc)bc.textContent=buyList.length+' stocks';
    if(sc)sc.textContent=sellList.length+' stocks';
  }catch(e){
    console.error('foreignTop',e);
    const fb=document.getElementById('foreignBuy');
    const fs=document.getElementById('foreignSell');
    if(fb)fb.innerHTML='<div class="no-data">데이터를 불러올 수 없습니다</div>';
    if(fs)fs.innerHTML='<div class="no-data">데이터를 불러올 수 없습니다</div>';
  }
}
function rForeignList(id,items,type){
  const el=document.getElementById(id);if(!el)return;
  if(!items.length){el.innerHTML='<div class="empty-txt">No data</div>';return}
  /* 1위 금액 = 바 100%, 나머지는 비례 */
  const maxAmt=Math.abs(items[0].amount)||1;
  const clr=type==='buy'?'220,38,38':'37,99,235';
  el.innerHTML=items.map((s,i)=>{
    const a=Math.abs(s.amount);
    const v=a>=10000?(a/10000).toFixed(1)+'\uC870':a.toLocaleString('ko-KR')+'\uC5B5';
    const pfx=type==='buy'?'+':'-';
    const rkCls=i===0?'fi-rk-1':i===1?'fi-rk-2':i===2?'fi-rk-3':'';
    const p=s.changePct||0;
    const pc=p>0?'up':p<0?'dn':'fl';
    const chgStr=(p>0?'+':'')+p.toFixed(1)+'%';
    const barPct=Math.min(100,Math.round(a/maxAmt*100));
    return'<div class="fi-item" onclick="openMo(\''+s.code+'\')">'
      +'<span class="fi-rk '+rkCls+'">'+(i+1)+'</span>'
      +'<span class="fi-nm">'+s.name+'</span>'
      +'<span class="fi-bar-wrap"><span class="fi-fill" style="width:'+barPct+'%;background:rgb('+clr+')"></span></span>'
      +'<span class="fi-chg '+pc+'">'+chgStr+'</span>'
      +'<span class="fi-amt '+type+'">'+pfx+v+'</span>'
    +'</div>';
  }).join('');
}


/* ═══════════════ Sector Flow — Diverging Bar Chart (tabbed) ═══════════════ */
window.switchSectorTab=function(mode){
  sectorTabMode=mode;
  document.querySelectorAll('.sector-tab').forEach(function(t){
    t.classList.toggle('active',t.getAttribute('data-tab')===mode);
  });
  if(sectorFlowData) renderSectorChart(sectorFlowData);
};

async function loadSectorFlow(){
  try{
    const d=await API.foreignSector();
    sectorFlowData=d||[];
    renderSectorChart(sectorFlowData);
  }catch(e){
    console.error('sectorFlow',e);
    const el=document.getElementById('sectorChart');
    if(el)el.innerHTML='<div class="no-data">데이터를 불러올 수 없습니다</div>';
  }
}
function renderSectorChart(items){
  const el=document.getElementById('sectorChart');
  if(!el)return;
  if(!items.length){el.innerHTML='<div class="empty-txt">No data</div>';return}

  /* Pick amount field based on tab */
  const isForeign=sectorTabMode==='foreign';
  const amtKey=isForeign?'foreignAmt':'instAmt';
  const label=isForeign?'Foreign':'Institution';

  /* Sort by selected amount */
  const sorted=items.slice().sort(function(a,b){return (b[amtKey]||0)-(a[amtKey]||0)});
  const maxAmt=Math.max(...sorted.map(function(s){return Math.abs(s[amtKey]||0)}))||1;

  let html='';
  /* Header row */
  html+='<div class="sector-header-row">';
  html+='<div class="sector-nm">업종</div>';
  html+='<div class="sector-bar-wrap">';
  html+='<div class="sector-bar-left">\u25C0 NET SELL</div>';
  html+='<div class="sector-axis"></div>';
  html+='<div class="sector-bar-right">NET BUY \u25B6</div>';
  html+='</div>';
  html+='<div class="sector-amt">금액</div>';
  html+='</div>';

  sorted.forEach(function(s){
    const amt=s[amtKey]||0;
    const pct=Math.round(Math.abs(amt)/maxAmt*100);
    const isBuy=amt>0;
    const isZero=amt===0;
    const cls=isZero?'zero':(isBuy?'buy':'sell');
    const sign=isBuy?'+':'';
    const absAmt=Math.abs(amt);
    const dispAmt=absAmt>=10000?(absAmt/10000).toFixed(1)+'\uC870':absAmt.toLocaleString('ko-KR')+'\uC5B5';

    html+='<div class="sector-row">';
    html+='<div class="sector-nm">'+s.sector+'</div>';
    html+='<div class="sector-bar-wrap">';
    html+='<div class="sector-bar-left">';
    if(!isBuy&&!isZero) html+='<div class="sector-bar sell" style="width:'+pct+'%"></div>';
    html+='</div>';
    html+='<div class="sector-axis"></div>';
    html+='<div class="sector-bar-right">';
    if(isBuy) html+='<div class="sector-bar buy" style="width:'+pct+'%"></div>';
    html+='</div>';
    html+='</div>';
    html+='<div class="sector-amt '+cls+'">'+sign+dispAmt+'</div>';
    html+='</div>';
  });

  el.innerHTML=html;
}


/* ═══════════════ Program Trading TOP ═══════════════ */
var _progData=null;
var _progShowAll=false;

async function loadProgramTop(){
  try{
    var d=await API.programTop();
    _progData=d||[];
    renderProgramTop(_progData);
  }catch(e){
    console.error('programTop',e);
    var el=document.getElementById('progBody');
    if(el)el.innerHTML='<tr><td colspan="6" style="text-align:center;color:var(--tx-3);padding:32px">데이터를 불러올 수 없습니다</td></tr>';
  }
}

function renderProgramTop(items){
  var el=document.getElementById('progBody');
  if(!el)return;
  var show=_progShowAll?50:5;
  var list=items.slice(0,show);
  if(!list.length){
    el.innerHTML='<tr><td colspan="6" style="text-align:center;color:var(--tx-3);padding:32px">No data</td></tr>';
    return;
  }
  el.innerHTML=list.map(function(s){
    var net=s.prm_netprps_amt||0;
    var netCls=net>=0?'buy':'sell';
    var absNet=Math.abs(net);
    /* 백만원 단위 → 억원 변환 */
    var netDisp=absNet>=100?(absNet/100).toFixed(0)+'억':absNet+'백만';
    var netSign=net>=0?'+':'-';
    var flu=s.flu_rt||0;
    var fluCls=flu>0?'up':flu<0?'dn':'fl';
    var mkt=(s.market||'').toLowerCase();
    return '<tr onclick="openMo(\''+s.stk_cd+'\')">'
      +'<td>'+s.rank+'</td>'
      +'<td class="p-nm">'+s.stk_nm+'</td>'
      +'<td><span class="p-mkt '+mkt+'">'+s.market+'</span></td>'
      +'<td class="p-prc">'+fNum(s.cur_prc)+'</td>'
      +'<td class="'+fluCls+'">'+(flu>0?'+':'')+flu.toFixed(2)+'%</td>'
      +'<td class="p-net '+netCls+'">'+netSign+netDisp+'</td>'
    +'</tr>';
  }).join('');
  /* Toggle button */
  var btn=document.getElementById('progToggle');
  if(btn){
    if(items.length<=5){btn.style.display='none'}
    else{
      btn.style.display='block';
      btn.textContent=_progShowAll?'접기 \u25B2':'더보기 \u25BC ('+items.length+'종목)';
    }
  }
}

window.toggleProg=function(){
  _progShowAll=!_progShowAll;
  if(_progData)renderProgramTop(_progData);
};


/* ═══════════════ Stealth Accumulation ═══════════════ */
var _accumData=[];

async function loadAccumulation(){
  try{
    var d=await API.accumulation();
    if(!d||!d.length){
      document.getElementById('accumCards').innerHTML='<div class="stealth-empty">No data</div>';
      return;
    }
    _accumData=d;
    renderAccumCards(d.slice(0,5));
    renderWeightTop(d);
  }catch(e){
    console.error('accumulation',e);
    document.getElementById('accumCards').innerHTML='<div class="stealth-empty">데이터를 불러올 수 없습니다</div>';
  }
}

function renderWeightTop(items){
  var el=document.getElementById('weightTopBody');
  if(!el)return;
  var sorted=items.slice().sort(function(a,b){return(b.wght_change_5d||0)-(a.wght_change_5d||0)});
  var top10=sorted.slice(0,10);
  if(!top10.length){
    el.innerHTML='<tr><td colspan="7" style="text-align:center;color:#64748B;padding:32px">No data</td></tr>';
    return;
  }
  el.innerHTML=top10.map(function(s,i){
    var c5=s.wght_change_5d||0,c20=s.wght_change_20d||0;
    var c5cls=c5>=0?'tbl-pos':'tbl-neg';
    var c20cls=c20>=0?'tbl-pos':'tbl-neg';
    var exh=s.exh_rt_incrs||0;
    var exhCls=exh>=0?'tbl-pos':'tbl-neg';
    var wght=s.wght_now||0;
    return '<tr onclick="openMo(\''+s.stk_cd+'\')">'
      +'<td>'+(i+1)+'</td>'
      +'<td class="tbl-nm">'+s.stk_nm+'</td>'
      +'<td>'+wght.toFixed(2)+'</td>'
      +'<td class="'+c5cls+'">'+(c5>=0?'+':'')+c5+'%p</td>'
      +'<td class="'+c20cls+'">'+(c20>=0?'+':'')+c20+'%p</td>'
      +'<td class="'+exhCls+'">'+(exh>=0?'+':'')+exh+'%p</td>'
      +'<td><span class="accum-sparkline mini-spark" data-values="'+(s.sparkline||[]).join(',')+'"></span></td>'
    +'</tr>';
  }).join('');
  setTimeout(function(){
    el.querySelectorAll('.accum-sparkline').forEach(drawAccumSparkline);
  },100);
}

/* ═══════════════ Consecutive Buy TOP (ka10035) ═══════════════ */
async function loadConsecutiveBuy(){
  try{
    var d=await API.consecutiveBuy();
    renderConsecTop(d||[]);
  }catch(e){
    console.error('consecutiveBuy',e);
    var el=document.getElementById('consecTopBody');
    if(el)el.innerHTML='<tr><td colspan="7" style="text-align:center;color:#64748B;padding:32px">\uB370\uC774\uD130\uB97C \uBD88\uB7EC\uC62C \uC218 \uC5C6\uC2B5\uB2C8\uB2E4</td></tr>';
  }
}

function renderConsecTop(items){
  var el=document.getElementById('consecTopBody');
  if(!el)return;
  var top10=items.slice(0,10);
  if(!top10.length){
    el.innerHTML='<tr><td colspan="7" style="text-align:center;color:#64748B;padding:32px">No data</td></tr>';
    return;
  }
  el.innerHTML=top10.map(function(s,i){
    var tot=s.tot||0;
    var totCls=tot>0?'tbl-pos':tot<0?'tbl-neg':'tbl-zero';
    /* D-1,D-2,D-3 순매수량 — 천주 단위를 만주로 변환해서 표시 */
    function fQty(v){
      if(!v)return'-';
      var a=Math.abs(v);
      return(v>0?'+':'-')+(a>=1000?(a/1000).toFixed(0)+'천':a.toLocaleString('ko-KR'));
    }
    return '<tr onclick="openMo(\''+s.stk_cd+'\')">'
      +'<td>'+s.rank+'</td>'
      +'<td class="tbl-nm">'+s.stk_nm+'</td>'
      +'<td>'+fNum(s.cur_prc)+'</td>'
      +'<td class="tbl-pos">'+fQty(s.dm1)+'</td>'
      +'<td class="tbl-pos">'+fQty(s.dm2)+'</td>'
      +'<td class="tbl-pos">'+fQty(s.dm3)+'</td>'
      +'<td class="'+totCls+'">'+fQty(s.tot)+'</td>'
    +'</tr>';
  }).join('');
}

function renderAccumCards(items){
  var el=document.getElementById('accumCards');
  if(!el)return;
  el.innerHTML=items.map(function(s){
    var g=s.grade.toLowerCase();
    var c5=s.wght_change_5d,c20=s.wght_change_20d;
    var c5cls=c5>=0?'pos':'neg',c20cls=c20>=0?'pos':'neg';
    var sigCls=s.signal.toLowerCase();
    return '<div class="accum-card" data-grade="'+s.grade+'" onclick="openMo(\''+s.stk_cd+'\')">'
      +'<div class="accum-card__hd">'
        +'<span class="accum-grade grade-'+g+'">'+s.grade+'</span>'
        +'<span class="accum-card__nm">'+s.stk_nm+'</span>'
      +'</div>'
      +'<div class="accum-card__score">'+s.accumulation_score+'</div>'
      +'<div class="accum-card__score-lbl">Accumulation Score</div>'
      +'<div class="accum-sparkline" data-values="'+(s.sparkline||[]).join(',')+'"></div>'
      +'<div class="accum-card__chg">'
        +'<span><span class="lbl">5D</span><span class="'+c5cls+'">'+(c5>=0?'+':'')+c5+'%p</span></span>'
        +'<span><span class="lbl">20D</span><span class="'+c20cls+'">'+(c20>=0?'+':'')+c20+'%p</span></span>'
      +'</div>'
      +'<div class="accum-signal '+sigCls+'">'+s.signal.replace(/_/g,' ')+'</div>'
    +'</div>';
  }).join('');
  /* Draw sparklines — use setTimeout to ensure layout is complete */
  setTimeout(function(){
    el.querySelectorAll('.accum-sparkline').forEach(drawAccumSparkline);
  },100);
}

function drawAccumSparkline(el){
  var raw=el.dataset.values;
  if(!raw)return;
  var values=raw.split(',').map(Number).filter(function(v){return !isNaN(v)});
  if(values.length<2)return;

  var isMini=el.classList.contains('mini-spark');
  var w=isMini?80:160;
  var h=isMini?24:36;
  var pad=3;
  var mn=Math.min.apply(null,values),mx=Math.max.apply(null,values);
  var range=mx-mn||1;

  var pts=values.map(function(v,i){
    var x=Math.round((i/(values.length-1))*w*10)/10;
    var y=Math.round((h-pad-((v-mn)/range)*(h-pad*2))*10)/10;
    return x+','+y;
  });

  var polyPts=pts.join(' ');
  var fillPts=polyPts+' '+w+','+h+' 0,'+h;

  el.innerHTML='<svg viewBox="0 0 '+w+' '+h+'" preserveAspectRatio="none" width="100%" height="100%">'
    +'<polygon points="'+fillPts+'"/>'
    +'<polyline points="'+polyPts+'"/>'
    +'</svg>';
}


/* ═══════════════ Institutions (5D buy + sell ranking) ═══════════════ */
const sellDataStore={};
const IB_META={
  MS:{name:'Morgan Stanley',cls:'ms'},
  JP:{name:'JP Morgan',cls:'jp'},
  GS:{name:'Goldman Sachs',cls:'gs'}
};

async function loadInst(){
  try{
    const d=await API.inst();
    if(!d){throw new Error('No data')}
    ['MS','JP','GS'].forEach(k=>{
      const inst=d[k];
      const el=document.getElementById(k+'-col');
      if(!el)return;
      if(!inst||(!((inst.buyTop||[]).length) && !((inst.sellTop||[]).length))){
        el.innerHTML='<div class="no-data">데이터 없음</div>';
        return;
      }
      /* Store sell data for popup */
      sellDataStore[k]=inst.sellTop||[];
      let html='';
      /* BUY section only */
      html+='<div class="ib-sub-hd buy">Net Buy TOP 5</div>';
      html+=rInstItems(inst.buyTop||[],false);
      /* Sell toggle button */
      const sellCnt=(inst.sellTop||[]).length;
      if(sellCnt>0){
        html+='<div class="sell-toggle-btn" onclick="openSellPopup(\''+k+'\')">'
          +'<span class="arrow">\u25BC</span> NET SELL TOP '+sellCnt+' 보기'
          +'</div>';
      }
      el.innerHTML=html;
    });
  }catch(e){
    console.error('inst',e);
    ['MS-col','JP-col','GS-col'].forEach(id=>{
      const el=document.getElementById(id);
      if(el)el.innerHTML='<div class="no-data">데이터를 불러올 수 없습니다</div>';
    });
  }
}
function rInstItems(stocks,isSell){
  if(!stocks||!stocks.length)return'<div class="empty-txt">No data</div>';
  const topN=stocks.slice(0,5);
  const maxAmt=Math.max(...topN.map(s=>Math.abs(s.amount||0)))||1;
  return topN.map((s,i)=>{
    const p=s.changePct||0,pc=p>0?'up':p<0?'dn':'fl';
    const amtPct=Math.round(Math.abs(s.amount||0)/maxAmt*100);
    const barColor=isSell?'var(--c-down)':(p>0?'var(--c-up)':p<0?'var(--c-down)':'var(--tx-3)');
    const amtDisplay=isSell?fAmt(-(Math.abs(s.amount||0))):fAmt(s.amount||0);
    const amtCls=isSell?'dn':pc;
    var cd=s.code||'';
    var click=cd?'onclick="openMo(\''+cd+'\')"':'style="cursor:default;opacity:.6"';
    return'<div class="is-item" '+click+'>'
      +'<div class="is-top">'
        +'<span class="is-rk">'+(i+1)+'</span>'
        +'<span class="is-nm">'+s.name+'</span>'
        +'<span class="is-amt '+amtCls+'">'+amtDisplay+'</span>'
      +'</div>'
      +'<div class="is-bot">'
        +'<span class="is-bar"><span class="is-fill" style="width:'+amtPct+'%;background:'+barColor+'"></span></span>'
        +'<span class="is-chg '+pc+'">'+(p>0?'+':'')+p.toFixed(1)+'%</span>'
      +'</div>'
    +'</div>';
  }).join('');
}


/* ═══════════════ Sell Popup ═══════════════ */
window.openSellPopup=function(ibKey){
  const overlay=document.getElementById('sellOverlay');
  const body=document.getElementById('sellPopBody');
  const logo=document.getElementById('sellPopLogo');
  const nm=document.getElementById('sellPopNm');
  if(!overlay||!body)return;
  const meta=IB_META[ibKey]||{name:ibKey,cls:''};
  logo.className='sell-popup__logo '+meta.cls;
  logo.textContent=ibKey;
  nm.textContent=meta.name;
  const items=sellDataStore[ibKey]||[];
  if(!items.length){
    body.innerHTML='<div class="empty-txt">No data</div>';
  }else{
    body.innerHTML='<div class="ib-sub-hd sell">Net Sell TOP '+items.length+'</div>'
      +rInstItems(items,true);
  }
  overlay.classList.add('on');
};
function closeSellPopup(){document.getElementById('sellOverlay').classList.remove('on')}

/* ═══════════════ Stock Modal ═══════════════ */
window.openMo=async function(code){
  if(!code||code==='undefined'||code==='null'){console.warn('openMo: invalid code',code);return}
  const mo=document.getElementById('mo'),bd=document.getElementById('mo-bd');
  if(!mo||!bd)return;
  mo.classList.add('on');
  bd.innerHTML='<div class="mo-loading">Loading...</div>';
  document.getElementById('mo-nm').textContent='';
  document.getElementById('mo-cd').textContent=code;
  try{
    const d=await API.stock(code);
    if(!d){bd.innerHTML='<div class="err-txt">No data</div>';return}
    document.getElementById('mo-nm').textContent=d.name||'';
    document.getElementById('mo-cd').textContent=code;
    const c=sigCls(d.signal),ar=sigArrow(d.signal);
    const ch=d.change||0,p=d.changePct||0;
    bd.innerHTML=`
      <div class="mo-prc-row">
        <span class="mo-prc">${fNum(d.curPrc||0)}\uC6D0</span>
        <span class="mo-prc-chg ${c}">${ar} ${ch>0?'+':''}${fNum(Math.abs(ch))} (${p>0?'+':''}${p.toFixed(2)}%)</span>
      </div>
      <div class="mo-grid">
        <div class="mo-f"><span class="mo-fl">Open</span><span class="mo-fv">${fNum(d.open||0)}</span></div>
        <div class="mo-f"><span class="mo-fl">High</span><span class="mo-fv">${fNum(d.high||0)}</span></div>
        <div class="mo-f"><span class="mo-fl">Low</span><span class="mo-fv">${fNum(d.low||0)}</span></div>
        <div class="mo-f"><span class="mo-fl">Volume</span><span class="mo-fv">${fNum(d.volume||0)}</span></div>
        <div class="mo-f"><span class="mo-fl">Market Cap</span><span class="mo-fv">${fCap(d.marketCap||0)}</span></div>
        <div class="mo-f"><span class="mo-fl">PER</span><span class="mo-fv">${(d.per||0).toFixed(2)}</span></div>
        <div class="mo-f"><span class="mo-fl">PBR</span><span class="mo-fv">${(d.pbr||0).toFixed(2)}</span></div>
        <div class="mo-f"><span class="mo-fl">Foreign %</span><span class="mo-fv">${(d.foreignRate||0).toFixed(1)}%</span></div>
      </div>`;
  }catch(e){bd.innerHTML='<div class="err-txt">Failed to load data</div>'}
};
function closeMo(){document.getElementById('mo').classList.remove('on')}

})();
