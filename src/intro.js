// 開場動畫:🐶🐰 相遇(每次開站只播一次;點一下略過;固定夜空,不跟主題)。
// 注意:這支是傳統(非 module)script,放在 #intro 之後同步執行,回訪者才不會閃一下夜空再消失。
// sessionStorage key 'azIntro' 與 src/storage.js 的 KEYS.INTRO 相同(這裡不能 import,須手動同步)。
(function(){
  const o=document.getElementById('intro');
  let seen=false; try{seen=!!sessionStorage.getItem('azIntro'); sessionStorage.setItem('azIntro','1');}catch(e){}
  if(seen||matchMedia('(prefers-reduced-motion: reduce)').matches||/[?&]p=/.test(location.search)){o.remove();return;}   // ?p= 是分享頁導回來的,直接開卡片
  const ttl=o.querySelector('.ttl'), p=o.querySelector('.pair'), cv=o.querySelector('canvas'), T=[];
  function close(){T.forEach(clearTimeout); if(!o.isConnected||o.classList.contains('out'))return; o.classList.add('out'); setTimeout(()=>o.remove(),520);}
  o.onclick=close;
  document.addEventListener('keydown',function k(e){ if(e.key==='Escape'||e.key==='Enter'||e.key===' '){close();} if(!o.isConnected) document.removeEventListener('keydown',k); });   // 鍵盤也能略過
  const dpr=Math.min(devicePixelRatio||1,2), W=innerWidth, H=innerHeight;
  cv.width=W*dpr; cv.height=H*dpr; const g=cv.getContext('2d'); g.scale(dpr,dpr);
  const S=Array.from({length:170},()=>({x:Math.random()*W,y:Math.random()*H,r:Math.random()*1.3+.3,
    d:Math.random()*600,tw:Math.random()*Math.PI*2,hue:Math.random()<.18?330:250}));
  const t0=performance.now();
  (function frame(now){                       // 星星陸續亮起、輕輕閃爍
    const t=now-t0; g.clearRect(0,0,W,H);
    for(const s of S){
      const a=Math.max(0,Math.min(1,(t-s.d)/400))*(0.6+0.4*Math.sin(t*0.004+s.tw));
      if(a<=0) continue;
      g.fillStyle=`hsla(${s.hue},70%,88%,${a})`; g.beginPath(); g.arc(s.x,s.y,s.r,0,Math.PI*2); g.fill();
    }
    if(o.isConnected) requestAnimationFrame(frame);
  })(t0);
  T.push(setTimeout(()=>ttl.classList.add('on'),60));
  T.push(setTimeout(()=>p.classList.add('meet'),120));     // 🐶🐰 從兩側靠近
  T.push(setTimeout(()=>p.classList.add('love'),850));     // ❤️ 冒出來
  T.push(setTimeout(close,1900));
})();
