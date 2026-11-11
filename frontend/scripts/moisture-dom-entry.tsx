import React from 'react';import {createRoot} from 'react-dom/client';
import MoisturePanel from '../src/components/MoisturePanel';
import {useMoistureResult} from '../src/hooks/useMoistureResult';
export {act} from 'react'; export {createRoot,React,MoisturePanel};
export function ResultHarness(p:any){const h=useMoistureResult(p.id,p.scope,p.active);(globalThis as any).resultHook=h;return <p>{h.status}</p>}

export {default as CosmeticPreview} from '../src/components/CosmeticPreview';

import {useAutoMoisture} from '../src/hooks/useAutoMoisture';
export function AutoHarness(p:any){const h=useAutoMoisture(p.value,true,null,p.onComplete,p.initial);(globalThis as any).autoHook=h;return <p>{h.view.phase}</p>}
