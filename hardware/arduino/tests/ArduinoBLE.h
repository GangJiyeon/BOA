#pragma once
#include <vector>
#define BLEWrite 4
#define BLERead 1
#define BLENotify 2
#define BLEConnected 1
#define BLEDisconnected 2
struct BLEDevice{};
struct BLECharacteristic {std::vector<uint8_t> data; bool pending=false; bool written(){bool v=pending;pending=false;return v;} int readValue(uint8_t &v){if(data.empty())return 0;v=data[0];return 1;} BLECharacteristic(const char*,int,int,bool){} void writeValue(uint8_t*p,unsigned n){data.assign(p,p+n);}};
struct BLEService { BLEService(const char*){} void addCharacteristic(BLECharacteristic&){} };
struct B { int polls=0; bool begin(){return true;} void setLocalName(const char*){} void setAdvertisedService(BLEService&){} void addService(BLEService&){} void advertise(){} void poll(){++polls;} void setEventHandler(int,void(*)(BLEDevice)){} };inline B BLE;
