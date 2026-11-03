const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
function page(storage,lang='ko') {
  const listeners={}, windowListeners={};
  const root={dataset:{},lang};
  const label={textContent:''};
  const button={hidden:true,attrs:{},setAttribute(k,v){this.attrs[k]=v;},querySelector(){return label;}};
  const document={documentElement:root,readyState:'loading',querySelectorAll(){return [button];},addEventListener(name,fn){listeners[name]=fn;}};
  vm.runInNewContext(fs.readFileSync('assets/theme.js','utf8'),{document,localStorage:storage,window:{addEventListener(name,fn){windowListeners[name]=fn;}}});
  const initial=root.dataset.theme;
  listeners.DOMContentLoaded();
  return {root,button,label,initial,click(){listeners.click({target:{closest(){return button;}}});},storageEvent(e){windowListeners.storage(e);}};
}
function storage(initial) {
  const values=new Map(initial?[['aisitei_theme',initial]]:[]);
  return {getItem:k=>values.get(k)||null,setItem:(k,v)=>values.set(k,v)};
}
test('first visit stays light and a toggle survives navigation to a new page',()=>{
  const saved=storage();const first=page(saved);
  assert.equal(first.initial,'light');assert.equal(first.button.hidden,false);
  first.click();assert.equal(first.root.dataset.theme,'dark');assert.equal(first.button.attrs['aria-pressed'],'true');
  const next=page(saved);assert.equal(next.initial,'dark');assert.equal(next.label.textContent,'라이트 모드');
  next.click();assert.equal(saved.getItem('aisitei_theme'),'light');
});
test('blocked browser storage does not prevent changing appearance',()=>{
  const blocked={getItem(){throw Error('blocked');},setItem(){throw Error('blocked');}};
  const view=page(blocked);view.click();assert.equal(view.root.dataset.theme,'dark');view.click();assert.equal(view.root.dataset.theme,'light');
});
test('other-tab preferences synchronize and invalid values fall back to light',()=>{
  const view=page(storage('invalid'),'en');assert.equal(view.initial,'light');
  view.storageEvent({key:'aisitei_theme',newValue:'dark'});assert.equal(view.root.dataset.theme,'dark');assert.equal(view.label.textContent,'Light mode');
  view.storageEvent({key:'unrelated',newValue:'light'});assert.equal(view.root.dataset.theme,'dark');
  view.storageEvent({key:'aisitei_theme',newValue:null});assert.equal(view.root.dataset.theme,'light');
});
