const I18N=window.CG_I18N||{};
const tr=(key,fallback='')=>I18N[key]||fallback||key;
const lang=window.CG_LANG==='fr'?'fr':'en';
let chartSequence=0;
let dashboardCoins=[];
let dashboardPage=1;
const dashboardPageSize=20;
let knownAlertIds=null;
let alertPreferences={enabled:true,sound_volume:65,minimum_severity:'info',browser_notifications:true};
let audioContext=null;

function escapeHtml(value){return String(value??'').replace(/[&<>'"]/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[char]))}
function fmtPct(value){return value===null||value===undefined||Number.isNaN(Number(value))?'—':`${Number(value)>=0?'+':''}${Number(value).toFixed(2)}%`}
function fmtPrice(value){const number=Number(value);if(!Number.isFinite(number))return '—';const abs=Math.abs(number);let max=2;if(abs<1)max=6;if(abs<.001)max=10;return number.toLocaleString(undefined,{maximumFractionDigits:max,maximumSignificantDigits:10})}
function fmtTime(ts){if(!ts)return '—';return new Date(Number(ts)*1000).toLocaleString()}
function fmtBytes(value){const n=Number(value)||0;if(n<1024)return `${n} B`;if(n<1024**2)return `${(n/1024).toFixed(1)} KB`;if(n<1024**3)return `${(n/1024**2).toFixed(2)} MB`;return `${(n/1024**3).toFixed(2)} GB`}
function fmtAge(seconds){const n=Math.max(0,Number(seconds)||0);if(n<60)return `${Math.round(n)}s`;if(n<3600)return `${Math.round(n/60)}m`;return `${(n/3600).toFixed(1)}h`}
function metricClass(value){const n=Number(value);if(!Number.isFinite(n))return 'neutral';return n>.05?'positive':n<-.05?'negative':'neutral'}
function assetLabel(kind){const labels={en:{crypto:'Crypto',meme:'Meme',tokenized_asset:'Tokenized',crypto_token:'Crypto token',commodity:'Spot metal'},fr:{crypto:'Crypto',meme:'Mème',tokenized_asset:'Tokenisé',crypto_token:'Jeton crypto',commodity:'Métal spot'}};return labels[lang][kind]||String(kind||'crypto').replaceAll('_',' ')}
function sourceLabel(source){return source==='gold_api'?'Gold API':'CoinGecko'}
function marketStatus(coin){if(coin.is_stale||coin.market_status==='stale')return {key:'stale',label:lang==='fr'?'Données anciennes':'Stale data'};if(coin.market_status==='closed')return {key:'closed',label:lang==='fr'?'Session fermée':'Market closed'};return {key:'live',label:coin.trading_mode==='24x7'?'24/7 LIVE':(lang==='fr'?'Session ouverte':'Session open')}}
function chartPath(points){if(points.length<2)return '';return points.map((point,index)=>`${index?'L':'M'} ${point.x.toFixed(2)} ${point.y.toFixed(2)}`).join(' ')}
function sparklineSvg(values,meta={}){
  const nums=(values||[]).map(Number).filter(Number.isFinite),period=Number(meta.period_hours)||24;
  if(nums.length<2)return `<div class="sparkline-empty"><span>${escapeHtml(tr('preparing','Preparing fresh'))} ${period}h ${lang==='fr'?'dans cette devise':'history in this currency'}…</span></div>`;
  const rawMin=Math.min(...nums),rawMax=Math.max(...nums),center=(rawMax+rawMin)/2;
  let span=rawMax-rawMin;const pad=Math.max(span*.14,Math.abs(center)*.0005,1e-10);let min=rawMin,max=rawMax+pad;min=rawMin-pad;span=max-min||1;
  const width=320,height=112,top=13,bottom=96;
  const points=nums.map((v,i)=>({x:i/(nums.length-1)*width,y:bottom-((v-min)/span)*(bottom-top)}));
  const linePath=chartPath(points),areaPath=`${linePath} L ${points.at(-1).x.toFixed(2)} ${bottom} L ${points[0].x.toFixed(2)} ${bottom} Z`;
  const trend=nums.at(-1)>nums[0]?'positive':nums.at(-1)<nums[0]?'negative':'neutral',last=points.at(-1),id=`cg-grad-${++chartSequence}`;
  const caption=`${period}h · ${nums.length} pts · ${sourceLabel(meta.source)}`;
  return `<div class="chart-shell"><div class="chart-extrema"><span>${fmtPrice(rawMax)}</span><span>${fmtPrice(rawMin)}</span></div><svg class="sparkline ${trend}" viewBox="0 0 ${width} ${height}" preserveAspectRatio="none" role="img" aria-label="Price chart"><defs><linearGradient id="${id}" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="currentColor" stop-opacity=".45"/><stop offset="100%" stop-color="currentColor" stop-opacity="0"/></linearGradient></defs><line class="grid" x1="0" y1="31" x2="${width}" y2="31"/><line class="grid" x1="0" y1="56" x2="${width}" y2="56"/><line class="grid" x1="0" y1="81" x2="${width}" y2="81"/><path class="area" style="fill:url(#${id})" d="${areaPath}"/><path class="line" d="${linePath}" fill="none"/><circle class="last-dot" cx="${last.x.toFixed(2)}" cy="${last.y.toFixed(2)}" r="3.2"/></svg><span class="chart-caption">${escapeHtml(caption)}</span></div>`;
}
function coinCard(coin){
  const m=coin.metrics||{},status=marketStatus(coin),headline=m['15m']??m['1h']??coin.change_24h;
  const note=coin.data_note?`<details class="data-source-details"><summary>${escapeHtml(lang==='fr'?'À propos de la source':'About this data source')}</summary><p class="data-note">${escapeHtml(coin.data_note)}</p></details>`:'';
  const quality=coin.data_quality_warning?`<p class="data-quality-note">⚠ ${escapeHtml(lang==='fr'?'Graphique assaini : des points incompatibles ont été ignorés.':'Chart integrity: incompatible points were ignored.')}</p>`:'';
  const age=coin.data_age_seconds!==undefined?`${lang==='fr'?'âge':'age'} ${fmtAge(coin.data_age_seconds)}`:'';
  const hourSource=m['1h_source']==='provider'?'API':(lang==='fr'?'local':'local');
  return `<article class="market-card" data-coin-id="${escapeHtml(coin.id)}"><header><div><div class="asset-line"><h3>${escapeHtml(coin.symbol)}</h3><span class="asset-badge kind-${escapeHtml(coin.asset_kind||'crypto')}">${escapeHtml(assetLabel(coin.asset_kind||'crypto'))}</span></div><p>${escapeHtml(coin.name)}</p></div><span class="change-pill ${metricClass(headline)}">${fmtPct(headline)}</span></header><div class="price-line"><strong>${fmtPrice(coin.price)}</strong><span>${escapeHtml(String(coin.fiat||'').toUpperCase())}${coin.unit==='troy_ounce'?' / oz':''}</span></div>${sparklineSvg(coin.sparkline,coin.sparkline_meta||{})}<div class="metrics"><span>5m <b class="${metricClass(m['5m'])}">${fmtPct(m['5m'])}</b></span><span>15m <b class="${metricClass(m['15m'])}">${fmtPct(m['15m'])}</b></span><span>1h <small class="metric-source">${hourSource}</small><b class="${metricClass(m['1h'])}">${fmtPct(m['1h'])}</b></span><span>24h <b class="${metricClass(coin.change_24h)}">${fmtPct(coin.change_24h)}</b></span></div><div class="asset-foot"><div><span class="source-badge">${escapeHtml(sourceLabel(coin.source))}</span><span class="status-badge ${status.key}">${escapeHtml(status.label)}</span></div><span>${escapeHtml(age)}</span></div>${quality}${note}</article>`;
}
function alertCard(alert){return `<article class="alert-item severity-${escapeHtml(alert.severity)}"><div class="alert-marker"></div><div class="alert-copy"><div><span class="badge ${escapeHtml(alert.severity)}">${escapeHtml(alert.severity)}</span><time>${fmtTime(alert.ts)}</time></div><p>${escapeHtml(alert.message)}</p></div></article>`}
function setText(id,text){const el=document.getElementById(id);if(el)el.textContent=text}
function setBar(id,value){const el=document.getElementById(id),n=Math.max(0,Math.min(100,Number(value)||0));if(el)el.style.width=`${n}%`;setText(`${id}-value`,`${n.toFixed(0)}%`)}

function filteredDashboardCoins(){
  const query=(document.getElementById('market-filter')?.value||'').trim().toLowerCase();
  if(!query)return dashboardCoins;
  return dashboardCoins.filter(coin=>`${coin.symbol||''} ${coin.name||''} ${coin.id||''}`.toLowerCase().includes(query));
}
function renderDashboardCoins(){
  const cards=document.getElementById('coin-cards');if(!cards)return;
  const filtered=filteredDashboardCoins(),pages=Math.max(1,Math.ceil(filtered.length/dashboardPageSize));dashboardPage=Math.min(Math.max(1,dashboardPage),pages);
  const start=(dashboardPage-1)*dashboardPageSize,visible=filtered.slice(start,start+dashboardPageSize);
  cards.innerHTML=visible.map(coinCard).join('')||`<div class="empty-state"><span>◌</span><p>${escapeHtml(tr('waiting','Waiting…'))}</p></div>`;
  const pagination=document.getElementById('market-pagination');if(!pagination)return;
  if(pages<=1){pagination.innerHTML='';return}
  pagination.innerHTML=`<button type="button" data-page="${dashboardPage-1}" ${dashboardPage===1?'disabled':''}>‹</button><span>${dashboardPage} / ${pages}</span><button type="button" data-page="${dashboardPage+1}" ${dashboardPage===pages?'disabled':''}>›</button>`;
  pagination.querySelectorAll('button[data-page]').forEach(button=>button.addEventListener('click',()=>{dashboardPage=Number(button.dataset.page)||1;renderDashboardCoins();document.getElementById('coin-cards')?.scrollIntoView({behavior:'smooth',block:'start'})}));
}

function alertIdentity(alert){return String(alert.id??`${alert.alert_key||alert.rule||'alert'}:${alert.ts||0}:${alert.message||''}`)}
function severityRank(value){return {info:0,warning:1,high:2,critical:3}[String(value||'info').toLowerCase()]??0}
function soundEnabled(){return localStorage.getItem('cgAlertSoundEnabled')==='1'}
function updateSoundButton(){const button=document.getElementById('alert-sound-toggle');if(button)button.textContent=soundEnabled()?`🔊 ${tr('disable_sound','Disable sound')}`:`🔔 ${tr('enable_sound','Enable sound')}`}
async function ensureAudio(){if(!audioContext){const AudioContextClass=window.AudioContext||window.webkitAudioContext;if(!AudioContextClass)throw new Error('Web Audio unavailable');audioContext=new AudioContextClass()}if(audioContext.state==='suspended')await audioContext.resume();return audioContext}
async function playAlertSound(severity='info'){
  if(!soundEnabled()||alertPreferences.enabled===false)return;
  try{
    const context=await ensureAudio(),volume=Math.max(0,Math.min(1,Number(alertPreferences.sound_volume??65)/100)),count=severityRank(severity)>=3?3:severityRank(severity)>=1?2:1;
    for(let i=0;i<count;i++){
      const oscillator=context.createOscillator(),gain=context.createGain();oscillator.frequency.value=severityRank(severity)>=2?880:660;gain.gain.setValueAtTime(0.0001,context.currentTime);gain.gain.exponentialRampToValueAtTime(Math.max(.0001,volume*.18),context.currentTime+.015);gain.gain.exponentialRampToValueAtTime(.0001,context.currentTime+.18);oscillator.connect(gain);gain.connect(context.destination);oscillator.start(context.currentTime);oscillator.stop(context.currentTime+.2);await new Promise(resolve=>setTimeout(resolve,260));
    }
  }catch(error){console.debug('Alert sound',error)}
}
function showBrowserAlert(alert){
  if(!alertPreferences.browser_notifications||!('Notification' in window)||Notification.permission!=='granted')return;
  try{new Notification(`CryptoGotchi · ${String(alert.severity||'info').toUpperCase()}`,{body:String(alert.message||''),tag:alertIdentity(alert),renotify:false})}catch(error){console.debug('Browser notification',error)}
}
async function processNewAlerts(alerts){
  const ids=new Set((alerts||[]).map(alertIdentity));
  if(knownAlertIds===null){knownAlertIds=ids;return}
  if(alertPreferences.enabled===false){knownAlertIds=ids;return}
  const minimum=severityRank(alertPreferences.minimum_severity||'info');
  const fresh=(alerts||[]).filter(alert=>!knownAlertIds.has(alertIdentity(alert))&&severityRank(alert.severity)>=minimum);
  knownAlertIds=ids;
  for(const alert of fresh.reverse()){await playAlertSound(alert.severity);showBrowserAlert(alert)}
}

async function refreshDashboard(){
  try{
    const response=await fetch('/api/status',{headers:{Accept:'application/json'}});if(!response.ok)return;
    const data=await response.json(),s=data.status||{},c=s.companion||{};alertPreferences={...alertPreferences,...(data.browser_alerts||{})};
    setText('state',String(s.state||'?').toUpperCase());setText('message',s.message||'');setText('brain-thought',c.thought||'');setText('brain-engine',c.engine||'micro-brain-v2');setText('brain-xp',c.xp||0);setText('brain-observations',c.observations||0);setText('last-update',`${tr('last_update','Last update')}: ${fmtTime(s.last_update)}`);
    const hero=document.getElementById('hero');if(hero)hero.className=`hero command-deck state-${s.state}`;
    const avatar=document.getElementById('web-avatar');if(avatar){const accessory=c.accessory||avatar.dataset.accessory||'none';avatar.dataset.accessory=accessory;avatar.className=`cg-avatar mood-${s.state} accessory-${accessory}`}
    dashboardCoins=s.coins||[];renderDashboardCoins();
    const alerts=data.alerts||[],alertBox=document.getElementById('alerts');if(alertBox)alertBox.innerHTML=alerts.map(alertCard).join('')||`<div class="empty-state compact"><span>✓</span><p>${escapeHtml(tr('none','No alerts.'))}</p></div>`;
    await processNewAlerts(alerts);
    setText('market-online',s.online?tr('online','Online'):tr('offline','Offline'));setText('cpu-temp',Number.isFinite(Number(s.system?.cpu_temp_c))?`${Number(s.system.cpu_temp_c).toFixed(1)}°C`:'—');
    const toggle=document.getElementById('notification-toggle');if(toggle)toggle.textContent=s.notifications_paused?tr('resume','Resume alerts'):tr('pause','Pause alerts');
    const economy=s.network?.economy||{};setText('economy-state',economy.active?`${tr('active','Active')} · ${economy.reason||'auto'}`:tr('normal','Normal'));setText('network-state',economy.connection?.type||'—');setText('data-usage',fmtBytes(s.network?.usage_today_bytes));setBar('vital-energy',c.energy);setBar('vital-stress',c.stress);setBar('vital-bond',c.bond);
  }catch(error){console.debug('Dashboard refresh',error)}
}

const navToggle=document.getElementById('nav-toggle'),siteNav=document.getElementById('site-nav');if(navToggle&&siteNav)navToggle.addEventListener('click',()=>{const open=siteNav.classList.toggle('open');navToggle.setAttribute('aria-expanded',String(open))});
document.addEventListener('click',event=>{if(siteNav?.classList.contains('open')&&!siteNav.contains(event.target)&&!navToggle?.contains(event.target)){siteNav.classList.remove('open');navToggle.setAttribute('aria-expanded','false')}});
document.querySelectorAll('[data-ts]').forEach(element=>element.textContent=fmtTime(element.dataset.ts));

const marketFilter=document.getElementById('market-filter');if(marketFilter)marketFilter.addEventListener('input',()=>{dashboardPage=1;renderDashboardCoins()});
const soundToggle=document.getElementById('alert-sound-toggle');if(soundToggle){updateSoundButton();soundToggle.addEventListener('click',async()=>{const enabling=!soundEnabled();localStorage.setItem('cgAlertSoundEnabled',enabling?'1':'0');if(enabling){try{await ensureAudio();await playAlertSound('info')}catch(error){console.debug(error)}if(alertPreferences.browser_notifications&&'Notification' in window&&Notification.permission==='default'){try{await Notification.requestPermission()}catch(error){console.debug(error)}}}updateSoundButton()})}
if(window.CRYPTOGOTCHI_DASHBOARD){refreshDashboard();setInterval(refreshDashboard,15000)}
const forceRefresh=document.getElementById('force-refresh');if(forceRefresh)forceRefresh.addEventListener('click',async()=>{forceRefresh.disabled=true;const old=forceRefresh.innerHTML;forceRefresh.textContent=tr('refreshing','Refreshing…');try{await fetch('/api/refresh',{method:'POST',headers:{'X-CSRF-Token':window.CRYPTOGOTCHI_CSRF,Accept:'application/json'}});setTimeout(refreshDashboard,1100)}finally{setTimeout(()=>{forceRefresh.disabled=false;forceRefresh.innerHTML=old},1500)}});

const analysisForm=document.getElementById('companion-analysis-form');if(analysisForm){const selector=analysisForm.querySelector('.asset-selector'),maximum=Math.max(1,Number(selector?.dataset.max)||5),counter=document.getElementById('analysis-selected-count');const sync=changed=>{const checked=[...analysisForm.querySelectorAll('input[name="coin_ids"]:checked')];if(checked.length>maximum&&changed){changed.checked=false}analysisForm.querySelectorAll('.asset-choice').forEach(label=>label.classList.toggle('selected',Boolean(label.querySelector('input')?.checked)));if(counter)counter.textContent=String(analysisForm.querySelectorAll('input[name="coin_ids"]:checked').length)};analysisForm.querySelectorAll('input[name="coin_ids"]').forEach(input=>input.addEventListener('change',()=>sync(input)));analysisForm.addEventListener('submit',event=>{if(!analysisForm.querySelector('input[name="coin_ids"]:checked')){event.preventDefault();alert(lang==='fr'?'Sélectionne au moins un actif.':'Select at least one asset.')}});sync()}

const searchBtn=document.getElementById('coin-search-btn');if(searchBtn)searchBtn.addEventListener('click',async()=>{
  const q=document.getElementById('coin-search').value.trim();if(q.length<2)return;const box=document.getElementById('coin-results');box.textContent=tr('searching','Searching…');
  try{const response=await fetch(`/api/coins/search?q=${encodeURIComponent(q)}`),data=await response.json();if(!Array.isArray(data)){box.textContent=data.error||tr('error','Error');return}
    box.innerHTML=data.map(item=>`<div class="search-result" data-id="${escapeHtml(item.id)}" data-symbol="${escapeHtml(item.symbol)}" data-name="${escapeHtml(item.name)}" data-kind="${escapeHtml(item.asset_kind||'crypto')}" data-note="${escapeHtml(item.warning||'')}"><div class="search-result-main">${item.thumb?`<img src="${escapeHtml(item.thumb)}" alt="">`:''}<div><b>${escapeHtml(item.symbol)} · ${escapeHtml(item.name)}</b><small>${escapeHtml(item.id)}${item.market_cap_rank?` · #${escapeHtml(item.market_cap_rank)}`:''}</small></div></div><div class="search-result-tags"><span class="asset-badge kind-${escapeHtml(item.asset_kind||'crypto')}">${escapeHtml(assetLabel(item.asset_kind||'crypto'))}</span>${item.warning?'<span class="status-badge closed">CHECK</span>':''}</div></div>`).join('')||`<div class="empty-state compact"><p>${lang==='fr'?'Aucun résultat':'No results'}</p></div>`;
    box.querySelectorAll('.search-result').forEach(row=>row.addEventListener('click',()=>{document.getElementById('add-id').value=row.dataset.id;document.getElementById('add-symbol').value=row.dataset.symbol;document.getElementById('add-name').value=row.dataset.name;document.getElementById('add-asset-kind').value=row.dataset.kind||'crypto';document.getElementById('add-data-note').value=row.dataset.note||'';const info=document.getElementById('selected-asset-info');if(info)info.innerHTML=`<span class="asset-badge kind-${escapeHtml(row.dataset.kind||'crypto')}">${escapeHtml(assetLabel(row.dataset.kind||'crypto'))}</span> ${escapeHtml(row.dataset.note||(lang==='fr'?'Flux crypto CoinGecko 24 h/24.':'CoinGecko crypto stream, 24/7.'))}`;document.getElementById('add-coin-form').scrollIntoView({behavior:'smooth',block:'start'})}))
  }catch(error){box.textContent=tr('error','Error')}
});
const searchInput=document.getElementById('coin-search');if(searchInput)searchInput.addEventListener('keydown',event=>{if(event.key==='Enter'){event.preventDefault();searchBtn?.click()}});

const wifiScanBtn=document.getElementById('wifi-scan-btn');if(wifiScanBtn)wifiScanBtn.addEventListener('click',async()=>{const status=document.getElementById('wifi-scan-status'),box=document.getElementById('wifi-results');status.textContent=`${tr('scan_wifi','Scan Wi-Fi')}…`;box.innerHTML='';try{const response=await fetch('/api/wifi/scan'),data=await response.json();if(!Array.isArray(data)){status.textContent=data.error||tr('error','Error');return}status.textContent=`${data.length}`;box.innerHTML=data.map(network=>`<div class="search-result wifi-result" data-ssid="${escapeHtml(network.ssid)}" data-security="${escapeHtml(network.security||'')}"><div><b>${escapeHtml(network.ssid)}</b><small>${escapeHtml(network.security||tr('open','Open'))}</small></div><span class="status-badge live">${escapeHtml(network.signal)}%</span></div>`).join('');box.querySelectorAll('.wifi-result').forEach(row=>row.addEventListener('click',()=>{document.getElementById('wifi-ssid').value=row.dataset.ssid;document.getElementById('wifi-hidden').checked=false;const security=String(row.dataset.security||'').toUpperCase(),select=document.getElementById('wifi-security');if(select)select.value=security.includes('SAE')&&!security.includes('WPA2')?'sae':(security?'wpa-psk':'open');document.getElementById('wifi-password').focus()}))}catch(error){status.textContent=tr('error','Error')}});
function bluetoothActions(device){const token=escapeHtml(window.CRYPTOGOTCHI_CSRF),address=escapeHtml(device.address),hidden=`<input type="hidden" name="csrf_token" value="${token}"><input type="hidden" name="bluetooth_address" value="${address}">`;const connect=device.pan_active?`<button type="button" disabled>${escapeHtml(lang==='fr'?'Internet actif':'Internet active')}</button>`:`<form method="post" action="/bluetooth/connect">${hidden}<button>${escapeHtml(lang==='fr'?'Connecter Internet':'Connect Internet')}</button></form>`;return `<div class="device-actions">${device.paired?'':`<form method="post" action="/bluetooth/pair">${hidden}<button>${escapeHtml(tr('pair','Pair'))}</button></form>`}${connect}<form method="post" action="/bluetooth/diagnostics">${hidden}<button class="secondary">${escapeHtml(tr('diagnostics','Diagnostics'))}</button></form>${device.pan_active?`<form method="post" action="/bluetooth/disconnect">${hidden}<button class="secondary">${escapeHtml(tr('disconnect','Disconnect'))}</button></form>`:''}${device.paired?`<form method="post" action="/bluetooth/remove">${hidden}<button class="danger">${escapeHtml(tr('remove','Forget'))}</button></form>`:''}</div>`}
const bluetoothScanBtn=document.getElementById('bluetooth-scan-btn');if(bluetoothScanBtn)bluetoothScanBtn.addEventListener('click',async()=>{const status=document.getElementById('bluetooth-scan-status'),box=document.getElementById('bluetooth-results');status.textContent=`${tr('scan_phones','Scan phones')}…`;box.innerHTML='';bluetoothScanBtn.disabled=true;try{const response=await fetch('/api/bluetooth/scan'),data=await response.json();if(!Array.isArray(data)){status.textContent=data.error||tr('error','Error');return}status.textContent=`${data.length}`;box.innerHTML=data.map(device=>{const pan=device.pan_active?(lang==='fr'?`Internet PAN actif · ${device.pan_device||'bnep'}${device.pan_ipv4?` · ${device.pan_ipv4}`:''}`:`PAN internet active · ${device.pan_device||'bnep'}${device.pan_ipv4?` · ${device.pan_ipv4}`:''}`):(device.connected?(lang==='fr'?'Bluetooth connecté, Internet PAN inactif':'Bluetooth connected, PAN internet inactive'):(lang==='fr'?'hors ligne':'offline'));return `<article class="bt-device ${device.pan_active?'pan-active':''}"><div><b>${escapeHtml(device.name)}</b><small>${escapeHtml(device.address)} · ${device.paired?'paired':'new'} · ${escapeHtml(pan)}</small></div>${bluetoothActions(device)}</article>`}).join('')||'<p>—</p>'}catch(error){status.textContent=tr('error','Error')}finally{bluetoothScanBtn.disabled=false}});
document.querySelectorAll('.range-input').forEach(input=>{const output=input.parentElement.querySelector('output');const sync=()=>{if(output)output.textContent=input.value};input.addEventListener('input',sync);sync()});
