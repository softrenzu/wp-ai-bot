(() => {
  const $ = selector => document.querySelector(selector);
  const show = (node,text) => { if(node) node.textContent = text; };
  const admin = $("#admin-form");
  if(admin) admin.addEventListener("submit",async ev=>{
    ev.preventDefault();
    const btn=admin.querySelector("button[type=submit]"),msg=$("#admin-result"),fd=new FormData(admin);
    const token=String(fd.get("adminToken")||"");
    const data=Object.fromEntries(["buyerCompany","signerName","signerEmail","serviceDetails"].map(k=>[k,String(fd.get(k)||"")]));
    btn.disabled=true;show(msg,"作成中...");
    try {
      const r=await fetch("/api/offers",{method:"POST",headers:{"content-type":"application/json",authorization:"Bearer "+token},body:JSON.stringify(data)});
      const j=await r.json();
      if(!r.ok) throw Error(j.error||"作成に失敗しました");
      const a=document.createElement("a");a.href=j.url;a.textContent="商談用URLを開く（"+j.quoteNumber+"）";a.rel="noopener";a.target="_blank";
      msg.textContent="";const qr=document.createElement("img");qr.src=j.url+"/qr.svg";qr.alt="顧客が読み取るための商談URLのQRコード";qr.className="qr";msg.append("作成済み：",a,document.createElement("br"),qr);
      admin.elements.adminToken.value="";
    } catch(e) {show(msg,e.message);} finally {btn.disabled=false;}
  });
  $("#print-document")?.addEventListener("click",()=>window.print());
  const form=$("#sign-form");
  if(form) {
    const canvas=$("#signature"),ctx=canvas.getContext("2d");let drawing=false,hasInk=false;
    ctx.lineWidth=3;ctx.lineCap="round";ctx.lineJoin="round";ctx.strokeStyle="#152b3d";
    function position(ev){const b=canvas.getBoundingClientRect();return {x:(ev.clientX-b.left)*canvas.width/b.width,y:(ev.clientY-b.top)*canvas.height/b.height};}
    canvas.addEventListener("pointerdown",ev=>{ev.preventDefault();drawing=true;canvas.setPointerCapture(ev.pointerId);const p=position(ev);ctx.beginPath();ctx.moveTo(p.x,p.y);ctx.lineTo(p.x+.1,p.y+.1);ctx.stroke();hasInk=true;});
    canvas.addEventListener("pointermove",ev=>{if(!drawing)return;ev.preventDefault();const p=position(ev);ctx.lineTo(p.x,p.y);ctx.stroke();});
    for(const type of ["pointerup","pointercancel"])canvas.addEventListener(type,()=>{drawing=false;});
    $("#clear-signature")?.addEventListener("click",()=>{ctx.clearRect(0,0,canvas.width,canvas.height);hasInk=false;});
    form.addEventListener("submit",async ev=>{
      ev.preventDefault();if(!hasInk){alert("署名欄に署名してください");return;}
      if(!form.reportValidity())return;
      const btn=form.querySelector("button[type=submit]");btn.disabled=true;
      const fd=new FormData(form);
      try {
        const r=await fetch("/api/offers/"+form.dataset.token+"/sign",{method:"POST",headers:{"content-type":"application/json"},body:JSON.stringify({
          agreementHash:form.dataset.hash,readTerms:true,authority:true,
          signedBy:fd.get("signedBy"),signedEmail:fd.get("signedEmail"),signatureImage:canvas.toDataURL("image/png")
        })});
        const j=await r.json();if(!r.ok)throw Error(j.error||"署名エラー");
        location.reload();
      } catch(e){alert(e.message);btn.disabled=false;}
    });
  }
  $("#checkout-button")?.addEventListener("click",async ev=>{
    const btn=ev.currentTarget,msg=$("#checkout-message");btn.disabled=true;show(msg,"Stripeの決済画面を準備しています");
    try {
      const r=await fetch("/api/offers/"+btn.dataset.token+"/checkout",{method:"POST"});
      const j=await r.json();if(!r.ok)throw Error(j.error||"決済画面を開けません");
      location.assign(j.url);
    } catch(e){show(msg,e.message);btn.disabled=false;}
  });
  if(new URLSearchParams(location.search).get("payment")==="success" && $("#checkout-message"))
    show($("#checkout-message"),"Stripeでの決済手続きを受け付けました。決済確定はWebhook確認後に反映されます。");
})();
