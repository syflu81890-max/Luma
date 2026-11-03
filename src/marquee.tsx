import React,{useEffect,useRef,useState} from 'react';

export function useMarquee(selected:string[],setSelected:(ids:string[])=>void){
 const root=useRef<HTMLDivElement>(null),drag=useRef<any>(null),suppress=useRef(false),[box,setBox]=useState<any>(null);
 useEffect(()=>()=>{if(drag.current)document.body.style.userSelect=drag.current.userSelect||'';cancelAnimationFrame(drag.current?.frame)},[]);
 const select=(x:number,y:number)=>{
  const d=drag.current;if(!d||!root.current)return;
  const rect={left:Math.min(d.x,x),top:Math.min(d.y,y),right:Math.max(d.x,x),bottom:Math.max(d.y,y)};setBox(rect);
  const ids=[...root.current.querySelectorAll<HTMLElement>('[data-select-id]')].filter(e=>{const r=e.getBoundingClientRect();return r.left<rect.right&&r.right>rect.left&&r.top<rect.bottom&&r.bottom>rect.top}).map(e=>e.dataset.selectId!);
  setSelected([...new Set([...d.base,...ids])]);
 };
 const end=(e:React.PointerEvent)=>{
  const d=drag.current;if(!d)return;
  cancelAnimationFrame(d.frame);drag.current=null;document.body.style.userSelect=d.userSelect;
  if(d.started){suppress.current=true;if(root.current?.hasPointerCapture(e.pointerId))root.current.releasePointerCapture(e.pointerId);setTimeout(()=>suppress.current=false,0)}
  setBox(null);
 };
 const props={
  onPointerDownCapture:(e:React.PointerEvent)=>{if(e.button!==0||(e.target as HTMLElement).closest('button,input,select,textarea,a'))return;drag.current={x:e.clientX,y:e.clientY,base:e.ctrlKey||e.metaKey||e.shiftKey?selected:[],started:false,userSelect:document.body.style.userSelect,pointer:e.pointerId}},
  onPointerMove:(e:React.PointerEvent)=>{
   const d=drag.current;if(!d)return;
   if(!d.started&&Math.hypot(e.clientX-d.x,e.clientY-d.y)<6)return;
   if(!d.started){d.started=true;document.body.style.userSelect='none';root.current?.setPointerCapture(e.pointerId)}
   select(e.clientX,e.clientY);cancelAnimationFrame(d.frame);
   const pane=root.current?.closest<HTMLElement>('.library'),x=e.clientX,y=e.clientY;
   const scroll=()=>{if(!drag.current||!pane)return;const r=pane.getBoundingClientRect(),delta=y>r.bottom-45?12:y<r.top+45?-12:0;if(delta){const old=pane.scrollTop;pane.scrollTop+=delta;d.y-=pane.scrollTop-old;select(x,y);d.frame=requestAnimationFrame(scroll)}};d.frame=requestAnimationFrame(scroll);
  },
  onPointerUp:end,onPointerCancel:end,
  onClickCapture:(e:React.MouseEvent)=>{if(suppress.current){e.preventDefault();e.stopPropagation()}},
 };
 return {root,props,overlay:box&&<div className="marquee-box" aria-hidden="true" style={{position:'fixed',left:box.left,top:box.top,width:box.right-box.left,height:box.bottom-box.top}}/>};
}
