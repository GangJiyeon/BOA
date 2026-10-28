#pragma once
#include <cstdint>
#include <sstream>
#include <string>
#define HEX 16
inline uint32_t ticks=0; inline uint32_t millis(){return ticks;} inline void delay(int n){ticks+=n;}
struct S { std::ostringstream out; std::string input;
 void begin(int){} operator bool(){return true;} int available(){return input.size();} int read(){char c=input[0];input.erase(0,1);return c;}
 template<class T> void print(T v){out<<v;} template<class T> void print(T v,int){out<<unsigned(v);}
 void println(){out<<'\n';} template<class T> void println(T v){print(v);println();} template<class T> void println(T v,int b){print(v,b);println();}
}; inline S Serial;
