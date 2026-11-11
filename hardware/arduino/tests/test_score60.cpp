#include <cassert>
#include <cmath>
#include "../moisture_sensor/MoistureScore60.h"
int main() {
  using namespace BoaMoisture60;
  const double responses[]={0,.9,12.999,13,22.999,23,27.999,28,39.999,40,45.999,46,100};
  const int scores[]={0,2,9,10,19,20,29,30,39,40,49,50,60};
  bool seen[61]={false};
  for(int i=0;i<13;i++) assert(scoreFromResponse(responses[i])==scores[i]);
  int last=-1;
  for(int i=0;i<=100000;i++) {
    double response=i/1000.0;
    int score=scoreFromResponse(response),index=int(response);
    int level=index<=12?1:index<=22?2:index<=27?3:index<=39?4:index<=45?5:6;
    assert(score>=last && score>=0 && score<=60);
    assert(levelFromScore(score)==level);
    seen[score]=true;last=score;
  }
  for(bool present:seen)assert(present);
  assert(scoreFromResponse(NAN)==-1 && scoreFromResponse(-1)==-1);
  assert(instantaneousScore(2540,2540,44)==-1);
  assert(instantaneousScore(2538,2506,44)==3);
  assert(instantaneousScore(2540,2538,44)==0);
}
