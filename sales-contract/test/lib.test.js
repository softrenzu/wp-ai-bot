import test from "node:test";
import assert from "node:assert/strict";
import { MONTHLY_PRICE, TAX_AMOUNT, TOTAL, makeAgreement, makeToken, sha256, yen } from "../lib.js";
test("monthly total matches quoted price",()=>{assert.equal(MONTHLY_PRICE,15000);assert.equal(TAX_AMOUNT,1500);assert.equal(TOTAL,16500);assert.equal(yen(TOTAL),"16,500円");});
test("a generated client token is high entropy",()=>{const a=makeToken(),b=makeToken();assert.match(a,/^[a-f0-9]{64}$/);assert.notEqual(a,b);});
test("agreement binds parties and explicitly separates API charges",()=>{
 const t=makeAgreement({issuerName:"株式会社穣",issuerAddress:"所在地",buyerCompany:"テスト株式会社",signerName:"試験 太郎",serviceDetails:"週2回"});
 assert.match(t,/テスト株式会社/);assert.match(t,/週2回/);assert.match(t,/OpenAI API/);assert.equal(sha256(t).length,64);
});
