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
class Device extends EventTarget {gatt={connected:false,connect:async()=>{this.gatt.connected=true;return {getPrimaryService:async uuid=>{assert.equal(uuid,protocol.SERVICE_UUID);return {getCharacteristic:async uuid=>{if(uuid!==protocol.MEASUREMENT_UUID)throw new DOMException('old firmware','NotFoundError');return characteristic}}}}},disconnect:()=>{this.gatt.connected=false}}}
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
await load('../src/moisture/hydrationEstimate.ts')
const {validateMoisture}=await load('../src/api/moisture.ts', {"'../moisture/hydrationEstimate'":JSON.stringify(urls.get('../src/moisture/hydrationEstimate.ts')),"'./client'":JSON.stringify(urls.get('../src/api/client.ts')), "'../moisture/protocol'":JSON.stringify(urls.get('../src/moisture/protocol.ts'))})
const v2=()=>{const d=new DataView(new ArrayBuffer(20));d.setUint8(0,2);d.setUint8(3,2);d.setUint16(4,395,true);d.setUint16(12,506,true);d.setUint16(14,395,true);d.setUint16(16,21,true);return d}
assert.equal(protocol.decodeMeasurement(v2()).reference.percent,21)
let warning=v2();warning.setUint8(2,1);warning.setUint16(4,65535,true);warning.setUint16(18,0x1000,true)
assert.equal(protocol.decodeMeasurement(warning).reference.amplitudeWarning,true)
for(const [offset,value] of [[12,0],[14,4096],[16,22],[18,0x2000]]) {const d=v2();d.setUint16(offset,value,true);assert.throws(()=>protocol.decodeMeasurement(d))}
let pendingPacket=v2();pendingPacket.setUint8(3,1);assert.throws(()=>protocol.decodeMeasurement(pendingPacket))
const projection=protocol.rawSubmission(protocol.decodeMeasurement(v2()));assert.equal(projection.protocol_version,1);assert.equal('reference' in projection,false)
const control=new Characteristic();control.writeValueWithResponse=async v=>{assert.deepEqual([...v],[1])}
const modern=new Device();modern.gatt.connect=async()=>{modern.gatt.connected=true;return {getPrimaryService:async()=>({getCharacteristic:async uuid=>uuid===protocol.COMMAND_UUID?control:characteristic})}}
const modernAdapter=new BleMoistureAdapter(observer,{requestDevice:async()=>modern});await modernAdapter.connect();await modernAdapter.calibrate();modernAdapter.disconnect();await assert.rejects(modernAdapter.calibrate())
const saved=globalThis.fetch
try {globalThis.fetch=async(url,init)=>{assert.equal(url,'/api/skin/moisture/validate');const body=JSON.parse(init.body);assert.equal(body.analysis_id,7);assert.equal(body.measurement.raw_value,1200);assert.equal('moisture_score' in body,false);return new Response('{}')};await validateMoisture(decoded,7)} finally {globalThis.fetch=saved}
console.log('Moisture protocol, BLE lifecycle, cancellation, mock guard and API payload: passed')

// v4: frozen sensor configuration is carried in the former reserved bits.
const profiled=v2();profiled.setUint8(0,4);profiled.setUint16(18,0x42c,true)
assert.equal(protocol.decodeMeasurement(profiled).sensor_profile.reference_divider,44)
for(const metadata of [0x400,0x40a,0x800,0x2c,0x142c]){
 const bad=new DataView(profiled.buffer.slice(0));bad.setUint16(18,metadata,true)
 assert.throws(()=>protocol.decodeMeasurement(bad))
}
const startup=new DataView(profiled.buffer.slice(0));startup.setUint16(18,0,true)
assert.equal(protocol.decodeMeasurement(startup).sensor_profile,undefined)
console.log('Profiled BLE: verified divider, missing configuration and malformed metadata passed')

// Real discovery prefers v4 even if legacy characteristics appear first.
const p4=new Characteristic();p4.uuid=protocol.PROFILED_UUID;p4.value=profiled;p4.readValue=async()=>profiled
const p3=new Characteristic();p3.uuid=protocol.FRESH_UUID
const discovering=new Device();discovering.gatt.connect=async()=>{
 discovering.gatt.connected=true
 return {getPrimaryService:async()=>({getCharacteristics:async()=>[p3,p4],getCharacteristic:async uuid=>{
  if(uuid===protocol.COMMAND_UUID)return control
  throw new Error('Direct measurement lookup must not replace enumeration')
 }})}
}
const discoverAdapter=new BleMoistureAdapter(observer,{requestDevice:async()=>discovering})
await discoverAdapter.connect()
assert.equal(p4.starts,1);assert.equal(p3.starts,0)
assert.equal(values.at(-1).protocol_version,4);assert.equal(values.at(-1).sensor_profile.reference_divider,44)
assert.equal(protocol.sensorReadiness(values.at(-1)),null)
assert(protocol.sensorReadiness(decoded).includes('이전 데이터 형식'))
assert(protocol.sensorReadiness(protocol.decodeMeasurement(startup)).includes('초기화'))
assert(!protocol.sensorReadiness(protocol.decodeMeasurement(startup)).includes('업로드'))
discoverAdapter.disconnect()
console.log('BLE discovery + initial read: v4 priority, legacy vs uninitialized diagnostics passed')

// v5: drive is frozen at calibration, and high/low warning evidence survives BLE.
const drivePacket=new DataView(profiled.buffer.slice(0));drivePacket.setUint8(0,5);drivePacket.setUint16(16,18,true)
const driveValue=protocol.decodeMeasurement(drivePacket)
assert.equal(driveValue.sensor_profile.drive_current_code,18)
assert.equal(driveValue.reference.percent,null)
assert.equal(protocol.sensorReadiness(driveValue),null)
for(const [direction,bits] of [['low',0x200],['high',0x400],['both',0x600],['unknown',0]]){
 const d=new DataView(drivePacket.buffer.slice(0));d.setUint8(2,1);d.setUint16(4,65535,true);d.setUint16(18,0x142c,true);d.setUint16(16,18|bits,true)
 const result=protocol.decodeMeasurement(d);assert.equal(result.reference.amplitude_direction,direction);assert.equal(result.status,'sensor_error');assert.equal(result.raw_value,null)
}
const invalidDrive=new DataView(drivePacket.buffer.slice(0));invalidDrive.setUint16(16,32,true);assert.throws(()=>protocol.decodeMeasurement(invalidDrive))
const p5=new Characteristic();p5.uuid=protocol.DRIVEN_UUID;p5.readValue=async()=>drivePacket
discovering.gatt.connect=async()=>{discovering.gatt.connected=true;return {getPrimaryService:async()=>({getCharacteristics:async()=>[p3,p4,p5],getCharacteristic:async()=>control})}}
await discoverAdapter.connect();assert.equal(p5.starts,1);assert.equal(values.at(-1).protocol_version,5);discoverAdapter.disconnect()
console.log('Drive-aware BLE v5: frozen drive, warning directions, no warning-to-valid conversion and discovery priority passed')
