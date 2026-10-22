import assert from 'node:assert/strict'
import fs from 'node:fs/promises'
import ts from 'typescript'
const urls = new Map()
async function load(path, replacements={}) {
  let source = await fs.readFile(new URL(path, import.meta.url),'utf8')
  for (const [from,to] of Object.entries(replacements)) source=source.replaceAll(from,to)
  const {outputText}=ts.transpileModule(source,{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.ES2022}})
  const url=`data:text/javascript;base64,${Buffer.from(outputText).toString('base64')}`
  urls.set(path,url);return import(url)
}
const protocol=await load('../src/moisture/protocol.ts')
const {BleMoistureAdapter,MockMoistureAdapter}=await load('../src/moisture/adapters.ts',{"'./protocol'":JSON.stringify(urls.get('../src/moisture/protocol.ts'))})
const packet=()=>{const v=new DataView(new ArrayBuffer(12));v.setUint8(0,1);v.setUint16(4,1200,true);v.setUint16(6,42,true);v.setUint32(8,123456,true);return v}
const decoded=protocol.decodeMeasurement(packet());assert.equal(decoded.raw_value,1200);assert.equal(decoded.sequence,42);assert.equal(decoded.device_uptime_ms,123456)
for(const [offset,value] of [[0,2],[1,2],[2,3],[3,1]]) {const v=packet();v.setUint8(offset,value);assert.throws(()=>protocol.decodeMeasurement(v))}
assert.throws(()=>protocol.decodeMeasurement(new DataView(new ArrayBuffer(11))))
let v=packet();v.setUint16(4,4096,true);assert.throws(()=>protocol.decodeMeasurement(v))
v=packet();v.setUint8(2,1);assert.throws(()=>protocol.decodeMeasurement(v));v.setUint16(4,65535,true);assert.equal(protocol.decodeMeasurement(v).raw_value,null)
v=packet();v.setUint8(1,1);assert.equal(protocol.decodeMeasurement(v).source,'ble_simulation')
const states=[], values=[], errors=[]
const observer={state:s=>states.push(s),measurement:m=>values.push(m),error:e=>errors.push(e)}
class Characteristic extends EventTarget { value=packet(); starts=0; stops=0; async startNotifications(){this.starts++;return this} async stopNotifications(){this.stops++;return this} }
const characteristic=new Characteristic()
class Device extends EventTarget {gatt={connected:false,connect:async()=>{this.gatt.connected=true;return {getPrimaryService:async uuid=>{assert.equal(uuid,protocol.SERVICE_UUID);return {getCharacteristic:async uuid=>{assert.equal(uuid,protocol.MEASUREMENT_UUID);return characteristic}}}}},disconnect:()=>{this.gatt.connected=false}}}
const device=new Device();let choices=0
const adapter=new BleMoistureAdapter(observer,{requestDevice:async()=>{choices++;return device}})
await Promise.all([adapter.connect(),adapter.connect()]);assert.equal(choices,1);assert.equal(characteristic.starts,1)
characteristic.dispatchEvent(new Event('characteristicvaluechanged'));assert.equal(values.at(-1).raw_value,1200)
characteristic.value=new DataView(new ArrayBuffer(1));characteristic.dispatchEvent(new Event('characteristicvaluechanged'));assert.equal(errors.length,1)
device.dispatchEvent(new Event('gattserverdisconnected'));assert.equal(states.at(-1),'disconnected')
const count=values.length;characteristic.value=packet();characteristic.dispatchEvent(new Event('characteristicvaluechanged'));assert.equal(values.length,count)
await adapter.connect();assert.equal(characteristic.starts,2);adapter.disconnect()
let choose;const pending=new BleMoistureAdapter(observer,{requestDevice:()=>new Promise(resolve=>{choose=resolve})})
const connecting=pending.connect();pending.disconnect();choose(device);await connecting;assert.equal(device.gatt.connected,false)
const denied=new BleMoistureAdapter(observer,{requestDevice:async()=>{throw new Error('permission denied')}});await denied.connect();assert.equal(states.at(-1),'error')
await new BleMoistureAdapter(observer,undefined,false).connect();assert.equal(states.at(-1),'error')
const mock=new MockMoistureAdapter(observer,true);await mock.connect();assert.equal(values.at(-1).source,'mock');mock.disconnect()
await assert.rejects(new MockMoistureAdapter(observer,false).connect())
await load('../src/api/client.ts')
const {validateMoisture}=await load('../src/api/moisture.ts',{"'./client'":JSON.stringify(urls.get('../src/api/client.ts'))})
const saved=globalThis.fetch
try {globalThis.fetch=async(url,init)=>{assert.equal(url,'/api/skin/moisture/validate');const body=JSON.parse(init.body);assert.equal(body.analysis_id,7);assert.equal(body.measurement.raw_value,1200);assert.equal('moisture_score' in body,false);return new Response('{}')};await validateMoisture(decoded,7)} finally {globalThis.fetch=saved}
console.log('Moisture protocol, BLE lifecycle, cancellation, mock guard and API payload: passed')
