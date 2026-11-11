#pragma once
#include <map>
struct W { std::map<int,uint16_t> regs; int reg=0,n=0,pos=0; uint16_t value=0,sample=507,status=8; bool fail=false; int dataReads=0;
 uint32_t surveyCode=678; bool surveyFresh=true; uint16_t surveyFlags=0; int ignoredRegister=-1; int minDrive=0,maxDrive=31;
 void begin(){} void setClock(int){} void beginTransmission(int){n=0;value=0;}
 void write(uint8_t v){if(n++==0)reg=v;else value=(value<<8)|v;}
 int endTransmission(bool=true){if(fail)return 4;if(n==3 && reg!=ignoredRegister)regs[reg]=value;return 0;}
 int requestFrom(uint8_t,uint8_t){pos=0;return 2;}
 int read(){bool survey=(regs[0x1C]&0x0600)==0;uint16_t v=regs[reg];if(reg==0x7E)v=0x5449;if(reg==0x7F)v=0x3054;if(reg==0x18)v=survey?(surveyFresh?8:0):status;if(reg==0){v=survey?uint16_t(surveyCode*(regs[0x14]&1023)/11/16)|surveyFlags:sample;if((regs[0x1E]>>11)<minDrive||(regs[0x1E]>>11)>maxDrive)v|=0x1000;if(pos==1){++dataReads;status &= ~8;}}return pos++==0?v>>8:v&255;}
}; inline W Wire1;
