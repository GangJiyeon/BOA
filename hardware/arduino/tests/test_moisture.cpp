#include <cassert>
#include <string>
#include "../moisture_sensor/moisture_sensor.ino"
void tick(uint16_t sample=507,bool fresh=true){Wire1.sample=sample;Wire1.status=fresh?8:0;delay(100);loop();}
int main(){
 { Fdc2112 tuned; Wire1.minDrive=7;Wire1.maxDrive=18;
   assert(tuned.begin() && tuned.driveCode==18 && tuned.driveCandidatesTested==14);
   const auto drive=Wire1.regs[0x1E];uint16_t value;
   Wire1.status=8;Wire1.sample=0x1000|2200;
   assert(tuned.sample(value)==1 && Wire1.regs[0x1E]==drive); // No drive changes during contact.
   Wire1.minDrive=0;Wire1.maxDrive=31;Wire1.sample=507;
 }
 assert(Fdc2112::hasHeadroom(169,170));
 assert(!Fdc2112::hasHeadroom(14,235));
 assert(!Fdc2112::hasHeadroom(0,0));
 { Fdc2112 ranged;
   assert(ranged.begin() && ranged.referenceDivider==44);
   Wire1.surveyCode=1000;assert(ranged.begin() && ranged.referenceDivider==22);
   Wire1.surveyCode=2000;assert(ranged.begin() && ranged.referenceDivider==11);
   Wire1.surveyCode=4000;assert(!ranged.begin() && ranged.fault==Fdc2112::RANGE_ERROR);
   Wire1.surveyCode=0;assert(!ranged.begin() && ranged.fault==Fdc2112::RANGE_ERROR);
   Wire1.surveyCode=678;Wire1.surveyFresh=false;
   assert(!ranged.begin() && ranged.fault==Fdc2112::NOT_READY);
   Wire1.surveyFresh=true;Wire1.surveyFlags=0x1000;
   assert(!ranged.begin() && ranged.fault==Fdc2112::AMPLITUDE_WARNING);
   Wire1.surveyFlags=0;Wire1.regs[0x1C]=0x0600;Wire1.ignoredRegister=0x1C;
   assert(!ranged.begin() && ranged.fault==Fdc2112::CONFIG_ERROR);
   Wire1.ignoredRegister=-1;
 }
  { Fdc2112 physical; physical.calibrated=true; physical.baseline=506; physical.averageCount=494;
    const float p=physical.capacitanceChangePercent(); assert(p>3.64f && p<3.66f);
    physical.averageCount=506; assert(physical.capacitanceChangePercent()==0.0f); }
 setup();
 assert(sensor.referenceDivider==44 && Wire1.regs[0x14]==0x202C);
 assert(Wire1.regs[0x08]==0x1000 && Wire1.regs[0x10]==0x0100);
 assert(Wire1.regs[0x1A]==0x1401 && Wire1.regs[0x1B]==0x0209);
 assert(Wire1.regs[0x19]==0x3801 && Wire1.regs[0x1E]==uint16_t(sensor.driveCode<<11));
 for (int reg : {0x08,0x10,0x1A,0x1B,0x19,0x1E}) {
   Wire1.regs[reg]^=(reg==0x19?0x0800:reg==0x1E?0x0800:reg==0x1B?1:0x10);assert(!sensor.verifyConfiguration());assert(sensor.begin());
 }
 assert(sensorReady && bleReady && !sensor.calibrated && !calibrationPending);
 Wire1.regs[0x0C]=0;assert(!sensor.verifyConfiguration() && sensor.fault==Fdc2112::CONFIG_ERROR);
 assert(sensor.begin()); // Successful reset restores the reference profile.
 Wire1.regs[0x1C] |= 1;assert(sensor.verifyConfiguration()); // Reserved bits ignored.
 uint16_t raw;Wire1.sample=63;Wire1.status=8;
 assert(sensor.sample(raw)==1 && raw==65535 && sensor.fault==Fdc2112::RANGE_ERROR && !sensor.referenceAvailable);
 Wire1.sample=3585;Wire1.status=8;assert(sensor.sample(raw)==1 && sensor.fault==Fdc2112::RANGE_ERROR);
 Wire1.sample=507;Wire1.status=8;const int before=Wire1.dataReads;
 assert(sensor.sample(raw)==0 && raw==507 && Wire1.dataReads==before+1);
 assert(sensor.sample(raw)==2 && raw==65535 && Wire1.dataReads==before+1);
 transport.command.data={1};transport.command.pending=true;tick();assert(calibrationPending);
 for(int i=0;i<55;++i){tick();}
 assert(sensor.calibrated && sensor.baseline==507 && BLE.polls>50);
 tick(501);assert(sensor.averageCount==501);
 assert(transport.driven.data.size()==20 && transport.driven.data[0]==5 && transport.driven.data[16]==sensor.driveCode);
 assert(transport.profiled.data.size()==20 && transport.profiled.data[0]==4);
 assert(transport.profiled.data[18]==44 && transport.profiled.data[19]==4);
 tick(492);assert(sensor.averageCount==492);
 tick(293);assert(sensor.averageCount==293);assert(transport.fresh.data[0]==3 && transport.fresh.data.size()==20 && transport.fresh.data[16]==42);
 tick(0x1000|293);assert(transport.profiled.data[19]==0x14);assert(transport.measurement.data[2]==1 && transport.fresh.data[19]==0x10 && sensorReady);
 assert(transport.fresh.data[14]==37 && transport.fresh.data[15]==1); // 293 diagnostic count, not a usable sample.
 Wire1.status=0x208;Wire1.sample=0x1000|293;sensor.sample(raw);assert(std::string(sensor.faultName())=="amplitude_low");
 Wire1.status=0x408;Wire1.sample=0x1000|293;sensor.sample(raw);assert(std::string(sensor.faultName())=="amplitude_high");
 tick(293,false);assert(transport.fresh.data[2]==2 && transport.fresh.data[16]==255 && !sensor.referenceAvailable);
 // A slow eight-count air drift fits the old range gate, but is not a stable baseline.
 scheduleCalibration();delay(3000);
 for(int i=0;i<20;++i)tick(2500+i*32/19);
 assert(!sensor.calibrated && calibrationFailed);
 // Rounding avoids the old downward integer bias for an even half-count mean.
 scheduleCalibration();delay(3000);
 for(int i=0;i<20;++i)tick(i%2?501:500);
 assert(sensor.calibrated && sensor.baseline==501);
 // A long no-data gap must discard the old partial window.
 scheduleCalibration();delay(3000);for(int i=0;i<10;++i)tick();
 tick(507,false);tick(507,false);tick(507,false);tick();
 assert(calibrationCount==1 && !sensor.calibrated);
 Serial.input="c";tick();for(int i=0;i<55;++i)tick(0);assert(!sensor.calibrated && calibrationFailed);
 Serial.input="c";tick();for(int i=0;i<55;++i){tick();}
 assert(sensor.calibrated);
 Wire1.fail=true;for(int i=0;i<3;++i)tick();assert(!sensorReady && !sensor.calibrated);
 Wire1.fail=false;delay(5001);tick();assert(sensorReady && !sensor.calibrated && !calibrationPending);
 Serial.input="c";tick();for(int i=0;i<55;++i)tick(507,false);assert(calibrationPending);for(int i=0;i<30;++i)tick(507,false);assert(!calibrationPending && calibrationFailed);
}
