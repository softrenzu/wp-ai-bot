import "dotenv/config";
import express from "express";
import helmet from "helmet";
import rateLimit from "express-rate-limit";
import pg from "pg";
import Stripe from "stripe";
import QRCode from "qrcode";
import { randomUUID, timingSafeEqual } from "node:crypto";
import { makeAgreement, makeToken, quoteNumber, sha256, yen, MONTHLY_PRICE, TAX_AMOUNT, TOTAL } from "./lib.js";

const app = express();
const port = Number(process.env.PORT || 3000);
const baseUrl = (process.env.PUBLIC_BASE_URL || "http://localhost:3000").replace(/\/$/, "");
const issuerName = process.env.ISSUER_NAME || "株式会社穣";
const issuerAddress = process.env.ISSUER_ADDRESS || "";
const issuerEmail = process.env.ISSUER_EMAIL || "";
const registration = process.env.INVOICE_REGISTRATION_NUMBER || "";
const stripe = process.env.STRIPE_SECRET_KEY ? new Stripe(process.env.STRIPE_SECRET_KEY) : null;
const pool = new pg.Pool({
  connectionString: process.env.DATABASE_URL,
  ssl: process.env.DATABASE_SSL === "true" ? { rejectUnauthorized: true } : false
});
const h = value => String(value ?? "").replace(/[&<>"']/g, c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const fail = (res,code,message) => res.status(code).json({ error:message });
const tokenHash = token => sha256(token);
const isAdmin = req => {
  const expected = process.env.ADMIN_TOKEN || "";
  const supplied = (req.get("authorization") || "").replace(/^Bearer\s+/i,"");
  if(expected.length < 24 || expected.length !== supplied.length) return false;
  return timingSafeEqual(Buffer.from(expected),Buffer.from(supplied));
};
const fetchOffer = async token => {
  if(!/^[a-f0-9]{64}$/.test(token || "")) return null;
  const {rows} = await pool.query("SELECT * FROM offers WHERE token_hash=$1", [tokenHash(token)]);
  return rows[0] || null;
};
const docHead = (title, bodyClass="") => `<!doctype html><html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>${h(title)} | ${h(issuerName)}</title><link rel="stylesheet" href="/style.css"></head><body class="${h(bodyClass)}">`;
const footer = `<footer>運営：${h(issuerName)}　お困りの際は ${h(issuerEmail || "販売担当者")} へお問い合わせください。</footer></body></html>`;
const docLink = (token,type) => `/o/${token}/document/${type}`;

app.set("trust proxy", 1);
app.use(helmet({contentSecurityPolicy: {directives: {defaultSrc:["'self'"],scriptSrc:["'self'"],styleSrc:["'self'"],imgSrc:["'self'","data:"],connectSrc:["'self'"],formAction:["'self'"]}}}));
app.use(rateLimit({windowMs:15*60*1000,limit:200,standardHeaders:"draft-7",legacyHeaders:false}));
app.post("/webhooks/stripe", express.raw({type:"application/json"}), async (req,res)=>{
  if(!stripe || !process.env.STRIPE_WEBHOOK_SECRET) return fail(res,503,"決済Webhook設定が未完了です");
  let event;
  try { event = stripe.webhooks.constructEvent(req.body,req.get("stripe-signature"),process.env.STRIPE_WEBHOOK_SECRET); }
  catch { return fail(res,400,"署名検証エラー"); }
  const client = await pool.connect();
  try {
    await client.query("BEGIN");
    const inserted=await client.query("INSERT INTO webhook_events(id,type) VALUES($1,$2) ON CONFLICT DO NOTHING RETURNING id",[event.id,event.type]);
    if(inserted.rowCount) {
      const obj=event.data.object;
      if(event.type === "checkout.session.completed") {
        await client.query("UPDATE offers SET stripe_subscription_id=$2,stripe_customer_id=$3,status=CASE WHEN status='paid' THEN 'paid' ELSE 'checkout_complete' END WHERE id=$1 AND signed_at IS NOT NULL",
          [obj.metadata?.offer_id || obj.client_reference_id,obj.subscription || null,obj.customer || null]);
      } else if(event.type === "invoice.paid" || event.type === "invoice.payment_failed") {
        const subId=obj.subscription || obj.parent?.subscription_details?.subscription || null;
        let offerId=obj.parent?.subscription_details?.metadata?.offer_id || null;
        if(!offerId && subId && stripe) { const sub=await stripe.subscriptions.retrieve(subId); offerId=sub.metadata?.offer_id; }
        if(offerId) {
          await client.query("UPDATE offers SET status=$2,paid_at=CASE WHEN $2='paid' THEN NOW() ELSE paid_at END,stripe_subscription_id=COALESCE($3,stripe_subscription_id),stripe_customer_id=COALESCE($4,stripe_customer_id),stripe_invoice_url=COALESCE($5,stripe_invoice_url) WHERE id=$1 AND signed_at IS NOT NULL",
          [offerId,event.type==="invoice.paid"?"paid":"past_due",subId,obj.customer || null,obj.hosted_invoice_url || null]);
        }
      } else if(event.type === "charge.succeeded" && obj.receipt_url) {
        // A charge event may arrive before checkout.session.completed.
        // Locate the offer through the subscription's metadata first.
        let offerId=null;
        const invoiceId=typeof obj.invoice==="string"?obj.invoice:obj.invoice?.id;
        if(invoiceId) {
          const invoice=await stripe.invoices.retrieve(invoiceId);
          const subId=invoice.subscription || invoice.parent?.subscription_details?.subscription;
          if(subId) {
            const sub=await stripe.subscriptions.retrieve(subId);
            offerId=sub.metadata?.offer_id || null;
          }
        }
        if(offerId) {
          await client.query("UPDATE offers SET stripe_receipt_url=$2,stripe_customer_id=COALESCE($3,stripe_customer_id) WHERE id=$1 AND signed_at IS NOT NULL",
            [offerId,obj.receipt_url,obj.customer || null]);
        } else if(obj.customer) {
          await client.query("UPDATE offers SET stripe_receipt_url=$2 WHERE stripe_customer_id=$1 AND signed_at IS NOT NULL",
            [obj.customer,obj.receipt_url]);
        }
      } else if(event.type === "customer.subscription.deleted") {
        await client.query("UPDATE offers SET status='cancelled' WHERE stripe_subscription_id=$1",[obj.id]);
      }
    }
    await client.query("COMMIT");
    return res.json({received:true});
  } catch(error) {
    await client.query("ROLLBACK");
    console.error("webhook processing error",error);
    return fail(res,500,"Webhook処理エラー");
  } finally { client.release(); }
});
app.use(express.json({limit:"240kb"}));
app.use(express.static("public",{index:false,maxAge:"1h"}));

app.get("/",(_req,res)=>res.redirect("/admin"));
app.get("/health",async (_req,res)=>{
  try { await pool.query("SELECT 1"); res.json({ok:true,db:"connected"}); }
  catch { fail(res,503,"DB未接続"); }
});
app.get("/admin",(_req,res)=>res.send(docHead("見積・契約の作成")+`
<header class="top"><div class="wrap nav"><div class="brand">JO AI <span>営業・契約</span></div><span>管理者専用</span></div></header>
<main class="wrap narrow">
 <div class="eyebrow">NEW OFFER</div><h1>その場で見積・契約を開始</h1><p class="lead">顧客情報を入力すると、商談用URLを発行します。価格は月額15,000円＋消費税です。</p>
 <section class="panel"><form id="admin-form">
 <label>管理者トークン<input name="adminToken" type="password" autocomplete="off" required placeholder="ADMIN_TOKEN"></label>
 <label>顧客の会社名・屋号<input name="buyerCompany" required maxlength="120" placeholder="例：株式会社サンプル"></label>
 <label>署名する担当者名<input name="signerName" required maxlength="80" placeholder="例：山田 太郎"></label>
 <label>担当者メールアドレス<input name="signerEmail" type="email" required maxlength="200"></label>
 <label>対象ブログ・投稿頻度等<textarea name="serviceDetails" rows="3" required maxlength="1000" placeholder="対象媒体・投稿頻度・承認手順など"></textarea></label>
 <div class="price-box"><div>月額利用料<strong>15,000円</strong></div><div>消費税（10%）<strong>1,500円</strong></div><div class="total">初回・月額合計<strong>16,500円</strong></div></div>
 <button class="primary" type="submit">顧客用の見積・契約URLを作成</button>
 </form><p role="status" id="admin-result"></p></section>
 <p class="muted">生成したURLは第三者に共有しないでください。管理トークンはブラウザーに保存されません。</p>
</main><script src="/app.js" defer></script>`+footer));

app.post("/api/offers",async (req,res)=>{
  if(!isAdmin(req)) return fail(res,401,"管理者認証に失敗しました");
  const {buyerCompany,signerName,signerEmail,serviceDetails}=req.body || {};
  if(![buyerCompany,signerName,signerEmail,serviceDetails].every(x=>typeof x==="string" && x.trim())) return fail(res,400,"必須項目が不足しています");
  if(buyerCompany.length>120||signerName.length>80||signerEmail.length>200||serviceDetails.length>1000||!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(signerEmail)) return fail(res,400,"入力値が不正です");
  const id=randomUUID(),token=makeToken();
  const agreement=makeAgreement({issuerName,issuerAddress,buyerCompany:buyerCompany.trim(),signerName:signerName.trim(),serviceDetails:serviceDetails.trim()});
  const qn=quoteNumber(id);
  await pool.query(`INSERT INTO offers(id,token_hash,quote_number,buyer_company,signer_name,signer_email,service_details,agreement_text,agreement_hash)
 VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9)`,
  [id,tokenHash(token),qn,buyerCompany.trim(),signerName.trim(),signerEmail.trim(),serviceDetails.trim(),agreement,sha256(agreement)]);
  res.status(201).json({url:`${baseUrl}/o/${token}`,quoteNumber:qn});
});

app.get("/o/:token",async (req,res)=>{
  const o=await fetchOffer(req.params.token);
  if(!o) return res.status(404).send("URLが無効です");
  const t=req.params.token, signed=Boolean(o.signed_at), paid=o.status==="paid";
  res.send(docHead("お見積・契約")+`
<header class="top"><div class="wrap nav"><div class="brand">JO AI <span>ブログ自動AI投稿</span></div><span class="status">${h(paid?"決済完了":signed?"署名済み":"お申込み受付")}</span></div></header>
<main class="wrap">
  <div class="hero"><div><div class="eyebrow">QUOTE & AGREEMENT</div><h1>ブログを、AIで<br>もっと手軽に。</h1><p>お見積・ご契約・お支払いを、この画面で完了できます。</p></div>
  <div class="hero-price"><span>月額利用料（税込）</span><strong>16,500<small>円</small></strong><em>税抜15,000円＋税1,500円</em></div></div>
  <div class="steps"><span class="done">01 見積</span><span class="${signed?"done":"active"}">02 契約・署名</span><span class="${paid?"done":signed?"active":""}">03 決済</span><span class="${paid?"done":""}">04 書類受領</span></div>
  <div class="columns"><section class="panel"><div class="eyebrow">ESTIMATE</div><h2>お見積書</h2>
   <p class="muted">見積番号：${h(o.quote_number)}<br>宛先：${h(o.buyer_company)} 御中</p>
   <div class="line"><span>ブログ自動AI投稿サービス（月額）</span><strong>15,000円</strong></div><div class="line"><span>消費税10%</span><strong>1,500円</strong></div><div class="line sum"><span>合計</span><strong>16,500円</strong></div>
   <p class="muted">対象：${h(o.service_details)}</p><a class="outline" href="${docLink(t,"quote")}" target="_blank" rel="noopener">見積書を表示・PDF保存</a>
  </section>
  <section class="panel"><div class="eyebrow">AGREEMENT</div><h2>契約内容・電子署名</h2><p class="muted">契約相手方：${h(issuerName)}<br>お申込者：${h(o.signer_name)}</p>
  <details><summary>契約書全文を確認する</summary><pre class="agreement">${h(o.agreement_text)}</pre></details>
  <a class="outline" href="${docLink(t,"agreement")}" target="_blank" rel="noopener">契約書を表示・PDF保存</a>
  ${signed ? `<p class="success">署名済み（${h(new Date(o.signed_at).toLocaleString("ja-JP",{timeZone:"Asia/Tokyo"}))}）</p>` : `
   <form id="sign-form" data-hash="${h(o.agreement_hash)}" data-token="${h(t)}">
    <label class="check"><input type="checkbox" name="readTerms" required> 契約書全文を確認し、内容に同意します</label>
    <label class="check"><input type="checkbox" name="authority" required> 私は契約締結の正当な権限を有します</label>
    <div class="signature-wrap"><span>こちらに指またはマウスで署名</span><canvas id="signature" width="760" height="210" aria-label="署名欄"></canvas><button type="button" class="text-button" id="clear-signature">署名を消す</button></div>
    <label>署名者氏名<input name="signedBy" required value="${h(o.signer_name)}" maxlength="80"></label>
    <label>署名者メール<input type="email" name="signedEmail" required value="${h(o.signer_email)}" maxlength="200"></label>
    <button class="primary" type="submit">署名して契約に同意する</button>
    <p class="muted">署名日時、接続元、文書ハッシュを保存します。本人確認には対面での本人・権限確認を併用してください。</p>
   </form>`}
  </section></div>
  <section class="panel payment"><div><div class="eyebrow">PAYMENT</div><h2>クレジットカードでお申し込み</h2>
  <p>月額16,500円（税込）をカードで継続決済します。カード情報の入力はStripeの安全な決済画面で行います。</p><p class="muted">OpenAI APIの利用料は別契約・別課金です。<a href="https://platform.openai.com/settings/organization/billing/overview" target="_blank" rel="noopener">OpenAI公式のAPI支払い設定</a></p></div>
  <div>${paid ? `<p class="success">お支払いを確認しました</p>` : `<button class="primary" id="checkout-button" data-token="${h(t)}" ${signed?"":"disabled"}>カード登録・決済へ進む</button>`}
  <p role="status" id="checkout-message"></p></div></section>
  <section class="panel"><h2>書類を受け取る</h2><div class="docs">
  <a href="${docLink(t,"quote")}" target="_blank" rel="noopener">見積書</a><a href="${docLink(t,"agreement")}" target="_blank" rel="noopener">契約書</a>
  ${o.stripe_invoice_url ? `<a href="/o/${h(t)}/invoice" target="_blank" rel="noopener">請求書（Stripe発行）</a>` : "<span>請求書：決済後に発行</span>"}
  ${o.stripe_receipt_url ? `<a href="/o/${h(t)}/receipt" target="_blank" rel="noopener">領収書（Stripe発行）</a>` : "<span>領収書：決済後に発行</span>"}
  </div></section>
</main><script src="/app.js" defer></script>`+footer);
});

app.get("/o/:token/qr.svg",async (req,res)=>{
  const offer=await fetchOffer(req.params.token);
  if(!offer) return res.status(404).end();
  const url=`${baseUrl}/o/${req.params.token}`;
  const qr=await QRCode.toString(url,{type:"svg",width:260,margin:2,errorCorrectionLevel:"M"});
  res.set("Cache-Control","private, no-store");
  res.type("image/svg+xml").send(qr);
});

app.post("/api/offers/:token/sign",async (req,res)=>{
  const o=await fetchOffer(req.params.token);
  if(!o) return fail(res,404,"見積が見つかりません");
  if(o.signed_at) return fail(res,409,"署名済みです");
  const {signedBy,signedEmail,signatureImage,agreementHash,readTerms,authority}=req.body||{};
  if(readTerms!==true||authority!==true||agreementHash!==o.agreement_hash) return fail(res,400,"契約書の同意・整合性を確認できません");
  if(typeof signedBy!=="string"||!signedBy.trim()||signedBy.length>80||typeof signedEmail!=="string"||signedEmail.toLowerCase()!==o.signer_email.toLowerCase()) return fail(res,400,"署名者情報を確認してください");
  if(typeof signatureImage!=="string"||!/^data:image\/png;base64,[A-Za-z0-9+/=]+$/.test(signatureImage)||signatureImage.length>200000) return fail(res,400,"署名画像が不正です");
  const bytes=Buffer.from(signatureImage.slice(22),"base64");
  if(bytes.length<100||bytes.subarray(0,8).toString("hex")!=="89504e470d0a1a0a") return fail(res,400,"PNG形式の署名が必要です");
  const result=await pool.query(`UPDATE offers SET signed_at=NOW(),status='signed',signed_by=$2,signed_email=$3,signed_ip=$4,signed_user_agent=$5,signature_image=$6
 WHERE id=$1 AND signed_at IS NULL RETURNING id`,
 [o.id,signedBy.trim(),signedEmail,req.ip,(req.get("user-agent")||"").slice(0,350),signatureImage]);
  if(!result.rowCount) return fail(res,409,"既に署名されています");
  res.json({signed:true});
});

app.post("/api/offers/:token/checkout",async(req,res)=>{
  const o=await fetchOffer(req.params.token);
  if(!o) return fail(res,404,"見積が見つかりません");
  if(!o.signed_at) return fail(res,409,"先に電子署名が必要です");
  if(o.status==="paid") return fail(res,409,"決済済みです");
  if(!stripe || !process.env.STRIPE_TAX_RATE_ID || !process.env.STRIPE_SECRET_KEY || !process.env.STRIPE_WEBHOOK_SECRET)
    return fail(res,503,"Stripe接続設定が未完了です");
  try {
    if(o.stripe_checkout_session_id) {
      const existing=await stripe.checkout.sessions.retrieve(o.stripe_checkout_session_id);
      if(existing.status==="open" && existing.url) return res.json({url:existing.url});
      if(existing.status==="complete") return fail(res,409,"決済確認中です。ページを再読込してください");
    }
    const session=await stripe.checkout.sessions.create({
      mode:"subscription",payment_method_types:["card"],
      client_reference_id:o.id,customer_email:o.signer_email,
      line_items:[{price_data:{currency:"jpy",product_data:{name:"ブログ自動AI投稿サービス（月額）"},unit_amount:MONTHLY_PRICE,recurring:{interval:"month"}},quantity:1,tax_rates:[process.env.STRIPE_TAX_RATE_ID]}],
      metadata:{offer_id:o.id},
      subscription_data:{metadata:{offer_id:o.id}},
      success_url:`${baseUrl}/o/${req.params.token}?payment=success`,
      cancel_url:`${baseUrl}/o/${req.params.token}?payment=cancel`
    },{idempotencyKey:`offer-${o.id}-v1`});
    await pool.query("UPDATE offers SET stripe_checkout_session_id=$2 WHERE id=$1",[o.id,session.id]);
    res.json({url:session.url});
  } catch(error) {
    console.error("checkout error",error?.message);
    return fail(res,502,"決済セッションを開始できません。Stripe設定を確認してください");
  }
});

app.get("/o/:token/document/:kind",async(req,res)=>{
  const o=await fetchOffer(req.params.token);
  if(!o) return res.status(404).send("見つかりません");
  const kind=req.params.kind;
  if(kind!=="quote"&&kind!=="agreement") return res.status(404).end();
  const issued=new Date(o.created_at).toLocaleDateString("ja-JP",{timeZone:"Asia/Tokyo"});
  const sign= o.signed_at ? `<div class="sign-block"><div>同意日時：${h(new Date(o.signed_at).toLocaleString("ja-JP",{timeZone:"Asia/Tokyo"}))}</div><div>署名者：${h(o.signed_by)}</div><img alt="契約者の電子署名" src="${h(o.signature_image)}"><div class="muted small">文書SHA-256：${h(o.agreement_hash)}<br>接続元記録：${h(o.signed_ip)}</div></div>` : '<div class="muted">未署名：契約書は効力確認前です。</div>';
  const issuer=`<div class="doc-issuer"><strong>${h(issuerName)}</strong><br>${h(issuerAddress)}<br>${h(issuerEmail)}${registration ? "<br>登録番号："+h(registration) : "<br>適格請求書発行事業者の登録番号：未設定"}</div>`;
  const content=kind==="quote" ? `<h1>見積書</h1><div class="doc-two"><div><h2>${h(o.buyer_company)} 御中</h2><p>下記のとおり御見積もり申し上げます。</p></div><div class="doc-meta">見積日：${h(issued)}<br>見積書番号：${h(o.quote_number)}${issuer}</div></div>
  <h3>件名：ブログ自動AI投稿サービス（月額）</h3><div class="doc-totals"><span>小計<br><strong>${yen(MONTHLY_PRICE)}</strong></span><span>消費税<br><strong>${yen(TAX_AMOUNT)}</strong></span><span>見積金額<br><strong>${yen(TOTAL)}</strong></span></div>
  <table><thead><tr><th>摘要</th><th>数量</th><th>単価</th><th>明細金額</th></tr></thead><tbody><tr><td>ブログ自動AI投稿サービス（月額）</td><td>1月</td><td>15,000</td><td>15,000</td></tr></tbody></table>
  <p>10%対象（税抜）：15,000円　／　消費税：1,500円</p><p>納品期限：毎月末日</p>
  <p class="note">対象媒体・個別仕様：${h(o.service_details)}<br>お支払い条件：電子契約後、Stripeにて初回カード決済。その後、月ごとに継続課金。OpenAI API利用料は別途顧客負担です。</p>`
  : `<h1>業務委託契約書</h1><pre class="agreement doc-terms">${h(o.agreement_text)}</pre>${issuer}${sign}`;
  res.send(docHead(kind==="quote"?"見積書":"業務委託契約書","print-document")+`<div class="print-toolbar"><button class="primary" id="print-document">印刷・PDFとして保存</button><a href="/o/${h(req.params.token)}">契約画面へ戻る</a></div><main class="paper">${content}</main><script src="/app.js" defer></script>`+footer);
});
app.get("/o/:token/:kind",async(req,res)=>{
  const o=await fetchOffer(req.params.token);
  if(!o) return res.status(404).end();
  const url=req.params.kind==="invoice"?o.stripe_invoice_url:req.params.kind==="receipt"?o.stripe_receipt_url:null;
  if(!url) return res.status(404).send("決済後、Stripeから発行された書類が利用できます");
  if(!/^https:\/\/(invoice|receipt|pay)\.stripe\.com\//.test(url)) return res.status(500).send("無効な書類リンク");
  res.redirect(302,url);
});

app.use((error,req,res,next)=>{console.error("server error",error);fail(res,500,"サーバーエラー");});
app.listen(port,()=>console.log(`Sales contract server listening on ${port}`));
